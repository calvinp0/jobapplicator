import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  createApplication,
  createRun,
  getJob,
  invokeRun,
  listApplications,
  listEvidenceBanks,
  listMasterResumes,
  listResumeVersions,
  listRuns,
} from "../api";
import type {
  Application,
  ClaudeRun,
  EvidenceBank,
  Job,
  MasterResume,
  ResumeVersion,
} from "../api";
import { extractApiDetail } from "../lib/api-errors";
import {
  draftLabel,
  draftStatusLabel,
  runIsActive,
  runNeedsImport,
  runStatusLabel,
} from "../lib/workflow";
import { useRunAutoPolling } from "./RunDetailPage";

const STEP_TITLES = [
  "Read the job description",
  "Choose resume source",
  "Generate a draft",
  "Review and approve drafts",
  "Send your application",
] as const;

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
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
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applyingVersionId, setApplyingVersionId] = useState<string | null>(
    null,
  );
  const [descriptionOpen, setDescriptionOpen] = useState(false);

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
    try {
      const run = await createRun({
        job_id: jobId,
        master_resume_id: selectedResumeId,
        evidence_bank_id: selectedBankId || null,
      });
      await invokeRun(run.id);
      navigate(`/runs/${run.id}`);
    } catch (err: unknown) {
      setGenerateError(extractApiDetail(err));
    } finally {
      setIsGenerating(false);
    }
  }

  const orderedDrafts = useMemo(() => {
    if (!resumeVersions) return [];
    return [...resumeVersions].sort((a, b) =>
      a.created_at.localeCompare(b.created_at),
    );
  }, [resumeVersions]);

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

  const handleVersionImported = useCallback((version: ResumeVersion) => {
    setResumeVersions((prev) => {
      if (!prev) return [version];
      const without = prev.filter((v) => v.id !== version.id);
      return [...without, version];
    });
  }, []);

  const handleImportError = useCallback((message: string) => {
    setGenerateError(message);
  }, []);

  useRunAutoPolling({
    runId: latestRun?.id ?? null,
    run: latestRun,
    needsImport: latestRunNeedsImportForPoll,
    onUpdate: handleRunUpdate,
    onImported: handleVersionImported,
    onImportError: handleImportError,
  });

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
  const latestRunNeedsImport = latestRun
    ? runNeedsImport(latestRun, resumeVersions)
    : false;
  const latestRunActive = latestRun
    ? runIsActive(latestRun.status) || latestRunNeedsImport
    : false;
  const latestRunDraftReady =
    !!latestRun &&
    (latestRunNeedsImport || latestRun.status === "imported");
  const latestRunStatusText = latestRun
    ? latestRunDraftReady
      ? "Draft ready to review"
      : runStatusLabel(latestRun.status)
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
            {latestRun && latestRunStatusText ? (
              <p className="workspace-run-status">
                Latest tailoring:{" "}
                <Link to={`/runs/${latestRun.id}`}>{latestRunStatusText}</Link>
                {latestRunActive ? null : (
                  <span className="workspace-run-meta">
                    {" "}
                    · started {formatTimestamp(latestRun.created_at)}
                  </span>
                )}
              </p>
            ) : null}
            <button
              type="button"
              onClick={handleGenerate}
              disabled={isGenerating || resumes.length === 0}
            >
              {isGenerating
                ? "Generating…"
                : hasPriorRuns
                  ? "Generate another draft"
                  : "Generate draft"}
            </button>
            {generateError ? (
              <p role="alert" className="error">
                {generateError}
              </p>
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
                {orderedDrafts.map((v, index) => (
                  <li key={v.id} className="resume-version-list-item">
                    <Link to={`/resume-versions/${v.id}`}>
                      {draftLabel(index)}
                    </Link>
                    <span className="resume-version-status">
                      {draftStatusLabel(v.approved_at)}
                    </span>
                  </li>
                ))}
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
