import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  getJob,
  getRun,
  importRun,
  invokeRun,
  listResumeVersions,
} from "../api";
import type { ClaudeRun, Job, ResumeVersion } from "../api";

export function runStatusBadge(status: string): {
  label: string;
  variant: string;
} {
  switch (status) {
    case "created":
      return { label: "Pending", variant: "pending" };
    case "running":
      return { label: "Running", variant: "running" };
    case "completed":
      return { label: "Completed", variant: "completed" };
    case "failed":
      return { label: "Failed", variant: "failed" };
    default:
      return {
        label: status.charAt(0).toUpperCase() + status.slice(1),
        variant: "default",
      };
  }
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
  const [resumeVersion, setResumeVersion] = useState<ResumeVersion | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isInvoking, setIsInvoking] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    Promise.all([getRun(runId), listResumeVersions()])
      .then(async ([r, versions]) => {
        if (cancelled) return;
        setRun(r);
        const existing =
          versions.find((v) => v.claude_run_id === runId) ?? null;
        setResumeVersion(existing);
        const j = await getJob(r.job_id).catch(() => null);
        if (cancelled || !j) return;
        setJob(j);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load run";
        setLoadError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  async function handleInvoke() {
    if (!runId || !run || run.status !== "created") return;
    setIsInvoking(true);
    setActionError(null);
    try {
      const updated = await invokeRun(runId);
      setRun(updated);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to invoke run";
      setActionError(message);
    } finally {
      setIsInvoking(false);
    }
  }

  async function handleImport() {
    if (!runId || !run || run.status !== "completed") return;
    setIsImporting(true);
    setActionError(null);
    try {
      const version = await importRun(runId);
      setResumeVersion(version);
      const refreshed = await getRun(runId);
      setRun(refreshed);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to import run";
      setActionError(message);
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
        <dd>{run.status}</dd>
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

      <div className="run-actions">
        <button
          type="button"
          onClick={handleInvoke}
          disabled={run.status !== "created" || isInvoking}
        >
          {isInvoking ? "Invoking…" : "Invoke"}
        </button>
        <button
          type="button"
          onClick={handleImport}
          disabled={run.status !== "completed" || isImporting}
        >
          {isImporting ? "Importing…" : "Import outputs"}
        </button>
      </div>

      {actionError ? (
        <p role="alert" className="error">
          {actionError}
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
      </details>
    </section>
  );
}
