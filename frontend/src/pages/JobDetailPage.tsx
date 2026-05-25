import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createApplication,
  createRun,
  createWordHandoff,
  getJob,
  getLlmProviderSetting,
  getWordHandoffInstructions,
  getWordHandoffPrompt,
  importWordResult,
  invokeRun,
  listApplications,
  listEvidenceBanks,
  listMasterResumes,
  listResumeVersions,
  listRevisionFeedbacks,
  listRuns,
} from "../api";
import type {
  Application,
  ClaudeRun,
  EvidenceBank,
  Job,
  LlmProvider,
  MasterResume,
  ResumeVersion,
  RevisionFeedback,
  WordHandoffMetadata,
  WordResultImportResponse,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";
import {
  draftLabel,
  draftStatusLabel,
  formatElapsedSince,
  parseTimestamp,
  runIsActive,
  runNeedsImport,
  runStartTimestamp,
} from "../lib/workflow";
import {
  RunActivityPanel,
  runIsTerminal,
  useRunAutoPolling,
  useRunLogPolling,
  useRunProgressPolling,
} from "./RunDetailPage";

const STEP_TITLES = [
  "Read the job description",
  "Choose resume source",
  "Generate a draft",
  "Review and approve drafts",
  "Send your application",
] as const;

function formatTimestamp(value: string | null): string {
  const parsed = parseTimestamp(value);
  if (!parsed) return "—";
  return parsed.toLocaleString();
}

function WorkspaceStep({
  index,
  title,
  children,
}: {
  index: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      className="workspace-step"
      aria-label={`Step ${index}: ${title}`}
    >
      <header className="workspace-step-header">
        <span className="workspace-step-index" aria-hidden="true">
          {index}
        </span>
        <h3 className="workspace-step-title">{title}</h3>
      </header>
      <div className="workspace-step-body">{children}</div>
    </section>
  );
}

const EXPECTED_WORD_OUTPUT_DISPLAY = "output/word_tailored_resume.docx";

function WordHandoffPanel({
  handoff,
  copyState,
  onCopyPrompt,
  onImport,
  importing,
  importResult,
  importError,
}: {
  handoff: {
    runId: string;
    metadata: WordHandoffMetadata;
    promptText: string;
    instructionsText: string;
  };
  copyState: "idle" | "copied";
  onCopyPrompt: () => void;
  onImport: () => void;
  importing: boolean;
  importResult: WordResultImportResponse | null;
  importError: string | null;
}) {
  const sourceMissing = handoff.metadata.resume_docx === null;
  const isWaiting =
    importResult !== null && importResult.status !== "completed";
  const isImported =
    importResult !== null && importResult.status === "completed";
  return (
    <section
      className="word-handoff-panel"
      aria-label="Claude for Word handoff"
    >
      <h4>Claude for Word handoff prepared</h4>
      <ol className="word-handoff-steps">
        <li>Open the prepared DOCX in Word</li>
        <li>Open Claude for Word</li>
        <li>Paste the generated prompt</li>
        <li>
          Save as <code>{EXPECTED_WORD_OUTPUT_DISPLAY}</code>
        </li>
        <li>Click Import Word Result</li>
      </ol>
      {sourceMissing ? (
        <p role="alert" className="word-handoff-warning">
          No source DOCX was found in this run's input. The prompt and
          instructions are still available below, but you will need to open
          your master resume DOCX in Word manually.
        </p>
      ) : null}
      <p className="word-handoff-save-path">
        Expected save path:{" "}
        <code>{EXPECTED_WORD_OUTPUT_DISPLAY}</code>
      </p>
      <div className="word-handoff-prompt">
        <div className="word-handoff-prompt-header">
          <h5>Prompt</h5>
          <button
            type="button"
            onClick={onCopyPrompt}
            aria-label="Copy prompt"
          >
            {copyState === "copied" ? "Copied" : "Copy prompt"}
          </button>
        </div>
        <textarea
          className="word-handoff-prompt-text"
          aria-label="Claude for Word prompt"
          value={handoff.promptText}
          readOnly
          rows={8}
        />
      </div>
      <div className="word-handoff-instructions">
        <h5>Instructions</h5>
        <pre className="word-handoff-instructions-text">
          {handoff.instructionsText}
        </pre>
      </div>
      <div className="word-handoff-import">
        <button
          type="button"
          onClick={onImport}
          disabled={importing}
        >
          {importing ? "Importing…" : "Import Word Result"}
        </button>
        {importError ? (
          <p role="alert" className="error">
            {importError}
          </p>
        ) : null}
        {isWaiting ? (
          <p role="status" className="word-handoff-waiting">
            Waiting for Word result. Save the completed document as{" "}
            <code>{EXPECTED_WORD_OUTPUT_DISPLAY}</code>, then click Import
            again.
          </p>
        ) : null}
        {isImported ? (
          <p role="status" className="word-handoff-success">
            Imported. Final resume available at{" "}
            <code>{importResult?.final_resume ?? "output/final_resume.docx"}</code>
            .
          </p>
        ) : null}
      </div>
    </section>
  );
}

export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [resumes, setResumes] = useState<MasterResume[] | null>(null);
  const [evidenceBanks, setEvidenceBanks] = useState<EvidenceBank[] | null>(
    null,
  );
  const [resumeVersions, setResumeVersions] = useState<ResumeVersion[] | null>(
    null,
  );
  const [runs, setRuns] = useState<ClaudeRun[] | null>(null);
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [revisionFeedbacks, setRevisionFeedbacks] = useState<
    RevisionFeedback[]
  >([]);
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const trackedRunIdRef = useRef<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applyingVersionId, setApplyingVersionId] = useState<string | null>(
    null,
  );
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [wordHandoff, setWordHandoff] = useState<{
    runId: string;
    metadata: WordHandoffMetadata;
    promptText: string;
    instructionsText: string;
  } | null>(null);
  const [isPreparingWordHandoff, setIsPreparingWordHandoff] = useState(false);
  const [wordHandoffError, setWordHandoffError] = useState<string | null>(null);
  const [isImportingWordResult, setIsImportingWordResult] = useState(false);
  const [wordImportResult, setWordImportResult] =
    useState<WordResultImportResponse | null>(null);
  const [wordImportError, setWordImportError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied">("idle");
  const [llmProviders, setLlmProviders] = useState<LlmProvider[] | null>(null);
  const [defaultProviderId, setDefaultProviderId] = useState<string>("");
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    Promise.all([
      getJob(jobId),
      listMasterResumes(),
      listEvidenceBanks(),
      listResumeVersions(),
      listRuns(),
      listApplications(),
    ])
      .then(([j, r, e, v, runRows, appRows]) => {
        if (cancelled) return;
        setJob(j);
        setResumes(r);
        setEvidenceBanks(e);
        setResumeVersions(v.filter((version) => version.job_id === jobId));
        setRuns(runRows.filter((run) => run.job_id === jobId));
        setApplications(appRows.filter((app) => app.job_id === jobId));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(extractApiDetail(err));
      });
    listRevisionFeedbacks()
      .then((rows) => {
        if (cancelled) return;
        setRevisionFeedbacks(rows.filter((rf) => rf.job_id === jobId));
      })
      .catch(() => {
        if (cancelled) return;
        setRevisionFeedbacks([]);
      });
    // Wrapped in try/catch because some legacy JobDetailPage test mocks omit
    // this export from `../api`; vitest throws at call-time in that case.
    // A failure here just disables the selector — generation still works
    // and falls back to the backend's persisted default.
    try {
      getLlmProviderSetting()
        .then((data) => {
          if (cancelled) return;
          setLlmProviders(data.available);
          setDefaultProviderId(data.default_provider);
          setSelectedProviderId(data.default_provider);
        })
        .catch(() => {
          if (cancelled) return;
          setLlmProviders([]);
        });
    } catch {
      setLlmProviders([]);
    }
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function handleCreateApplication(versionId: string) {
    if (!jobId) return;
    setApplyingVersionId(versionId);
    setApplyError(null);
    try {
      const application = await createApplication({
        job_id: jobId,
        resume_version_id: versionId,
        status: "approved",
      });
      navigate(`/applications/${application.id}`);
    } catch (err: unknown) {
      setApplyError(extractApiDetail(err));
    } finally {
      setApplyingVersionId(null);
    }
  }

  async function handleGenerate() {
    if (!jobId) return;
    if (!selectedResumeId) {
      setGenerateError("Pick a master resume before generating a draft.");
      return;
    }
    setIsGenerating(true);
    setGenerateError(null);
    setImportError(null);
    try {
      const payload: Parameters<typeof createRun>[0] = {
        job_id: jobId,
        master_resume_id: selectedResumeId,
        evidence_bank_id: selectedBankId || null,
      };
      if (
        selectedProviderId &&
        selectedProviderId !== defaultProviderId
      ) {
        payload.llm_provider = selectedProviderId;
      }
      const run = await createRun(payload);
      // Insert the new run immediately so the workspace flips into its
      // "tailoring in progress" state without waiting on the invoke
      // round-trip. The poller takes over from here.
      setRuns((prev) => (prev ? [...prev, run] : [run]));
      const invoked = await invokeRun(run.id);
      setRuns((prev) => {
        if (!prev) return [invoked];
        const without = prev.filter((r) => r.id !== invoked.id);
        return [...without, invoked];
      });
    } catch (err: unknown) {
      setGenerateError(extractApiDetail(err));
    } finally {
      setIsGenerating(false);
    }
  }

  async function handlePrepareWordHandoff() {
    if (!jobId) return;
    if (!selectedResumeId) {
      setWordHandoffError(
        "Pick a master resume before preparing the Word handoff.",
      );
      return;
    }
    setIsPreparingWordHandoff(true);
    setWordHandoffError(null);
    setWordImportError(null);
    setWordImportResult(null);
    try {
      const run = await createRun({
        job_id: jobId,
        master_resume_id: selectedResumeId,
        evidence_bank_id: selectedBankId || null,
      });
      setRuns((prev) => (prev ? [...prev, run] : [run]));
      const metadata = await createWordHandoff(run.id);
      const [prompt, instructions] = await Promise.all([
        getWordHandoffPrompt(run.id),
        getWordHandoffInstructions(run.id),
      ]);
      setWordHandoff({
        runId: run.id,
        metadata,
        promptText: prompt.content,
        instructionsText: instructions.content,
      });
    } catch (err: unknown) {
      setWordHandoffError(extractApiDetail(err));
    } finally {
      setIsPreparingWordHandoff(false);
    }
  }

  async function handleImportWordResult() {
    if (!wordHandoff) return;
    setIsImportingWordResult(true);
    setWordImportError(null);
    try {
      const response = await importWordResult(wordHandoff.runId);
      setWordImportResult(response);
    } catch (err: unknown) {
      setWordImportError(extractApiDetail(err));
    } finally {
      setIsImportingWordResult(false);
    }
  }

  async function handleCopyPrompt() {
    if (!wordHandoff) return;
    try {
      await navigator.clipboard.writeText(wordHandoff.promptText);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1500);
    } catch {
      // Clipboard may be unavailable (e.g. insecure context); the prompt
      // textarea is still visible and selectable so the user has a fallback.
    }
  }

  const orderedDrafts = useMemo(() => {
    if (!resumeVersions) return [];
    return [...resumeVersions].sort((a, b) =>
      a.created_at.localeCompare(b.created_at),
    );
  }, [resumeVersions]);

  const revisionFollowupRunToSource = useMemo(() => {
    const map = new Map<string, string>();
    for (const rf of revisionFeedbacks) {
      if (rf.followup_claude_run_id) {
        map.set(rf.followup_claude_run_id, rf.source_resume_version_id);
      }
    }
    return map;
  }, [revisionFeedbacks]);

  const revisesLabelForDraft = useMemo(() => {
    const labels = new Map<string, string>();
    for (const draft of orderedDrafts) {
      if (!draft.claude_run_id) continue;
      const sourceId = revisionFollowupRunToSource.get(draft.claude_run_id);
      if (!sourceId) continue;
      const sourceIndex = orderedDrafts.findIndex((d) => d.id === sourceId);
      if (sourceIndex < 0) continue;
      labels.set(draft.id, `revises ${draftLabel(sourceIndex)}`);
    }
    return labels;
  }, [orderedDrafts, revisionFollowupRunToSource]);

  const latestRun = useMemo(() => {
    if (!runs || runs.length === 0) return null;
    return [...runs].sort((a, b) =>
      b.created_at.localeCompare(a.created_at),
    )[0];
  }, [runs]);

  const latestRunNeedsImportForPoll =
    latestRun && resumeVersions
      ? runNeedsImport(latestRun, resumeVersions)
      : false;

  const handleRunUpdate = useCallback((updated: ClaudeRun) => {
    setRuns((prev) => {
      if (!prev) return prev;
      const without = prev.filter((r) => r.id !== updated.id);
      return [...without, updated];
    });
  }, []);

  const handleVersionImported = useCallback(
    (version: ResumeVersion) => {
      setResumeVersions((prev) => {
        if (!prev) return [version];
        const without = prev.filter((v) => v.id !== version.id);
        return [...without, version];
      });
      // Re-fetch in the background so the drafts list reflects any other
      // versions written since the page loaded (e.g. a sibling run that
      // finished concurrently). Best-effort: if the request fails, the
      // inline insert above keeps the new draft visible.
      if (!jobId) return;
      void listResumeVersions()
        .then((rows) => {
          setResumeVersions(rows.filter((v) => v.job_id === jobId));
        })
        .catch(() => {});
    },
    [jobId],
  );

  const handleImportError = useCallback((message: string) => {
    setImportError(message);
  }, []);

  const { isImporting, importFailed, retryImport } = useRunAutoPolling({
    runId: latestRun?.id ?? null,
    run: latestRun,
    needsImport: latestRunNeedsImportForPoll,
    onUpdate: handleRunUpdate,
    onImported: handleVersionImported,
    onImportError: handleImportError,
  });

  // Live recent-activity feed for the most-recent run. Active until the run
  // reaches a terminal state; the final lines stay visible after failure or
  // import so the user sees what happened.
  const logPollingActive = latestRun
    ? !runIsTerminal(latestRun.status)
    : false;
  const {
    lines: latestRunLogLines,
    hasLoadedOnce: latestRunLogLoaded,
    truncated: latestRunLogTruncated,
  } = useRunLogPolling({
    runId: latestRun?.id ?? null,
    active: logPollingActive,
  });
  const {
    lines: latestRunProgressLines,
    hasLoadedOnce: latestRunProgressLoaded,
    truncated: latestRunProgressTruncated,
  } = useRunProgressPolling({
    runId: latestRun?.id ?? null,
    active: logPollingActive,
  });
  const activityHasLoadedOnce =
    latestRunProgressLoaded || latestRunLogLoaded;
  const activityTruncated =
    latestRunProgressLines.length > 0
      ? latestRunProgressTruncated
      : latestRunLogTruncated;

  // Reset import error when the user starts a new run.
  useEffect(() => {
    const id = latestRun?.id ?? null;
    if (id !== trackedRunIdRef.current) {
      trackedRunIdRef.current = id;
      setImportError(null);
    }
  }, [latestRun?.id]);

  // Tick the elapsed-time display while a run is active.
  const runActiveForTick =
    !!latestRun &&
    (runIsActive(latestRun.status) ||
      (latestRun.status === "completed" &&
        resumeVersions !== null &&
        runNeedsImport(latestRun, resumeVersions) &&
        !importFailed));
  useEffect(() => {
    if (!runActiveForTick) return;
    const id = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(id);
  }, [runActiveForTick]);

  if (loadError) {
    return (
      <section className="job-detail">
        <h2>Job</h2>
        <p role="alert" className="error">
          {loadError}
        </p>
      </section>
    );
  }

  if (
    !job ||
    !resumes ||
    !evidenceBanks ||
    !resumeVersions ||
    !runs ||
    !applications
  ) {
    return (
      <section className="job-detail">
        <h2>Job</h2>
        <p>Loading…</p>
      </section>
    );
  }

  const hasSubmittedApplication = applications.some(
    (a) => a.status === "submitted",
  );
  const submittedApplication = applications.find(
    (a) => a.status === "submitted",
  );
  const approvedDrafts = orderedDrafts.filter((v) => v.approved_at !== null);
  const hasPriorRuns = runs.length > 0;
  const latestRunVersion = latestRun
    ? resumeVersions.find((v) => v.claude_run_id === latestRun.id) ?? null
    : null;
  const latestRunNeedsImport = latestRun
    ? runNeedsImport(latestRun, resumeVersions)
    : false;
  const latestRunActive = latestRun
    ? runIsActive(latestRun.status) || latestRunNeedsImport
    : false;
  // Step-3 progress copy — must match the task's wording.
  let progressCopy: { title: string; detail: string | null } | null = null;
  let progressTone: "running" | "loading" | "ready" | "failed" | null = null;
  if (latestRun) {
    if (latestRun.status === "failed") {
      progressCopy = {
        title: "Tailoring failed",
        detail: latestRun.error_message ?? null,
      };
      progressTone = "failed";
    } else if (importFailed && importError) {
      progressCopy = {
        title:
          "The tailoring run finished, but the draft could not be loaded.",
        detail: importError,
      };
      progressTone = "failed";
    } else if (latestRunVersion || latestRun.status === "imported") {
      progressCopy = { title: "Draft ready to review.", detail: null };
      progressTone = "ready";
    } else if (latestRun.status === "completed") {
      progressCopy = {
        title: "Tailoring finished. Loading the generated draft…",
        detail: null,
      };
      progressTone = "loading";
    } else {
      progressCopy = {
        title: "Tailoring in progress…",
        detail:
          "The app is generating a draft using your selected resume and evidence bank. This can take a little while.",
      };
      progressTone = "running";
    }
  }

  const elapsedLabel = latestRun && latestRunActive
    ? formatElapsedSince(runStartTimestamp(latestRun), new Date(nowTick))
    : null;

  const latestRunProviderName = latestRun?.llm_provider && llmProviders
    ? (llmProviders.find((p) => p.id === latestRun.llm_provider)?.display_name
        ?? latestRun.llm_provider)
    : null;

  return (
    <section className="job-detail">
      <h2>
        {job.title} — {job.company}
      </h2>
      {job.location ? <p className="job-meta">{job.location}</p> : null}
      {job.external_url ? (
        <p className="job-meta">
          <a href={job.external_url} target="_blank" rel="noreferrer">
            {job.external_url}
          </a>
        </p>
      ) : null}

      <ol className="workspace-steps" aria-label="Job workspace">
        <li>
          <WorkspaceStep index={1} title={STEP_TITLES[0]}>
            <p className="workspace-step-help">
              Confirm the role before tailoring a draft.
            </p>
            <button
              type="button"
              className="workspace-description-toggle"
              aria-expanded={descriptionOpen}
              aria-controls="job-description-body"
              onClick={() => setDescriptionOpen((open) => !open)}
            >
              {descriptionOpen ? "Hide job description" : "Read job description"}
            </button>
            {descriptionOpen ? (
              <pre
                id="job-description-body"
                className="job-description"
              >
                {job.description_text}
              </pre>
            ) : null}
          </WorkspaceStep>
        </li>

        <li>
          <WorkspaceStep index={2} title={STEP_TITLES[1]}>
            {resumes.length === 0 ? (
              <p className="settings-empty">
                No master resumes yet —{" "}
                <Link to="/settings">add one in Settings</Link> to enable
                tailoring.
              </p>
            ) : (
              <label className="field">
                <span>Master resume</span>
                <select
                  value={selectedResumeId}
                  onChange={(e) => setSelectedResumeId(e.target.value)}
                >
                  <option value="">Select a master resume…</option>
                  {resumes.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {evidenceBanks.length === 0 ? (
              <p className="workspace-step-help">
                No evidence banks yet — optional, but useful for grounded
                tailoring. <Link to="/settings">Add one in Settings.</Link>
              </p>
            ) : (
              <label className="field">
                <span>Evidence bank (optional)</span>
                <select
                  value={selectedBankId}
                  onChange={(e) => setSelectedBankId(e.target.value)}
                >
                  <option value="">No evidence bank</option>
                  {evidenceBanks.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </WorkspaceStep>
        </li>

        <li>
          <WorkspaceStep index={3} title={STEP_TITLES[2]}>
            <p className="workspace-step-help">
              Generate a tailored draft from the resume source above.
            </p>
            {latestRun && progressCopy && progressTone ? (
              <div
                className={`tailoring-progress tailoring-progress-${progressTone}`}
                role="status"
                aria-live="polite"
              >
                <div className="tailoring-progress-header">
                  {progressTone === "running" || progressTone === "loading" ? (
                    <span
                      className="tailoring-spinner"
                      aria-hidden="true"
                    />
                  ) : null}
                  <Link
                    to={`/runs/${latestRun.id}`}
                    className="tailoring-progress-title"
                  >
                    {progressCopy.title}
                  </Link>
                </div>
                {progressCopy.detail ? (
                  <p className="tailoring-progress-detail">
                    {progressCopy.detail}
                  </p>
                ) : null}
                <p className="tailoring-progress-meta">
                  Started {formatTimestamp(latestRun.created_at)}
                  {elapsedLabel ? (
                    <>
                      {" "}
                      · {elapsedLabel === "just now" ||
                        elapsedLabel === "elapsed time unavailable"
                        ? elapsedLabel
                        : `${elapsedLabel} elapsed`}
                    </>
                  ) : null}
                  {latestRunProviderName ? (
                    <>
                      {" "}
                      · Using {latestRunProviderName}
                    </>
                  ) : null}
                </p>
                {importFailed && importError ? (
                  <button
                    type="button"
                    onClick={() => {
                      setImportError(null);
                      void retryImport();
                    }}
                    disabled={isImporting}
                    className="tailoring-progress-retry"
                  >
                    {isImporting
                      ? "Loading draft…"
                      : "Retry loading draft"}
                  </button>
                ) : null}
                <RunActivityPanel
                  progressLines={latestRunProgressLines}
                  lines={latestRunLogLines}
                  hasLoadedOnce={activityHasLoadedOnce}
                  truncated={activityTruncated}
                />
              </div>
            ) : null}
            <div className="tailoring-method-actions">
              <button
                type="button"
                onClick={handleGenerate}
                disabled={isGenerating || resumes.length === 0}
              >
                {isGenerating
                  ? "Generating…"
                  : hasPriorRuns
                    ? "Generate another draft automatically"
                    : "Generate Automatically"}
              </button>
              {llmProviders && llmProviders.length > 0 ? (
                <label
                  className="tailoring-provider-select"
                  aria-label="LLM provider for this run"
                >
                  <span className="tailoring-provider-select-label">LLM</span>
                  <select
                    aria-label="LLM provider"
                    value={selectedProviderId}
                    onChange={(e) =>
                      setSelectedProviderId(e.target.value)
                    }
                    disabled={isGenerating}
                  >
                    {llmProviders.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                type="button"
                className="tailoring-method-secondary"
                onClick={handlePrepareWordHandoff}
                disabled={
                  isPreparingWordHandoff || resumes.length === 0
                }
              >
                {isPreparingWordHandoff
                  ? "Preparing…"
                  : "Prepare for Claude for Word"}
              </button>
            </div>
            {generateError ? (
              <p role="alert" className="error">
                {generateError}
              </p>
            ) : null}
            {wordHandoffError ? (
              <p role="alert" className="error">
                {wordHandoffError}
              </p>
            ) : null}
            {wordHandoff ? (
              <WordHandoffPanel
                handoff={wordHandoff}
                copyState={copyState}
                onCopyPrompt={handleCopyPrompt}
                onImport={handleImportWordResult}
                importing={isImportingWordResult}
                importResult={wordImportResult}
                importError={wordImportError}
              />
            ) : null}
          </WorkspaceStep>
        </li>

        <li>
          <WorkspaceStep index={4} title={STEP_TITLES[3]}>
            {orderedDrafts.length === 0 ? (
              <p className="settings-empty">
                No drafts yet — generate one in step 3.
              </p>
            ) : (
              <ul className="resume-version-list">
                {orderedDrafts.map((v, index) => {
                  const revisesLabel = revisesLabelForDraft.get(v.id);
                  return (
                    <li key={v.id} className="resume-version-list-item">
                      <span className="resume-version-draft-label">
                        <Link to={`/resume-versions/${v.id}`}>
                          {draftLabel(index)}
                        </Link>
                        {revisesLabel ? (
                          <span className="resume-version-revises">
                            {revisesLabel}
                          </span>
                        ) : null}
                      </span>
                      <span className="resume-version-status">
                        {draftStatusLabel(v.approved_at)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </WorkspaceStep>
        </li>

        <li>
          <WorkspaceStep index={5} title={STEP_TITLES[4]}>
            {hasSubmittedApplication ? (
              <p className="workspace-step-status">
                Sent
                {submittedApplication?.submitted_at
                  ? ` on ${formatTimestamp(submittedApplication.submitted_at)}`
                  : null}
                .
              </p>
            ) : approvedDrafts.length === 0 ? (
              <p className="application-gating">
                Pick an approved draft on the job page first.
              </p>
            ) : (
              <ul className="resume-version-list">
                {approvedDrafts.map((v) => {
                  const index = orderedDrafts.findIndex((d) => d.id === v.id);
                  return (
                    <li key={v.id} className="resume-version-list-item">
                      <span>
                        {draftLabel(index)}{" "}
                        <span className="resume-version-status">
                          (Approved — ready to send)
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() => handleCreateApplication(v.id)}
                        disabled={applyingVersionId !== null}
                      >
                        {applyingVersionId === v.id
                          ? "Starting…"
                          : "Start application"}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            {applyError ? (
              <p role="alert" className="error">
                {applyError}
              </p>
            ) : null}
            {applications.length > 0 ? (
              <ul className="application-list workspace-application-list">
                {applications.map((app) => (
                  <li key={app.id} className="application-list-item">
                    <Link to={`/applications/${app.id}`}>
                      Application opened {formatTimestamp(app.created_at)}
                    </Link>
                    {app.status === "submitted" ? (
                      <span className="application-meta">
                        {" "}
                        · Sent {formatTimestamp(app.submitted_at)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </WorkspaceStep>
        </li>
      </ol>
    </section>
  );
}
