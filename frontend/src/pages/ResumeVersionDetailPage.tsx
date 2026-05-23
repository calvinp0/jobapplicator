import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  approveResumeVersion,
  getJob,
  getResumeVersion,
  openResumeVersionFile,
} from "../api";
import type { Job, ResumeVersion } from "../api";

function truncateHash(hash: string | null): string {
  if (!hash) return "—";
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function ResumeVersionDetailPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);
  const [isOpening, setIsOpening] = useState(false);

  useEffect(() => {
    if (!versionId) return;
    let cancelled = false;
    getResumeVersion(versionId)
      .then((v) => {
        if (cancelled) return;
        setVersion(v);
        return getJob(v.job_id);
      })
      .then((j) => {
        if (cancelled || !j) return;
        setJob(j);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load resume version";
        setLoadError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  async function handleApprove() {
    if (!versionId || !version || version.approved_at) return;
    setIsApproving(true);
    setActionError(null);
    try {
      const updated = await approveResumeVersion(versionId);
      setVersion(updated);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to approve version";
      setActionError(message);
    } finally {
      setIsApproving(false);
    }
  }

  async function handleOpenDocx() {
    if (!versionId || !version || !version.docx_path) return;
    setIsOpening(true);
    setActionError(null);
    try {
      await openResumeVersionFile(versionId);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to open DOCX";
      setActionError(message);
    } finally {
      setIsOpening(false);
    }
  }

  if (loadError) {
    return (
      <section className="resume-version-detail">
        <h2>Resume version</h2>
        <p role="alert" className="error">
          {loadError}
        </p>
      </section>
    );
  }

  if (!version) {
    return (
      <section className="resume-version-detail">
        <h2>Resume version</h2>
        <p>Loading…</p>
      </section>
    );
  }

  return (
    <section className="resume-version-detail">
      <h2>Resume version {version.version_number}</h2>
      <dl className="run-meta">
        <dt>Version</dt>
        <dd>{version.version_number}</dd>
        <dt>Job</dt>
        <dd>
          {job ? (
            <Link to={`/jobs/${version.job_id}`}>
              {job.title} — {job.company}
            </Link>
          ) : (
            <Link to={`/jobs/${version.job_id}`}>{version.job_id}</Link>
          )}
        </dd>
        <dt>Source</dt>
        <dd>{version.source}</dd>
        <dt>Created</dt>
        <dd>{formatTimestamp(version.created_at)}</dd>
        <dt>Approved</dt>
        <dd>
          {version.approved_at
            ? `Approved on ${formatTimestamp(version.approved_at)}`
            : "Not approved"}
        </dd>
      </dl>

      <div className="run-actions">
        <button
          type="button"
          onClick={handleOpenDocx}
          disabled={!version.docx_path || isOpening}
        >
          {isOpening ? "Opening…" : "Open DOCX"}
        </button>
        <button
          type="button"
          onClick={handleApprove}
          disabled={version.approved_at !== null || isApproving}
        >
          {isApproving ? "Approving…" : "Approve"}
        </button>
      </div>

      {actionError ? (
        <p role="alert" className="error">
          {actionError}
        </p>
      ) : null}

      <details className="advanced-details">
        <summary>Advanced details</summary>
        <dl className="run-meta">
          <dt>Resume version id</dt>
          <dd>
            <code>{version.id}</code>
          </dd>
          <dt>Claude run id</dt>
          <dd>
            {version.claude_run_id ? (
              <Link to={`/runs/${version.claude_run_id}`}>
                <code>{version.claude_run_id}</code>
              </Link>
            ) : (
              "—"
            )}
          </dd>
          <dt>Content hash</dt>
          <dd>
            <code>{truncateHash(version.content_hash)}</code>
          </dd>
          <dt>Prompt hash</dt>
          <dd>
            <code>{truncateHash(version.prompt_hash)}</code>
          </dd>
          <dt>DOCX path</dt>
          <dd>
            {version.docx_path ? <code>{version.docx_path}</code> : "—"}
          </dd>
          <dt>PDF path</dt>
          <dd>
            {version.pdf_path ? <code>{version.pdf_path}</code> : "—"}
          </dd>
        </dl>
      </details>

      {version.content_markdown ? (
        <details className="resume-version-markdown">
          <summary>Resume markdown</summary>
          <pre className="job-description">{version.content_markdown}</pre>
        </details>
      ) : null}
    </section>
  );
}
