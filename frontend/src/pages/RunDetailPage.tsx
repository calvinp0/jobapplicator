import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getJob,
  getRun,
  importRun,
  invokeRun,
  listResumeVersions,
} from "../api";
import type { ClaudeRun, Job, ResumeVersion } from "../api";
import { extractApiDetail } from "../lib/api-errors";
import { runIsActive, runNeedsImport, runStatusLabel } from "../lib/workflow";

export const RUN_POLL_INTERVAL_MS = 5000;

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

/**
 * Poll `getRun(runId)` while the run is in a non-terminal state and fire
 * `importRun(runId)` exactly once when it transitions into `completed`
 * without an existing imported ResumeVersion.
 *
 * Polling stops on terminal states (`imported`, `failed`) and on unmount.
 * If `importRun` fails the callback receives a parsed message and the
 * one-shot guard is reset so a manual retry can succeed.
 */
export function useRunAutoPolling({
  runId,
  run,
  needsImport,
  onUpdate,
  onImported,
  onImportError,
  intervalMs = RUN_POLL_INTERVAL_MS,
}: RunAutoPollingArgs) {
  const importTriggered = useRef(false);
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

  useEffect(() => {
    if (!runId || !run) return;
    if (!needsImport) return;
    if (importTriggered.current) return;
    importTriggered.current = true;
    importRun(runId)
      .then(async (version) => {
        onImportedRef.current(version);
        const refreshed = await getRun(runId).catch(() => null);
        if (refreshed) onUpdateRef.current(refreshed);
      })
      .catch((err: unknown) => {
        importTriggered.current = false;
        onImportErrorRef.current(extractApiDetail(err));
      });
  }, [runId, run, needsImport]);

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
}

function truncateHash(hash: string | null): string {
  if (!hash) return "—";
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
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

  const resumeVersion =
    resumeVersions?.find((v) => v.claude_run_id === runId) ?? null;
  const needsImport = run
    ? runNeedsImport(run, resumeVersions ?? [])
    : false;

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

  return (
    <section className="run-detail">
      <h2>
        {heading}
        <span className={`status-badge status-badge-${badge.variant}`}>
          {badge.label}
        </span>
      </h2>
      <dl className="run-meta">
        <dt>Status</dt>
        <dd>{runStatusLabel(run.status)}</dd>
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
        <p role="alert" className="error">
          {importError}
        </p>
      ) : null}

      {resumeVersion ? (
        <p className="resume-version-link">
          Resume version:{" "}
          <Link to={`/resume-versions/${resumeVersion.id}`}>
            {resumeVersion.id}
          </Link>
        </p>
      ) : null}

      <details className="advanced-details">
        <summary>Advanced details</summary>
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
