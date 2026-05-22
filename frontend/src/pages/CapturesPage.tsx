import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listCaptures } from "../api";
import type { JobCapture } from "../api";

export function CapturesPage() {
  const [captures, setCaptures] = useState<JobCapture[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCaptures()
      .then((rows) => {
        if (!cancelled) setCaptures(rows);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load captures";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="captures-page">
        <h2>Captures</h2>
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (captures === null) {
    return (
      <section className="captures-page">
        <h2>Captures</h2>
        <p>Loading captures…</p>
      </section>
    );
  }

  const pending = captures.filter((c) => !c.user_confirmed);

  return (
    <section className="captures-page">
      <h2>Pending Captures</h2>
      {pending.length === 0 ? (
        <p>No pending captures.</p>
      ) : (
        <ul className="capture-list">
          {pending.map((capture) => (
            <li key={capture.id} className="capture-list-item">
              <Link to={`/captures/${capture.id}`}>
                <strong>{capture.title ?? "(no title)"}</strong>
                {" — "}
                <span>{capture.company ?? "(no company)"}</span>
              </Link>
              {capture.location ? (
                <span className="capture-meta"> · {capture.location}</span>
              ) : null}
              <div className="capture-meta">
                {capture.source_platform} · {capture.capture_method}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
