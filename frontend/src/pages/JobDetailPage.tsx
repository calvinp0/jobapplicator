import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  createApplication,
  createRun,
  getJob,
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

const STAGES = ["Captured", "Tailoring", "Approved", "Submitted"] as const;
type Stage = (typeof STAGES)[number];

const IN_FLIGHT_RUN_STATUSES = new Set([
  "created",
  "running",
  "completed-not-imported",
]);

function computeStage(
  runs: ClaudeRun[],
  versions: ResumeVersion[],
  applications: Application[],
): Stage {
  if (applications.some((a) => a.status === "submitted")) return "Submitted";
  if (versions.some((v) => v.approved_at)) return "Approved";
  if (runs.length > 0) return "Tailoring";
  return "Captured";
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
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
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applyingVersionId, setApplyingVersionId] = useState<string | null>(
    null,
  );

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
        const message =
          err instanceof ApiError ? err.message : "Failed to load job";
        setLoadError(message);
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
      const message =
        err instanceof ApiError ? err.message : "Failed to create application";
      setApplyError(message);
    } finally {
      setApplyingVersionId(null);
    }
  }

  async function handleGenerate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!jobId) return;
    if (!selectedResumeId) {
      setSubmitError("Pick a master resume before generating.");
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const run = await createRun({
        job_id: jobId,
        master_resume_id: selectedResumeId,
        evidence_bank_id: selectedBankId || null,
      });
      navigate(`/runs/${run.id}`);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to create run";
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

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

  const stage = computeStage(runs, resumeVersions, applications);
  const inFlightRuns = runs.filter((r) => IN_FLIGHT_RUN_STATUSES.has(r.status));
  const hasSubmittedApplication = applications.some(
    (a) => a.status === "submitted",
  );

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

      <ol
        className="job-status-track"
        aria-label="Job status"
        data-testid="job-status-track"
      >
        {STAGES.map((s) => {
          const isActive = s === stage;
          return (
            <li
              key={s}
              className={
                isActive
                  ? "job-status-step job-status-step-active"
                  : "job-status-step"
              }
              aria-current={isActive ? "step" : undefined}
            >
              {s}
            </li>
          );
        })}
      </ol>

      <details>
        <summary>Description</summary>
        <pre className="job-description">{job.description_text}</pre>
      </details>

      <h3>Tailored resumes</h3>
      {resumeVersions.length === 0 ? (
        <p className="settings-empty">No resume versions for this job yet.</p>
      ) : (
        <ul className="resume-version-list">
          {resumeVersions.map((v) => (
            <li key={v.id} className="resume-version-list-item">
              <Link to={`/resume-versions/${v.id}`}>
                Version {v.version_number}
              </Link>
              <span className="resume-version-status">
                {v.approved_at ? "Approved" : "Pending"}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h4>In-flight runs</h4>
      {inFlightRuns.length === 0 ? (
        <p className="settings-empty">No runs in flight for this job.</p>
      ) : (
        <ul className="run-list">
          {inFlightRuns.map((r) => (
            <li key={r.id} className="run-list-item">
              <Link to={`/runs/${r.id}`}>
                <strong>{r.id}</strong>
              </Link>
              <span className="run-meta-inline"> · {r.status}</span>
            </li>
          ))}
        </ul>
      )}

      <h3>Submit this job</h3>
      {(() => {
        const approved = resumeVersions.filter((v) => v.approved_at);
        if (hasSubmittedApplication) {
          return (
            <p className="settings-empty">
              This job already has a submitted application.
            </p>
          );
        }
        if (approved.length === 0) {
          return (
            <p className="settings-empty">
              Approve a resume version first (see Tailored resumes above).
            </p>
          );
        }
        return (
          <ul className="resume-version-list">
            {approved.map((v) => (
              <li key={v.id} className="resume-version-list-item">
                <span>
                  Version {v.version_number}{" "}
                  <span className="resume-version-status">(approved)</span>
                </span>
                <button
                  type="button"
                  onClick={() => handleCreateApplication(v.id)}
                  disabled={applyingVersionId !== null}
                >
                  {applyingVersionId === v.id
                    ? "Creating…"
                    : "Create application"}
                </button>
              </li>
            ))}
          </ul>
        );
      })()}
      {applyError ? (
        <p role="alert" className="error">
          {applyError}
        </p>
      ) : null}

      <h4>Applications</h4>
      {applications.length === 0 ? (
        <p className="settings-empty">No applications for this job yet.</p>
      ) : (
        <ul className="application-list">
          {applications.map((app) => (
            <li key={app.id} className="application-list-item">
              <Link to={`/applications/${app.id}`}>
                <strong>{app.id}</strong>
              </Link>
              <span className="application-meta">
                {" "}
                · {app.status} · submitted {formatTimestamp(app.submitted_at)}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3>Tailor a new resume</h3>
      <p className="job-meta">
        Generate a new tailored draft when you want to iterate on the resume.
      </p>
      <form onSubmit={handleGenerate} noValidate>
        <label className="field">
          <span>Master resume</span>
          <select
            value={selectedResumeId}
            onChange={(e) => setSelectedResumeId(e.target.value)}
            required
          >
            <option value="">Select a master resume…</option>
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
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

        {submitError ? (
          <p role="alert" className="error">
            {submitError}
          </p>
        ) : null}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Generating…" : "Generate resume"}
        </button>
      </form>
    </section>
  );
}
