import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listCaptures } from "../api";
import type { JobCapture } from "../api";
import { EmptyState, PageHeader, StatusBadge } from "../components/ui";

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
        <PageHeader
          title="Pending Captures"
          description="Jobs the extension has captured but not yet confirmed."
        />
        <p role="alert" className="error">
          {error}
        </p>
      </section>
    );
  }

  if (captures === null) {
    return (
      <section className="captures-page">
        <PageHeader
          title="Pending Captures"
          description="Jobs the extension has captured but not yet confirmed."
        />
        <p>Loading captures…</p>
      </section>
    );
  }

  const pending = captures.filter((c) => !c.user_confirmed);

  return (
    <section className="captures-page">
      <PageHeader
        title="Pending Captures"
        description="Jobs the extension has captured but not yet confirmed."
        meta={
          <p className="page-subtitle" data-testid="captures-summary">
            {pending.length === 0
              ? "Nothing waiting on you."
              : `${pending.length} pending capture${
                  pending.length === 1 ? "" : "s"
                } · ${captures.length} total`}
          </p>
        }
      />
      {pending.length === 0 ? (
        <EmptyState
          title="No pending captures."
          description="Capture a job from the browser extension and it will land here for confirmation."
        />
      ) : (
        <ul className="capture-list">
          {pending.map((capture) => (
            <li key={capture.id} className="capture-list-item">
              <div className="capture-list-item-row">
                <Link to={`/captures/${capture.id}`}>
                  <strong>{capture.title ?? "(no title)"}</strong>
                  {" — "}
                  <span>{capture.company ?? "(no company)"}</span>
                </Link>
                <StatusBadge variant="pending">Pending</StatusBadge>
              </div>
              {capture.location ? (
                <span className="capture-meta">{capture.location}</span>
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
