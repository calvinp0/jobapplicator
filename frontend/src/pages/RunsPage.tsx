import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listJobs, listRuns } from "../api";
import type { ClaudeRun, Job } from "../api";
import { EmptyState, PageHeader, StatusBadge } from "../components/ui";
import type { StatusBadgeVariant } from "../components/ui";

function statusBadge(status: string): {
  label: string;
  variant: StatusBadgeVariant;
} {
  switch (status) {
    case "created":
      return { label: "Pending", variant: "pending" };
    case "running":
      return { label: "Running", variant: "running" };
    case "completed":
      return { label: "Completed", variant: "completed" };
    case "imported":
      return { label: "Imported", variant: "completed" };
    case "failed":
      return { label: "Failed", variant: "failed" };
    default:
      return {
        label: status.charAt(0).toUpperCase() + status.slice(1),
        variant: "default",
      };
  }
}

export function RunsPage() {
  const [runs, setRuns] = useState<ClaudeRun[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listRuns(), listJobs()])
      .then(([rs, js]) => {
        if (cancelled) return;
        setRuns(rs);
        setJobs(js);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load runs";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="runs-page">
        <PageHeader
          title="Runs"
          description="Every tailoring run, newest first."
        />
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (runs === null || jobs === null) {
    return (
      <section className="runs-page">
        <PageHeader
          title="Runs"
          description="Every tailoring run, newest first."
        />
        <p>Loading runs…</p>
      </section>
    );
  }

  const jobsById = new Map(jobs.map((j) => [j.id, j]));
  const sorted = [...runs].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );

  return (
    <section className="runs-page">
      <PageHeader
        title="Runs"
        description="Every tailoring run, newest first."
      />
      {sorted.length === 0 ? (
        <EmptyState
          title="No runs yet."
          description="Open a job and click Generate Automatically to start your first tailoring run."
        />
      ) : (
        <ul className="run-list">
          {sorted.map((run) => {
            const job = jobsById.get(run.job_id);
            const label = job
              ? `${job.title} — ${job.company}`
              : run.id;
            const badge = statusBadge(run.status);
            return (
              <li key={run.id} className="run-list-item">
                <div className="run-list-item-row">
                  <Link to={`/runs/${run.id}`} className="run-list-item-link">
                    <strong>{label}</strong>
                  </Link>
                  <StatusBadge variant={badge.variant}>
                    {badge.label}
                  </StatusBadge>
                </div>
                <span className="run-meta-inline">
                  {new Date(run.created_at).toLocaleString()}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
