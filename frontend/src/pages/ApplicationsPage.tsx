import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  listApplications,
  listJobs,
  markApplicationInterview,
  markApplicationRejected,
  submitApplication,
} from "../api";
import type { Application, Job } from "../api";
import {
  applicationUpdatedLabel,
  emailStatusLabel,
  lastEmailSummary,
  runStatusLabel,
  submissionStatusLabel,
  timelineStageLabel,
  timelineStageVariant,
} from "../lib/workflow";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

export function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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

  async function runAction(
    appId: string,
    action: (id: string) => Promise<Application>,
  ) {
    setPendingActionId(appId);
    setActionError(null);
    try {
      const updated = await action(appId);
      setApplications((prev) =>
        prev ? prev.map((a) => (a.id === updated.id ? updated : a)) : prev,
      );
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to update application";
      setActionError(message);
    } finally {
      setPendingActionId(null);
    }
  }

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
      {actionError ? (
        <p role="alert" className="error">
          {actionError}
        </p>
      ) : null}
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
            const submissionLabel = submissionStatusLabel(app.submission_status);
            const submittedLine =
              app.submission_status === "submitted" && app.submitted_at
                ? `Submission: Submitted ${formatDate(app.submitted_at)}`
                : `Submission: ${submissionLabel}`;
            const emailLine = `Email: ${emailStatusLabel(app.email_status)}`;
            const latestRunLine = app.latest_run_status
              ? `Latest run: ${runStatusLabel(app.latest_run_status)}`
              : null;
            const updatedLine = `Updated: ${applicationUpdatedLabel(app)}`;
            const isPending = pendingActionId === app.id;
            const showSubmit = app.submission_status === "not_submitted";
            const showReject = !["rejected", "withdrawn"].includes(app.status);
            const showInterview = !["interview", "rejected", "withdrawn", "offer"].includes(
              app.status,
            );
            return (
              <li key={app.id} className="application-list-item">
                <div className="application-row-head">
                  <Link to={`/applications/${app.id}`}>
                    <strong>{label}</strong>
                  </Link>
                  <span
                    className={`status-badge status-badge-${stageVariant}`}
                    data-testid={`status-badge-${app.id}`}
                  >
                    {stageLabel}
                  </span>
                </div>
                <span className="application-meta">{submittedLine}</span>
                <span className="application-meta">{emailLine}</span>
                {latestRunLine ? (
                  <span className="application-meta">{latestRunLine}</span>
                ) : null}
                <span className="application-meta">{updatedLine}</span>
                <span
                  className="application-meta application-next-action"
                  data-testid={`next-action-${app.id}`}
                >
                  Next: {app.next_action}
                </span>
                {emailSummary ? (
                  <span className="application-meta application-email-summary">
                    {emailSummary}
                    {emailSuffix}
                  </span>
                ) : null}
                <div className="application-actions">
                  <Link
                    className="application-action-link"
                    to={`/applications/${app.id}`}
                  >
                    Open
                  </Link>
                  {showSubmit ? (
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => runAction(app.id, submitApplication)}
                    >
                      Mark submitted
                    </button>
                  ) : null}
                  {showInterview ? (
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() =>
                        runAction(app.id, markApplicationInterview)
                      }
                    >
                      Mark interview
                    </button>
                  ) : null}
                  {showReject ? (
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => runAction(app.id, markApplicationRejected)}
                    >
                      Mark rejected
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
