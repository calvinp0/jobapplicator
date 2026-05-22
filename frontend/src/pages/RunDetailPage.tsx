import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, getRun } from "../api";
import type { ClaudeRun } from "../api";

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<ClaudeRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    getRun(runId)
      .then((r) => {
        if (!cancelled) setRun(r);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load run";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) {
    return (
      <section className="run-detail">
        <h2>Run</h2>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (!run) {
    return (
      <section className="run-detail">
        <h2>Run</h2>
        <p>Loading…</p>
      </section>
    );
  }

  return (
    <section className="run-detail">
      <h2>Run {run.id}</h2>
      <dl className="run-meta">
        <dt>Status</dt>
        <dd>{run.status}</dd>
        <dt>Run directory</dt>
        <dd>{run.run_dir}</dd>
        <dt>Created</dt>
        <dd>{new Date(run.created_at).toLocaleString()}</dd>
      </dl>
    </section>
  );
}
