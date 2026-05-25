import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listApplications, listJobs } from "../api";
import type { Application, Job } from "../api";
import {
  lastEmailSummary,
  timelineStageLabel,
  timelineStageVariant,
} from "../lib/workflow";

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listApplications(), listJobs()])
      .then(([apps, js]) => {
        if (cancelled) return;
        setApplications(apps);
        setJobs(js);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load applications";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="applications-page">
        <h2>Applications</h2>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (applications === null || jobs === null) {
    return (
      <section className="applications-page">
        <h2>Applications</h2>
        <p>Loading applications…</p>
      </section>
    );
  }

  const jobsById = new Map(jobs.map((j) => [j.id, j]));

  return (
    <section className="applications-page">
      <h2>Applications</h2>
      {applications.length === 0 ? (
        <p>No applications yet.</p>
      ) : (
        <ul className="application-list">
          {applications.map((app) => {
            const job = jobsById.get(app.job_id);
            const label = job
              ? `${job.title} — ${job.company}`
              : `Job ${app.job_id}`;
            const stageLabel = timelineStageLabel(app.timeline_stage);
            const stageVariant = timelineStageVariant(app.timeline_stage);
            const emailSummary = lastEmailSummary(app);
            const emailSuffix =
              emailSummary && app.email_link_count > 1
                ? ` · ${app.email_link_count} emails`
                : "";
            return (
              <li key={app.id} className="application-list-item">
                <div className="application-row-head">
                  <Link to={`/applications/${app.id}`}>
                    <strong>{label}</strong>
                  </Link>
                  <span
                    className={`status-badge status-badge-${stageVariant}`}
                  >
                    {stageLabel}
                  </span>
                </div>
                {app.submitted_at ? (
                  <span className="application-meta">
                    sent {formatTimestamp(app.submitted_at)}
                  </span>
                ) : null}
                {emailSummary ? (
                  <span className="application-meta application-email-summary">
                    {emailSummary}
                    {emailSuffix}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
