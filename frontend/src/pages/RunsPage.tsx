import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listRuns } from "../api";
import type { ClaudeRun } from "../api";

export function RunsPage() {
  const [runs, setRuns] = useState<ClaudeRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listRuns()
      .then((rows) => {
        if (!cancelled) setRuns(rows);
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
        <h2>Runs</h2>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (runs === null) {
    return (
      <section className="runs-page">
        <h2>Runs</h2>
        <p>Loading runs…</p>
      </section>
    );
  }

  const sorted = [...runs].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );

  return (
    <section className="runs-page">
      <h2>Runs</h2>
      {sorted.length === 0 ? (
        <p>No runs yet.</p>
      ) : (
        <ul className="run-list">
          {sorted.map((run) => (
            <li key={run.id} className="run-list-item">
              <Link to={`/runs/${run.id}`}>
                <strong>{run.id}</strong>
              </Link>
              <span className="run-meta-inline">
                {" "}
                · {run.status} ·{" "}
                {new Date(run.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
