import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getJob,
  getRun,
  getRunLog,
  getRunProgress,
  getRunRecruiterReview,
  importRun,
  invokeRun,
  listResumeVersions,
} from "../api";
import type {
  ClaudeRun,
  Job,
  RecruiterReview,
  ResumeVersion,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";
import {
  parseTimestamp,
  runIsActive,
  runNeedsImport,
  runStatusLabel,
} from "../lib/workflow";

export const RUN_POLL_INTERVAL_MS = 5000;
export const RUN_LOG_POLL_INTERVAL_MS = 2000;
export const RUN_PROGRESS_POLL_INTERVAL_MS = 2000;
export const RUN_LOG_DEFAULT_DISPLAY_LINES = 8;

const ANSI_ESCAPE_RE = /\x1B\[[0-?]*[ -/]*[@-~]/g;

/**
 * A run is in a terminal state once we should stop live-polling it. The
 * intermediate `completed` state is non-terminal because the frontend
 * still needs to drive the import handshake.
 */
export function runIsTerminal(status: string): boolean {
  return status === "imported" || status === "failed";
}

/**
 * Sanitize raw run.log lines into a compact, user-readable list:
 *   - strip ANSI escape codes (in case any leaked through the backend)
 *   - drop blank/whitespace-only lines
 *   - collapse adjacent duplicates (Claude tends to repeat spinner ticks)
 *   - strip the `jobapply: ` prefix so milestones read cleanly
 *   - keep only the last `maxLines` lines
 */
export function sanitizeRunLogLines(
  lines: string[],
  maxLines: number = RUN_LOG_DEFAULT_DISPLAY_LINES,
): string[] {
  const cleaned: string[] = [];
  for (const raw of lines) {
    const stripped = raw.replace(ANSI_ESCAPE_RE, "").trim();
    if (!stripped) continue;
    const display = stripped.startsWith("jobapply: ")
      ? stripped.slice("jobapply: ".length)
      : stripped;
    if (cleaned.length > 0 && cleaned[cleaned.length - 1] === display) continue;
    cleaned.push(display);
  }
  if (cleaned.length <= maxLines) return cleaned;
  return cleaned.slice(cleaned.length - maxLines);
}

export function runStatusBadge(status: string): {
  label: string;
  variant: string;
} {
  switch (status) {
    case "created":
      return { label: runStatusLabel(status), variant: "pending" };
    case "running":
      return { label: runStatusLabel(status), variant: "running" };
    case "completed":
      return { label: runStatusLabel(status), variant: "completed" };
    case "imported":
      return { label: runStatusLabel(status), variant: "completed" };
    case "failed":
      return { label: runStatusLabel(status), variant: "failed" };
    default:
      return {
        label: status.charAt(0).toUpperCase() + status.slice(1),
        variant: "default",
      };
  }
}

interface RunAutoPollingArgs {
  runId: string | null;
  run: ClaudeRun | null;
  needsImport: boolean;
  onUpdate: (run: ClaudeRun) => void;
  onImported: (version: ResumeVersion) => void;
  onImportError: (message: string) => void;
  intervalMs?: number;
}

export interface RunAutoPollingState {
  isImporting: boolean;
  importFailed: boolean;
  retryImport: () => Promise<void>;
}

/**
 * Poll `getRun(runId)` while the run is in a non-terminal state and fire
 * `importRun(runId)` exactly once when it transitions into `completed`
 * without an existing imported ResumeVersion.
 *
 * Polling stops on terminal states (`imported`, `failed`) and on unmount.
 * The auto-import is single-shot per run: a failure does NOT reset the
 * guard, which is what prevents repeated POST /import spam on every poll
 * tick. The caller can invoke `retryImport()` to re-attempt manually.
 */
export function useRunAutoPolling({
  runId,
  run,
  needsImport,
  onUpdate,
  onImported,
  onImportError,
  intervalMs = RUN_POLL_INTERVAL_MS,
}: RunAutoPollingArgs): RunAutoPollingState {
  const importTriggered = useRef(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importFailed, setImportFailed] = useState(false);
  const onUpdateRef = useRef(onUpdate);
  const onImportedRef = useRef(onImported);
  const onImportErrorRef = useRef(onImportError);

  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);
  useEffect(() => {
    onImportedRef.current = onImported;
  }, [onImported]);
  useEffect(() => {
    onImportErrorRef.current = onImportError;
  }, [onImportError]);

  // Reset the per-run guard if the runId changes (different run loaded).
  useEffect(() => {
    importTriggered.current = false;
    setImportFailed(false);
  }, [runId]);

  const runImport = useCallback(
    async (id: string) => {
      setIsImporting(true);
      try {
        const version = await importRun(id);
        setImportFailed(false);
        onImportedRef.current(version);
        const refreshed = await getRun(id).catch(() => null);
        if (refreshed) onUpdateRef.current(refreshed);
      } catch (err: unknown) {
        setImportFailed(true);
        onImportErrorRef.current(extractApiDetail(err));
      } finally {
        setIsImporting(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!runId || !run) return;
    if (!needsImport) return;
    if (importTriggered.current) return;
    importTriggered.current = true;
    void runImport(runId);
  }, [runId, run, needsImport, runImport]);

  const retryImport = useCallback(async () => {
    if (!runId) return;
    if (isImporting) return;
    importTriggered.current = true;
    setImportFailed(false);
    await runImport(runId);
  }, [runId, isImporting, runImport]);

  const polling =
    !!runId && !!run && (runIsActive(run.status) || needsImport);

  useEffect(() => {
    if (!polling || !runId) return;
    const id = setInterval(() => {
      getRun(runId)
        .then((r) => onUpdateRef.current(r))
        .catch(() => {});
    }, intervalMs);
    return () => clearInterval(id);
  }, [polling, runId, intervalMs]);

  return { isImporting, importFailed, retryImport };
}

interface RunLogPollingArgs {
  runId: string | null;
  active: boolean;
  intervalMs?: number;
}

export interface RunLogPollingState {
  /** Raw lines (post-sanitization order). May be empty until the worker
   *  writes the first milestone or while a non-existent log returns []. */
  lines: string[];
  /** True for one render after the very first response, regardless of
   *  whether it was empty — lets callers distinguish "loading" from "no
   *  activity yet". */
  hasLoadedOnce: boolean;
  truncated: boolean;
}

/**
 * Poll `GET /runs/{id}/log` while `active`. Polling is cheaper than the
 * run-row poll because the endpoint reads only the file tail, so we tick
 * faster (2s vs 5s) — the user wants the activity feed to feel live.
 *
 * Stops polling on `runIsTerminal(status)` so a final failed/imported
 * panel keeps its last lines without spamming the backend.
 */
export function useRunLogPolling({
  runId,
  active,
  intervalMs = RUN_LOG_POLL_INTERVAL_MS,
}: RunLogPollingArgs): RunLogPollingState {
  const [lines, setLines] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  // Reset when the run we're following changes.
  useEffect(() => {
    setLines([]);
    setTruncated(false);
    setHasLoadedOnce(false);
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    const tick = () => {
      getRunLog(runId)
        .then((res) => {
          if (cancelled) return;
          setLines(res.lines);
          setTruncated(res.truncated);
          setHasLoadedOnce(true);
        })
        .catch(() => {
          // Swallow polling errors — the activity panel is best-effort.
        });
    };
    tick();
    if (!active) return () => {
      cancelled = true;
    };
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [runId, active, intervalMs]);

  return { lines, hasLoadedOnce, truncated };
}

interface RunProgressPollingArgs {
  runId: string | null;
  active: boolean;
  intervalMs?: number;
}

export interface RunProgressPollingState {
  /** User-facing progress lines from ``progress/progress.log``. Empty until
   *  the worker writes its first event (or while a non-existent file
   *  returns []). These are the lines the default UI prefers. */
  lines: string[];
  hasLoadedOnce: boolean;
  truncated: boolean;
}

/**
 * Poll `GET /runs/{id}/progress` while `active`. Mirrors `useRunLogPolling`
 * but targets the user-facing progress feed, which is what the default
 * `Recent activity` panel displays.
 */
export function useRunProgressPolling({
  runId,
  active,
  intervalMs = RUN_PROGRESS_POLL_INTERVAL_MS,
}: RunProgressPollingArgs): RunProgressPollingState {
  const [lines, setLines] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  useEffect(() => {
    setLines([]);
    setTruncated(false);
    setHasLoadedOnce(false);
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    const tick = () => {
      getRunProgress(runId)
        .then((res) => {
          if (cancelled) return;
          setLines(res.lines);
          setTruncated(res.truncated);
          setHasLoadedOnce(true);
        })
        .catch(() => {
          // Best-effort polling: the activity panel falls back to logs if
          // this endpoint errors or is unreachable.
        });
    };
    tick();
    if (!active) return () => {
      cancelled = true;
    };
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [runId, active, intervalMs]);

  return { lines, hasLoadedOnce, truncated };
}

interface RunActivityPanelProps {
  /** Plain user-facing progress lines (from /progress). Preferred. */
  progressLines?: string[];
  /** Raw run.log lines (from /log) — used as fallback when no progress
   *  lines exist yet. Kept as the back-compat single source if
   *  `progressLines` is not supplied. */
  lines: string[];
  hasLoadedOnce: boolean;
  truncated?: boolean;
  maxLines?: number;
}

/**
 * Renders the "Recent activity" list shown on RunDetailPage and as part of
 * the in-progress card on JobDetailPage. Prefers user-facing progress
 * events (one bullet per phase) and only falls back to the technical
 * run.log stream when no progress events have been written yet.
 */
export function RunActivityPanel({
  progressLines,
  lines,
  hasLoadedOnce,
  truncated = false,
  maxLines = RUN_LOG_DEFAULT_DISPLAY_LINES,
}: RunActivityPanelProps) {
  const sanitizedProgress = (progressLines ?? [])
    .map((raw) => raw.replace(ANSI_ESCAPE_RE, "").trim())
    .filter((cleaned) => cleaned.length > 0);
  const cappedProgress =
    sanitizedProgress.length <= maxLines
      ? sanitizedProgress
      : sanitizedProgress.slice(sanitizedProgress.length - maxLines);
  const useProgress = cappedProgress.length > 0;
  const display = useProgress
    ? cappedProgress
    : sanitizeRunLogLines(lines, maxLines);
  if (!hasLoadedOnce) {
    return (
      <div className="run-activity" aria-live="polite">
        <p className="run-activity-empty">Loading recent activity…</p>
      </div>
    );
  }
  if (display.length === 0) {
    return (
      <div className="run-activity" aria-live="polite">
        <p className="run-activity-empty">
          Waiting for the tailoring agent to start…
        </p>
      </div>
    );
  }
  return (
    <div className="run-activity" aria-live="polite">
      <p className="run-activity-label">Recent activity</p>
      <ul className="run-activity-list">
        {display.map((line, idx) => (
          <li key={`${idx}:${line}`} className="run-activity-item">
            {line}
          </li>
        ))}
      </ul>
      {truncated ? (
        <p className="run-activity-truncated">
          Earlier log lines hidden — see Advanced details for the full log.
        </p>
      ) : null}
    </div>
  );
}

export function isMissingOutputsError(message: string | null): boolean {
  if (!message) return false;
  return message.toLowerCase().includes("expected output file missing");
}

function truncateHash(hash: string | null): string {
  if (!hash) return "—";
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
}

function formatTimestamp(value: string | null): string {
  const parsed = parseTimestamp(value);
  if (!parsed) return "—";
  return parsed.toLocaleString();
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<ClaudeRun | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [resumeVersions, setResumeVersions] = useState<ResumeVersion[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [isInvoking, setIsInvoking] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [recruiterReview, setRecruiterReview] =
    useState<RecruiterReview | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    Promise.all([getRun(runId), listResumeVersions()])
      .then(async ([r, versions]) => {
        if (cancelled) return;
        setRun(r);
        setResumeVersions(versions);
        const j = await getJob(r.job_id).catch(() => null);
        if (cancelled || !j) return;
        setJob(j);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Fetch the recruiter review whenever the run reaches a state where
  // output/recruiter_review.md may exist. The endpoint reports
  // available=false when the file has not been written, so we can
  // safely poll it on every status change without surfacing errors.
  useEffect(() => {
    if (!runId || !run) return;
    if (run.status !== "completed" && run.status !== "imported") return;
    let cancelled = false;
    getRunRecruiterReview(runId)
      .then((review) => {
        if (cancelled) return;
        setRecruiterReview(review);
      })
      .catch(() => {
        if (cancelled) return;
        setRecruiterReview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run]);

  const resumeVersion =
    resumeVersions?.find((v) => v.claude_run_id === runId) ?? null;
  const needsImport = run
    ? runNeedsImport(run, resumeVersions ?? [])
    : false;

  const { isImporting: isAutoImporting, importFailed, retryImport } =
    useRunAutoPolling({
      runId: runId ?? null,
      run,
      needsImport,
      onUpdate: setRun,
      onImported: (version) => {
        setResumeVersions((prev) => {
          if (!prev) return [version];
          const without = prev.filter((v) => v.id !== version.id);
          return [...without, version];
        });
      },
      onImportError: setImportError,
    });

  // Keep streaming the log while the run is still working through the
  // tailoring + import handshake. After it terminates we still load it
  // once on mount (the hook's initial tick) so the panel shows the final
  // recent activity.
  const logPollingActive = run ? !runIsTerminal(run.status) : false;
  const {
    lines: logLines,
    hasLoadedOnce: logHasLoadedOnce,
    truncated: logTruncated,
  } = useRunLogPolling({
    runId: runId ?? null,
    active: logPollingActive,
  });
  const {
    lines: progressLines,
    hasLoadedOnce: progressHasLoadedOnce,
    truncated: progressTruncated,
  } = useRunProgressPolling({
    runId: runId ?? null,
    active: logPollingActive,
  });
  // The panel is "loaded" once either feed has responded — the progress
  // endpoint is the preferred source but the technical log is a valid
  // fallback while the worker hasn't written any user-facing lines yet.
  const activityHasLoadedOnce = progressHasLoadedOnce || logHasLoadedOnce;
  const activityTruncated =
    progressLines.length > 0 ? progressTruncated : logTruncated;

  async function handleStartTailoring() {
    if (!runId || !run || run.status !== "created") return;
    setIsInvoking(true);
    setActionError(null);
    try {
      const updated = await invokeRun(runId);
      setRun(updated);
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsInvoking(false);
    }
  }

  async function handleRetryImport() {
    if (!runId || !run || run.status !== "completed") return;
    setIsImporting(true);
    setActionError(null);
    setImportError(null);
    try {
      const version = await importRun(runId);
      setResumeVersions((prev) => {
        if (!prev) return [version];
        const without = prev.filter((v) => v.id !== version.id);
        return [...without, version];
      });
      const refreshed = await getRun(runId);
      setRun(refreshed);
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsImporting(false);
    }
  }

  if (loadError) {
    return (
      <section className="run-detail">
        <h2>Resume tailoring run</h2>
        <p role="alert" className="error">
          {loadError}
        </p>
      </section>
    );
  }

  if (!run) {
    return (
      <section className="run-detail">
        <h2>Resume tailoring run</h2>
        <p>Loading…</p>
      </section>
    );
  }

  const badge = runStatusBadge(run.status);
  const heading = job
    ? `Resume tailoring run — ${job.title} — ${job.company}`
    : "Resume tailoring run";

  const statusDisplay =
    importFailed && run.status === "completed"
      ? "Draft could not be loaded"
      : resumeVersion
        ? "Draft ready to review"
        : runStatusLabel(run.status);

  const showSpinner =
    runIsActive(run.status) ||
    (run.status === "completed" && !resumeVersion && !importFailed) ||
    isAutoImporting;

  return (
    <section className="run-detail">
      <h2>
        {heading}
        <span className={`status-badge status-badge-${badge.variant}`}>
          {badge.label}
        </span>
      </h2>

      <div
        className="tailoring-progress"
        role="status"
        aria-live="polite"
      >
        {showSpinner ? (
          <span className="tailoring-spinner" aria-hidden="true" />
        ) : null}
        <span className="tailoring-progress-label">{statusDisplay}</span>
      </div>

      {run.status === "failed" && isMissingOutputsError(run.error_message) ? (
        <p className="tailoring-failure-explanation">
          The tailoring process finished without producing the required
          output files.
        </p>
      ) : null}

      <RunActivityPanel
        progressLines={progressLines}
        lines={logLines}
        hasLoadedOnce={activityHasLoadedOnce}
        truncated={activityTruncated}
      />

      <dl className="run-meta">
        <dt>Status</dt>
        <dd>{statusDisplay}</dd>
        <dt>Created</dt>
        <dd>{formatTimestamp(run.created_at)}</dd>
        <dt>Started</dt>
        <dd>{formatTimestamp(run.started_at)}</dd>
        <dt>Completed</dt>
        <dd>{formatTimestamp(run.completed_at)}</dd>
        {run.error_message ? (
          <>
            <dt>Error</dt>
            <dd className="error">{run.error_message}</dd>
          </>
        ) : null}
      </dl>

      {importError ? (
        <div className="import-failure">
          <p role="alert" className="error">
            The tailoring run finished, but the draft could not be loaded.
            <br />
            {importError}
          </p>
          <button
            type="button"
            onClick={() => {
              setImportError(null);
              void retryImport();
            }}
            disabled={isAutoImporting}
          >
            {isAutoImporting ? "Loading draft…" : "Retry loading draft"}
          </button>
        </div>
      ) : null}

      {resumeVersion ? (
        <p className="resume-version-link">
          Resume version:{" "}
          <Link to={`/resume-versions/${resumeVersion.id}`}>
            {resumeVersion.id}
          </Link>
          {" · "}
          <Link
            className="review-workspace-link"
            to={`/resume-versions/${resumeVersion.id}/review`}
          >
            Open review workspace
          </Link>
        </p>
      ) : null}

      {recruiterReview && recruiterReview.available ? (
        <details className="recruiter-review">
          <summary>Open recruiter review</summary>
          <pre className="job-description">{recruiterReview.content}</pre>
        </details>
      ) : recruiterReview && !recruiterReview.available ? (
        <p className="recruiter-review-missing">
          Recruiter review not produced for this run yet.
        </p>
      ) : null}

      <details className="advanced-details">
        <summary>Advanced details</summary>
        {progressLines.length > 0 ? (
          <>
            <p className="advanced-section-label">Technical run log</p>
            {logHasLoadedOnce && sanitizeRunLogLines(logLines).length > 0 ? (
              <ul className="run-activity-list run-activity-list-technical">
                {sanitizeRunLogLines(logLines).map((line, idx) => (
                  <li key={`${idx}:${line}`} className="run-activity-item">
                    {line}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="run-activity-empty">
                No technical log entries yet.
              </p>
            )}
            {logTruncated ? (
              <p className="run-activity-truncated">
                Earlier log lines were truncated.
              </p>
            ) : null}
          </>
        ) : null}
        <dl className="run-meta">
          <dt>Run id</dt>
          <dd>
            <code>{run.id}</code>
          </dd>
          <dt>Run directory</dt>
          <dd>
            <code>{run.run_dir}</code>
          </dd>
          <dt>Raw status</dt>
          <dd>
            <code>{run.status}</code>
          </dd>
          <dt>Prompt hash</dt>
          <dd>
            <code>{truncateHash(run.prompt_hash)}</code>
          </dd>
          <dt>Input hash</dt>
          <dd>
            <code>{truncateHash(run.input_hash)}</code>
          </dd>
          <dt>Output hash</dt>
          <dd>
            <code>{truncateHash(run.output_hash)}</code>
          </dd>
        </dl>
        <div className="run-actions advanced-run-actions">
          <button
            type="button"
            onClick={handleStartTailoring}
            disabled={run.status !== "created" || isInvoking}
          >
            {isInvoking ? "Starting…" : "Start tailoring"}
          </button>
          <button
            type="button"
            onClick={handleRetryImport}
            disabled={run.status !== "completed" || isImporting}
          >
            {isImporting ? "Importing…" : "Retry import"}
          </button>
        </div>
        {actionError ? (
          <p role="alert" className="error">
            {actionError}
          </p>
        ) : null}
      </details>
    </section>
  );
}
