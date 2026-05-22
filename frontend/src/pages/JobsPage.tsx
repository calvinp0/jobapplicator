import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listJobs } from "../api";
import type { Job } from "../api";

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listJobs()
      .then((rows) => {
        if (!cancelled) setJobs(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load jobs";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="jobs-page">
        <h2>Jobs</h2>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (jobs === null) {
    return (
      <section className="jobs-page">
        <h2>Jobs</h2>
        <p>Loading jobs…</p>
      </section>
    );
  }

  return (
    <section className="jobs-page">
      <h2>Jobs</h2>
      {jobs.length === 0 ? (
        <p>No confirmed jobs yet.</p>
      ) : (
        <ul className="job-list">
          {jobs.map((job) => (
            <li key={job.id} className="job-list-item">
              <Link to={`/jobs/${job.id}`}>
                <strong>{job.title}</strong> — <span>{job.company}</span>
              </Link>
              {job.location ? <span> · {job.location}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
