import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  listApplications,
  listJobs,
  listResumeVersions,
  listRuns,
} from "../api";
import type {
  Application,
  ClaudeRun,
  Job,
  ResumeVersion,
} from "../api";

const IN_FLIGHT_RUN_STATUSES = new Set(["created", "running", "completed"]);

type JobStageKey =
  | "tailoring"
  | "review"
  | "ready"
  | "submitted"
  | "captured";

interface JobStage {
  key: JobStageKey;
  label: string;
  variant: string;
}

interface JobView {
  job: Job;
  stage: JobStage;
  approvedVersion: ResumeVersion | null;
  pendingVersion: ResumeVersion | null;
  inFlightRun: ClaudeRun | null;
  submittedApp: Application | null;
  openApp: Application | null;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatRelative(value: string | null): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return formatTimestamp(value);
  const diffMs = Date.now() - then;
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

function computeJobStage(
  job: Job,
  versions: ResumeVersion[],
  applications: Application[],
  runs: ClaudeRun[],
): JobStage {
  const jobApps = applications.filter((a) => a.job_id === job.id);
  if (jobApps.some((a) => a.status === "submitted")) {
    return { key: "submitted", label: "Submitted", variant: "submitted" };
  }
  const jobVersions = versions.filter((v) => v.job_id === job.id);
  if (jobVersions.some((v) => v.approved_at)) {
    return { key: "ready", label: "Ready to apply", variant: "approved" };
  }
  if (jobVersions.length > 0) {
    return {
      key: "review",
      label: "Resume ready to review",
      variant: "completed",
    };
  }
  const jobRuns = runs.filter((r) => r.job_id === job.id);
  if (jobRuns.some((r) => IN_FLIGHT_RUN_STATUSES.has(r.status))) {
    return { key: "tailoring", label: "Tailoring resume", variant: "running" };
  }
  return { key: "captured", label: "Awaiting tailoring", variant: "pending" };
}

function buildJobView(
  job: Job,
  versions: ResumeVersion[],
  applications: Application[],
  runs: ClaudeRun[],
): JobView {
  const stage = computeJobStage(job, versions, applications, runs);
  const jobVersions = versions
    .filter((v) => v.job_id === job.id)
    .sort((a, b) => b.version_number - a.version_number);
  const approvedVersion =
    jobVersions.find((v) => v.approved_at !== null) ?? null;
  const pendingVersion =
    jobVersions.find((v) => v.approved_at === null) ?? null;
  const jobRuns = runs.filter((r) => r.job_id === job.id);
  const inFlightRun =
    jobRuns.find((r) => IN_FLIGHT_RUN_STATUSES.has(r.status)) ?? null;
  const jobApps = applications.filter((a) => a.job_id === job.id);
  const submittedApp = jobApps.find((a) => a.status === "submitted") ?? null;
  const openApp = jobApps.find((a) => a.status !== "submitted") ?? null;
  return {
    job,
    stage,
    approvedVersion,
    pendingVersion,
    inFlightRun,
    submittedApp,
    openApp,
  };
}

interface NextAction {
  title: string;
  description: string;
  href: string;
  cta: string;
}

function computeNextAction(views: JobView[]): NextAction | null {
  const priority: JobStageKey[] = [
    "ready",
    "review",
    "tailoring",
    "captured",
  ];
  for (const key of priority) {
    const view = views.find((v) => v.stage.key === key);
    if (!view) continue;
    const company = view.job.company;
    const title = view.job.title;
    if (key === "ready" && view.approvedVersion) {
      const target = view.openApp
        ? `/applications/${view.openApp.id}`
        : `/jobs/${view.job.id}`;
      return {
        title: `Submit application to ${company}`,
        description: `${title} — your tailored resume is approved and ready to send.`,
        href: target,
        cta: view.openApp ? "Continue application" : "Open job",
      };
    }
    if (key === "review" && view.pendingVersion) {
      return {
        title: `Review tailored resume for ${company}`,
        description: `${title} — a new draft is waiting on your approval.`,
        href: `/resume-versions/${view.pendingVersion.id}`,
        cta: "Review resume",
      };
    }
    if (key === "tailoring" && view.inFlightRun) {
      return {
        title: `Tailoring resume for ${company}`,
        description: `${title} — a tailoring run is in progress. Check on it when it finishes.`,
        href: `/runs/${view.inFlightRun.id}`,
        cta: "View run",
      };
    }
    if (key === "captured") {
      return {
        title: `Tailor a resume for ${company}`,
        description: `${title} — pick a master resume and start a tailoring run.`,
        href: `/jobs/${view.job.id}`,
        cta: "Open job",
      };
    }
  }
  return null;
}

interface ActivityItem {
  id: string;
  time: string;
  label: string;
  href: string;
  sub: string;
}

function buildActivity(
  jobs: Job[],
  applications: Application[],
  versions: ResumeVersion[],
  runs: ClaudeRun[],
): ActivityItem[] {
  const jobsById = new Map(jobs.map((j) => [j.id, j]));
  const items: ActivityItem[] = [];

  for (const app of applications) {
    const job = jobsById.get(app.job_id);
    const label = job ? `${job.title} — ${job.company}` : "Application";
    if (app.submitted_at) {
      items.push({
        id: `app-sub-${app.id}`,
        time: app.submitted_at,
        label: `Application submitted · ${label}`,
        href: `/applications/${app.id}`,
        sub: formatRelative(app.submitted_at),
      });
    } else {
      items.push({
        id: `app-${app.id}`,
        time: app.created_at,
        label: `Application started · ${label}`,
        href: `/applications/${app.id}`,
        sub: formatRelative(app.created_at),
      });
    }
  }

  for (const v of versions) {
    const job = jobsById.get(v.job_id);
    const label = job ? `${job.title} — ${job.company}` : "Resume version";
    if (v.approved_at) {
      items.push({
        id: `v-app-${v.id}`,
        time: v.approved_at,
        label: `Resume approved · ${label}`,
        href: `/resume-versions/${v.id}`,
        sub: formatRelative(v.approved_at),
      });
    }
    items.push({
      id: `v-${v.id}`,
      time: v.created_at,
      label: `Resume draft ${v.version_number} · ${label}`,
      href: `/resume-versions/${v.id}`,
      sub: formatRelative(v.created_at),
    });
  }

  for (const r of runs) {
    const job = jobsById.get(r.job_id);
    const label = job ? `${job.title} — ${job.company}` : "Tailoring run";
    items.push({
      id: `r-${r.id}`,
      time: r.created_at,
      label: `Tailoring run · ${label}`,
      href: `/runs/${r.id}`,
      sub: formatRelative(r.created_at),
    });
  }

  return items
    .sort((a, b) => b.time.localeCompare(a.time))
    .slice(0, 6);
}

export function DashboardPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [runs, setRuns] = useState<ClaudeRun[] | null>(null);
  const [resumeVersions, setResumeVersions] = useState<ResumeVersion[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listJobs(),
      listApplications(),
      listRuns(),
      listResumeVersions(),
    ])
      .then(([js, apps, rs, vs]) => {
        if (cancelled) return;
        setJobs(js);
        setApplications(apps);
        setRuns(rs);
        setResumeVersions(vs);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load dashboard";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="dashboard">
        <header className="page-header">
          <h2>Application cockpit</h2>
        </header>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (
    jobs === null ||
    applications === null ||
    runs === null ||
    resumeVersions === null
  ) {
    return (
      <section className="dashboard">
        <header className="page-header">
          <h2>Application cockpit</h2>
        </header>
        <p>Loading dashboard…</p>
      </section>
    );
  }

  const submittedJobIds = new Set(
    applications.filter((a) => a.submitted_at !== null).map((a) => a.job_id),
  );
  const activeJobs = jobs.filter((j) => !submittedJobIds.has(j.id));
  const importedRunIds = new Set(
    resumeVersions
      .map((v) => v.claude_run_id)
      .filter((id): id is string => id !== null),
  );
  const inFlightRuns = runs.filter((run) => {
    if (!IN_FLIGHT_RUN_STATUSES.has(run.status)) return false;
    if (run.status === "completed" && importedRunIds.has(run.id)) return false;
    return true;
  });
  const submittedApplications = applications.filter(
    (a) => a.submitted_at !== null,
  );
  const resumesReady = resumeVersions.filter((v) => v.approved_at !== null);

  const activeJobViews = activeJobs.map((j) =>
    buildJobView(j, resumeVersions, applications, runs),
  );

  const nextAction = computeNextAction(activeJobViews);
  const activity = buildActivity(jobs, applications, resumeVersions, runs);
  const hasData =
    jobs.length > 0 ||
    applications.length > 0 ||
    runs.length > 0 ||
    resumeVersions.length > 0;

  return (
    <section className="dashboard">
      <header className="page-header">
        <h2>Application cockpit</h2>
        <p className="page-subtitle">
          {hasData
            ? `You have ${activeJobs.length} active job${
                activeJobs.length === 1 ? "" : "s"
              }, ${inFlightRuns.length} in-flight run${
                inFlightRuns.length === 1 ? "" : "s"
              }, and ${submittedApplications.length} application${
                submittedApplications.length === 1 ? "" : "s"
              } submitted.`
            : "Capture a job from the browser extension to get started."}
        </p>
        <p className="dashboard-summary-sr">
          {activeJobs.length} active jobs · {inFlightRuns.length} in-flight runs
          · {submittedApplications.length} applications submitted
        </p>
      </header>

      <ul className="summary-cards" aria-label="Summary">
        <li className="summary-card">
          <span className="summary-card-label">Active jobs</span>
          <span className="summary-card-value">{activeJobs.length}</span>
          <Link to="/jobs" className="summary-card-link">
            View jobs
          </Link>
        </li>
        <li className="summary-card">
          <span className="summary-card-label">Resumes ready</span>
          <span className="summary-card-value">{resumesReady.length}</span>
          <span className="summary-card-meta">
            {resumesReady.length === 0
              ? "Approve a draft to unlock submitting"
              : "Approved and ready to send"}
          </span>
        </li>
        <li className="summary-card">
          <span className="summary-card-label">Applications submitted</span>
          <span className="summary-card-value">
            {submittedApplications.length}
          </span>
          <Link to="/applications" className="summary-card-link">
            View applications
          </Link>
        </li>
        <li className="summary-card">
          <span className="summary-card-label">In-flight runs</span>
          <span className="summary-card-value">{inFlightRuns.length}</span>
          <span className="summary-card-meta">
            {inFlightRuns.length === 0
              ? "No tailoring runs in progress"
              : "Tailoring in progress"}
          </span>
        </li>
      </ul>

      <section className="dashboard-section" aria-labelledby="dashboard-next">
        <h3 id="dashboard-next">Next action</h3>
        {nextAction ? (
          <article className="next-action-card">
            <div className="next-action-body">
              <h4 className="next-action-title">{nextAction.title}</h4>
              <p className="next-action-description">
                {nextAction.description}
              </p>
            </div>
            <Link to={nextAction.href} className="button button-primary">
              {nextAction.cta}
            </Link>
          </article>
        ) : (
          <p className="dashboard-empty">
            {hasData
              ? "Nothing waiting on you — every active job is up to date."
              : "Once you capture a job, your next action will appear here."}
          </p>
        )}
      </section>

      <section
        className="dashboard-section"
        aria-labelledby="dashboard-active-jobs"
      >
        <h3 id="dashboard-active-jobs">Active jobs</h3>
        {activeJobs.length === 0 ? (
          <p className="dashboard-empty">
            No active jobs yet — capture a job from the extension.
          </p>
        ) : (
          <ul className="job-card-grid">
            {activeJobViews.map((view) => (
              <li key={view.job.id} className="job-card">
                <div className="job-card-header">
                  <div>
                    <Link
                      to={`/jobs/${view.job.id}`}
                      className="job-card-title"
                    >
                      {view.job.title}
                    </Link>
                    <p className="job-card-company">{view.job.company}</p>
                  </div>
                  <span
                    className={`status-badge status-badge-${view.stage.variant}`}
                  >
                    {view.stage.label}
                  </span>
                </div>
                {view.job.location ? (
                  <p className="job-card-meta">{view.job.location}</p>
                ) : null}
                <div className="job-card-actions">
                  <Link
                    to={`/jobs/${view.job.id}`}
                    className="button button-secondary"
                  >
                    Review job
                  </Link>
                  {view.approvedVersion ? (
                    <Link
                      to={`/resume-versions/${view.approvedVersion.id}`}
                      className="button button-secondary"
                    >
                      Open resume
                    </Link>
                  ) : view.pendingVersion ? (
                    <Link
                      to={`/resume-versions/${view.pendingVersion.id}`}
                      className="button button-secondary"
                    >
                      Open draft
                    </Link>
                  ) : null}
                  {view.openApp ? (
                    <Link
                      to={`/applications/${view.openApp.id}`}
                      className="button button-secondary"
                    >
                      Continue application
                    </Link>
                  ) : null}
                  {view.inFlightRun ? (
                    <Link
                      to={`/runs/${view.inFlightRun.id}`}
                      className="button button-secondary"
                    >
                      View run
                    </Link>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="dashboard-section" aria-labelledby="dashboard-runs">
        <h3 id="dashboard-runs">In-flight runs</h3>
        {inFlightRuns.length === 0 ? (
          <p className="dashboard-empty">
            No runs in progress — start a tailoring run from a job page.
          </p>
        ) : (
          <ul className="run-list">
            {inFlightRuns.map((run) => {
              const job = jobs.find((j) => j.id === run.job_id);
              const label = job
                ? `${job.title} — ${job.company}`
                : `Run ${run.id}`;
              return (
                <li key={run.id} className="run-list-item">
                  <Link to={`/runs/${run.id}`}>
                    <strong>{label}</strong>
                  </Link>
                  <span className="run-meta-inline">
                    {" "}
                    · {run.status} · {formatTimestamp(run.created_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section
        className="dashboard-section"
        aria-labelledby="dashboard-activity"
      >
        <h3 id="dashboard-activity">Recent activity</h3>
        {activity.length === 0 ? (
          <p className="dashboard-empty">
            No applications yet — approve a tailored resume on a job to create one.
          </p>
        ) : (
          <ol className="timeline">
            {activity.map((item) => (
              <li key={item.id} className="timeline-item">
                <span className="timeline-dot" aria-hidden="true" />
                <div className="timeline-body">
                  <Link to={item.href} className="timeline-title">
                    {item.label}
                  </Link>
                  <span className="timeline-meta">{item.sub}</span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}
