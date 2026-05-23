import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  createRun,
  getJob,
  listEvidenceBanks,
  listMasterResumes,
  listResumeVersions,
} from "../api";
import type {
  EvidenceBank,
  Job,
  MasterResume,
  ResumeVersion,
} from "../api";

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
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [selectedBankId, setSelectedBankId] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    Promise.all([
      getJob(jobId),
      listMasterResumes(),
      listEvidenceBanks(),
      listResumeVersions(),
    ])
      .then(([j, r, e, v]) => {
        if (cancelled) return;
        setJob(j);
        setResumes(r);
        setEvidenceBanks(e);
        setResumeVersions(v.filter((version) => version.job_id === jobId));
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

  if (!job || !resumes || !evidenceBanks || !resumeVersions) {
    return (
      <section className="job-detail">
        <h2>Job</h2>
        <p>Loading…</p>
      </section>
    );
  }

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
      <details>
        <summary>Description</summary>
        <pre className="job-description">{job.description_text}</pre>
      </details>

      <h3>Resume versions</h3>
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

      <h3>Generate tailored resume</h3>
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
