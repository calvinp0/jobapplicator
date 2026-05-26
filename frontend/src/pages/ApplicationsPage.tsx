import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  getGmailStatus,
  listApplications,
  listJobs,
  markApplicationInterview,
  markApplicationRejected,
  submitApplication,
  syncApplicationsGmail,
} from "../api";
import type {
  Application,
  GmailStatusResponse,
  GmailSyncApplicationsResponse,
  Job,
} from "../api";
import {
  applicationUpdatedLabel,
  emailStatusLabel,
  lastEmailSummary,
  parseTimestamp,
  runStatusLabel,
  submissionStatusLabel,
  timelineStageLabel,
  timelineStageVariant,
} from "../lib/workflow";

function formatChecked(value: string | null | undefined): string | null {
  const then = parseTimestamp(value ?? null);
  if (!then) return null;
  const diff = Date.now() - then.getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

type FilterId =
  | "all"
  | "drafts"
  | "ready"
  | "submitted"
  | "needs_review"
  | "interviews"
  | "rejected";

const FILTERS: Array<{ id: FilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "drafts", label: "Drafts" },
  { id: "ready", label: "Ready" },
  { id: "submitted", label: "Submitted" },
  { id: "needs_review", label: "Needs review" },
  { id: "interviews", label: "Interviews" },
  { id: "rejected", label: "Rejected" },
];

// Sort priority for the table: needs-attention rows surface first so the
// user sees rejections / review queues / drafts before quiet
// "waiting for email" rows. Lower numbers sort earlier.
const ATTENTION_ORDER: Record<string, number> = {
  needs_review: 0,
  email_received: 1,
  classified_rejection: 2,
  classified_interview: 3,
  classified_positive: 4,
  classified_offer: 5,
  classified_neutral: 6,
  confirmation_found: 7,
  watching: 8,
  no_match: 9,
  not_watching: 10,
  error: 11,
};

const STAGE_ORDER: Record<string, number> = {
  draft: 0,
  rejected: 1,
  interview: 2,
  offer: 3,
  response_received: 4,
  confirmation_received: 5,
  sent: 6,
  withdrawn: 7,
};

function attentionScore(app: Application): number {
  const stage = STAGE_ORDER[app.timeline_stage] ?? 99;
  const email = ATTENTION_ORDER[app.email_status] ?? 99;
  return stage * 100 + email;
}

function matchesFilter(app: Application, filter: FilterId): boolean {
  switch (filter) {
    case "all":
      return true;
    case "drafts":
      return app.timeline_stage === "draft";
    case "ready":
      return (
        app.timeline_stage === "draft" &&
        app.submission_status === "not_submitted" &&
        app.next_action.toLowerCase().includes("ready")
      );
    case "submitted":
      return app.submission_status === "submitted";
    case "needs_review":
      return app.email_status === "needs_review";
    case "interviews":
      return app.timeline_stage === "interview";
    case "rejected":
      return app.timeline_stage === "rejected";
    default:
      return true;
  }
}

export function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncResult, setSyncResult] =
    useState<GmailSyncApplicationsResponse | null>(null);
  const [gmailStatus, setGmailStatus] = useState<GmailStatusResponse | null>(
    null,
  );
  const [filter, setFilter] = useState<FilterId>("all");

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
    // Gmail status is loaded separately so a failure here never blocks the
    // application list; the UI just falls back to the generic "Connect Gmail
    // in Settings" hint.
    getGmailStatus()
      .then((s) => {
        if (!cancelled) setGmailStatus(s);
      })
      .catch(() => {
        // Non-fatal; treat as unknown status.
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

  async function handleSyncGmail() {
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      const response = await syncApplicationsGmail();
      setSyncResult(response);
      if (response.gmail_connected) {
        // Refresh applications so derived fields reflect the new
        // email_status / last_gmail_check_at / classification.
        try {
          const refreshed = await listApplications();
          setApplications(refreshed);
        } catch {
          // The sync response is the user-facing source of truth — if
          // the refresh fails, leave the existing list in place.
        }
      }
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to sync Gmail";
      setSyncError(message);
    } finally {
      setSyncing(false);
    }
  }

  const visibleApplications = useMemo(() => {
    if (!applications) return [];
    const filtered = applications.filter((a) => matchesFilter(a, filter));
    return [...filtered].sort((a, b) => {
      const scoreA = attentionScore(a);
      const scoreB = attentionScore(b);
      if (scoreA !== scoreB) return scoreA - scoreB;
      const tA = parseTimestamp(a.updated_at)?.getTime() ?? 0;
      const tB = parseTimestamp(b.updated_at)?.getTime() ?? 0;
      return tB - tA;
    });
  }, [applications, filter]);

  if (error) {
    return (
      <section className="applications-page">
        <header className="page-header">
          <h2>Applications</h2>
        </header>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (applications === null || jobs === null) {
    return (
      <section className="applications-page">
        <header className="page-header">
          <h2>Applications</h2>
        </header>
        <p>Loading applications…</p>
      </section>
    );
  }

  const jobsById = new Map(jobs.map((j) => [j.id, j]));

  const gmailDisconnected =
    gmailStatus && gmailStatus.configured && !gmailStatus.connected;
  const gmailNotConfigured = gmailStatus && !gmailStatus.configured;

  return (
    <section className="applications-page">
      <header className="page-header applications-page-header">
        <div className="applications-page-header-row">
          <div>
            <h2>Applications</h2>
            <p className="page-subtitle">
              Track drafts, submissions, email evidence, and outcomes.
            </p>
          </div>
          <div className="applications-toolbar">
            <button
              type="button"
              className="button"
              onClick={handleSyncGmail}
              disabled={syncing}
              data-testid="sync-gmail-button"
            >
              {syncing ? "Syncing Gmail…" : "Sync Gmail"}
            </button>
          </div>
        </div>
        {gmailNotConfigured ? (
          <p
            className="applications-toolbar-hint"
            data-testid="sync-gmail-hint"
          >
            Gmail OAuth is not configured.{" "}
            <Link to="/settings">Open Settings</Link> for setup details.
          </p>
        ) : gmailDisconnected ? (
          <p
            className="applications-toolbar-hint"
            data-testid="sync-gmail-hint"
          >
            <Link to="/settings">Connect Gmail in Settings</Link> before
            syncing applications.
          </p>
        ) : null}
        {syncResult && syncResult.gmail_connected ? (
          <p className="applications-toolbar-summary" role="status">
            Last sync: checked {syncResult.checked_count} application
            {syncResult.checked_count === 1 ? "" : "s"} · Updated{" "}
            {syncResult.updated_count} · No match {syncResult.no_match_count} ·
            Needs review {syncResult.needs_review_count}
          </p>
        ) : null}
      </header>

      {syncError ? (
        <p role="alert" className="error">
          {syncError}
        </p>
      ) : null}
      {syncResult && !syncResult.gmail_connected ? (
        <p className="applications-toolbar-summary" role="status">
          {syncResult.message ?? "Connect Gmail before syncing applications."}
        </p>
      ) : null}
      {syncResult && syncResult.gmail_connected && syncResult.results.length > 0 ? (
        <ul className="applications-sync-results">
          {syncResult.results.map((res) => {
            const label = `${res.job_title ?? "—"} — ${res.company ?? "—"}`;
            if (res.skipped_reason) {
              return (
                <li key={res.application_id}>
                  {label}: Skipped ({res.skipped_reason})
                </li>
              );
            }
            if (res.classification) {
              const top = res.evidence[0];
              return (
                <li key={res.application_id}>
                  {label}:{" "}
                  {res.application_status_changed
                    ? `${res.new_application_status} (was ${res.previous_application_status})`
                    : res.classification.replace(/_/g, " ")}
                  {top ? ` — Evidence: "${top.text}"` : null}
                </li>
              );
            }
            return (
              <li key={res.application_id}>
                {label}: {res.new_email_status.replace(/_/g, " ")}
              </li>
            );
          })}
        </ul>
      ) : null}
      {actionError ? (
        <p role="alert" className="error">
          {actionError}
        </p>
      ) : null}

      {applications.length === 0 ? (
        <div className="applications-empty">
          <h3>No applications yet.</h3>
          <p>
            Create or generate a draft from a job to start tracking
            applications.
          </p>
        </div>
      ) : (
        <>
          <div
            className="applications-filters"
            role="toolbar"
            aria-label="Filter applications"
          >
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`applications-filter${
                  filter === f.id ? " applications-filter-active" : ""
                }`}
                aria-pressed={filter === f.id}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {visibleApplications.length === 0 ? (
            <p className="applications-empty-filter">
              No applications match this filter.
            </p>
          ) : (
            <div
              className="applications-table-wrapper"
              data-testid="applications-table"
            >
              <table className="applications-table">
                <thead>
                  <tr>
                    <th scope="col">Job</th>
                    <th scope="col">Status</th>
                    <th scope="col">Submission</th>
                    <th scope="col">Email</th>
                    <th scope="col">Latest run</th>
                    <th scope="col">Updated</th>
                    <th scope="col">Next action</th>
                    <th scope="col" className="applications-table-actions-col">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visibleApplications.map((app) => {
                    const job = jobsById.get(app.job_id);
                    const title = job ? job.title : `Job ${app.job_id}`;
                    const company = job ? job.company : null;
                    const label = company ? `${title} — ${company}` : title;
                    const stageLabel = timelineStageLabel(app.timeline_stage);
                    const stageVariant = timelineStageVariant(
                      app.timeline_stage,
                    );
                    const submissionLabel = submissionStatusLabel(
                      app.submission_status,
                    );
                    const submissionCell =
                      app.submission_status === "submitted" && app.submitted_at
                        ? `${submissionLabel} ${formatDate(app.submitted_at)}`
                        : submissionLabel;
                    const emailSummary = lastEmailSummary(app);
                    const emailExtra =
                      emailSummary && app.email_link_count > 1
                        ? ` · ${app.email_link_count} emails`
                        : "";
                    const gmailCheckedAgo = formatChecked(
                      app.last_gmail_check_at,
                    );
                    const latestRunCell = app.latest_run_status
                      ? runStatusLabel(app.latest_run_status)
                      : "—";
                    const updatedCell = applicationUpdatedLabel(app);
                    const isPending = pendingActionId === app.id;
                    const showSubmit =
                      app.submission_status === "not_submitted";
                    const showReject = !["rejected", "withdrawn"].includes(
                      app.status,
                    );
                    const showInterview = ![
                      "interview",
                      "rejected",
                      "withdrawn",
                      "offer",
                    ].includes(app.status);
                    return (
                      <tr
                        key={app.id}
                        className="applications-row"
                        data-application-id={app.id}
                      >
                        <td
                          className="applications-cell-job"
                          data-label="Job"
                        >
                          <Link
                            to={`/applications/${app.id}`}
                            className="applications-job-link"
                          >
                            {title}
                          </Link>
                          {company ? (
                            <span className="applications-job-company">
                              {company}
                            </span>
                          ) : null}
                        </td>
                        <td data-label="Status">
                          <span
                            className={`status-badge status-badge-${stageVariant}`}
                            data-testid={`status-badge-${app.id}`}
                          >
                            {stageLabel}
                          </span>
                        </td>
                        <td data-label="Submission">
                          <span className="applications-cell-text">
                            Submission: {submissionCell}
                          </span>
                        </td>
                        <td data-label="Email">
                          <div className="applications-cell-email">
                            <span className="applications-cell-text">
                              Email: {emailStatusLabel(app.email_status)}
                            </span>
                            {emailSummary ? (
                              <span className="applications-cell-email-summary">
                                {emailSummary}
                                {emailExtra}
                              </span>
                            ) : null}
                            {gmailCheckedAgo ? (
                              <span className="applications-cell-subtle">
                                Gmail checked: {gmailCheckedAgo}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td data-label="Latest run">
                          <span className="applications-cell-text">
                            {latestRunCell}
                          </span>
                        </td>
                        <td data-label="Updated">
                          <span className="applications-cell-text">
                            Updated: {updatedCell}
                          </span>
                        </td>
                        <td data-label="Next action">
                          <span
                            className="applications-cell-next-action"
                            data-testid={`next-action-${app.id}`}
                          >
                            Next: {app.next_action}
                          </span>
                        </td>
                        <td
                          data-label="Actions"
                          className="applications-cell-actions"
                        >
                          <div className="applications-row-actions">
                            <Link
                              className="applications-action-link"
                              to={`/applications/${app.id}`}
                              aria-label={`Open ${label}`}
                            >
                              Open
                            </Link>
                            {showSubmit ? (
                              <button
                                type="button"
                                className="applications-action-button"
                                disabled={isPending}
                                onClick={() =>
                                  runAction(app.id, submitApplication)
                                }
                              >
                                Mark submitted
                              </button>
                            ) : null}
                            {showInterview ? (
                              <button
                                type="button"
                                className="applications-action-button"
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
                                className="applications-action-button"
                                disabled={isPending}
                                onClick={() =>
                                  runAction(app.id, markApplicationRejected)
                                }
                              >
                                Mark rejected
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
