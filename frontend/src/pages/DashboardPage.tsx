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

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function jobStatusLabel(
  job: Job,
  versions: ResumeVersion[],
  applications: Application[],
): string {
  const jobApps = applications.filter((a) => a.job_id === job.id);
  if (jobApps.some((a) => a.status === "approved" || a.status === "ready")) {
    return "Approved — ready to submit";
  }
  const jobVersions = versions.filter((v) => v.job_id === job.id);
  if (jobVersions.some((v) => v.approved_at)) {
    return "Approved — ready to submit";
  }
  if (jobVersions.length > 0) {
    return "Resume ready to approve";
  }
  return "Awaiting tailoring";
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
        <h2>Home</h2>
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
        <h2>Home</h2>
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

  const recentApplications = [...applications]
    .sort((a, b) => {
      const aTime = a.submitted_at ?? a.created_at;
      const bTime = b.submitted_at ?? b.created_at;
      return bTime.localeCompare(aTime);
    })
    .slice(0, 5);

  const jobsById = new Map(jobs.map((j) => [j.id, j]));

  return (
    <section className="dashboard">
      <h2>Home</h2>
      <p className="dashboard-summary">
        {activeJobs.length} active jobs · {inFlightRuns.length} in-flight runs
        · {submittedApplications.length} applications submitted
      </p>

      <section className="dashboard-section" aria-labelledby="dashboard-active-jobs">
        <h3 id="dashboard-active-jobs">Active jobs</h3>
        {activeJobs.length === 0 ? (
          <p className="dashboard-empty">
            No active jobs yet — capture a job from the extension.
          </p>
        ) : (
          <ul className="job-list">
            {activeJobs.map((job) => (
              <li key={job.id} className="job-list-item">
                <Link to={`/jobs/${job.id}`}>
                  <strong>{job.title}</strong> — <span>{job.company}</span>
                </Link>
                <span className="dashboard-job-state">
                  {" "}
                  · {jobStatusLabel(job, resumeVersions, applications)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="dashboard-section" aria-labelledby="dashboard-runs">
        <h3 id="dashboard-runs">In-flight runs</h3>
        {inFlightRuns.length === 0 ? (
          <p className="dashboard-empty">
            No runs in progress — start one from a job page.
          </p>
        ) : (
          <ul className="run-list">
            {inFlightRuns.map((run) => {
              const job = jobsById.get(run.job_id);
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
        aria-labelledby="dashboard-applications"
      >
        <h3 id="dashboard-applications">Recent applications</h3>
        {recentApplications.length === 0 ? (
          <p className="dashboard-empty">
            No applications yet — approve a tailored resume on a job to create one.
          </p>
        ) : (
          <ul className="application-list">
            {recentApplications.map((app) => {
              const job = jobsById.get(app.job_id);
              const label = job
                ? `${job.title} — ${job.company}`
                : `Job ${app.job_id}`;
              return (
                <li key={app.id} className="application-list-item">
                  <Link to={`/applications/${app.id}`}>
                    <strong>{label}</strong>
                  </Link>
                  <span className="application-meta">
                    {" "}
                    · {app.status} · submitted{" "}
                    {formatTimestamp(app.submitted_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </section>
  );
}
