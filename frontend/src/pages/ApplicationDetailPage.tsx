import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  createApplicationEvent,
  getApplication,
  getJob,
  getResumeVersion,
  listApplicationEvents,
  submitApplication,
} from "../api";
import type {
  Application,
  ApplicationEvent,
  Job,
  ResumeVersion,
} from "../api";
import { draftLabel, draftStatusLabel } from "../lib/workflow";

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function gatingReason(
  application: Application,
  version: ResumeVersion | null,
): string | null {
  if (application.status === "submitted") return "Already submitted.";
  if (!application.resume_version_id) return "Link an approved resume version first.";
  if (!version || !version.approved_at)
    return "Linked resume version is not yet approved.";
  return null;
}

export function ApplicationDetailPage() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const [application, setApplication] = useState<Application | null>(null);
  const [events, setEvents] = useState<ApplicationEvent[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [eventType, setEventType] = useState("");
  const [eventNotes, setEventNotes] = useState("");
  const [isAddingEvent, setIsAddingEvent] = useState(false);
  const [eventError, setEventError] = useState<string | null>(null);

  useEffect(() => {
    if (!applicationId) return;
    let cancelled = false;
    getApplication(applicationId)
      .then(async (app) => {
        if (cancelled) return;
        setApplication(app);
        const [eventList, jobRow, versionRow] = await Promise.all([
          listApplicationEvents(applicationId),
          getJob(app.job_id),
          app.resume_version_id
            ? getResumeVersion(app.resume_version_id)
            : Promise.resolve(null),
        ]);
        if (cancelled) return;
        setEvents(eventList);
        setJob(jobRow);
        setVersion(versionRow);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load application";
        setLoadError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [applicationId]);

  async function refreshEvents() {
    if (!applicationId) return;
    const rows = await listApplicationEvents(applicationId);
    setEvents(rows);
  }

  async function handleMarkSubmitted() {
    if (!applicationId || !application) return;
    setIsSubmitting(true);
    setActionError(null);
    try {
      const updated = await submitApplication(applicationId);
      setApplication(updated);
      await refreshEvents();
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to mark submitted";
      setActionError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAddEvent(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!applicationId) return;
    if (!eventType.trim()) {
      setEventError("Event type is required.");
      return;
    }
    setIsAddingEvent(true);
    setEventError(null);
    try {
      await createApplicationEvent(applicationId, {
        event_type: eventType.trim(),
        notes: eventNotes.trim() || null,
      });
      setEventType("");
      setEventNotes("");
      await refreshEvents();
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to record event";
      setEventError(message);
    } finally {
      setIsAddingEvent(false);
    }
  }

  if (loadError) {
    return (
      <section className="application-detail">
        <h2>Application</h2>
        <p role="alert" className="error">
          {loadError}
        </p>
      </section>
    );
  }

  if (!application || events === null) {
    return (
      <section className="application-detail">
        <h2>Application</h2>
        <p>Loading…</p>
      </section>
    );
  }

  const reason = gatingReason(application, version);
  const submitDisabled = reason !== null || isSubmitting;

  const heading = job
    ? `Application — ${job.title} — ${job.company}`
    : "Application";
  const submitted = application.status === "submitted";
  const badge = {
    label: submitted
      ? "Submitted"
      : application.status.charAt(0).toUpperCase() +
        application.status.slice(1),
    variant: submitted ? "submitted" : "default",
  };

  return (
    <section className="application-detail">
      <h2>
        {heading}
        <span className={`status-badge status-badge-${badge.variant}`}>
          {badge.label}
        </span>
      </h2>
      <dl className="run-meta">
        <dt>Status</dt>
        <dd>{application.status}</dd>
        <dt>Submitted</dt>
        <dd>{formatTimestamp(application.submitted_at)}</dd>
        <dt>Job</dt>
        <dd>
          {job ? (
            <Link to={`/jobs/${application.job_id}`}>
              {job.title} — {job.company}
            </Link>
          ) : (
            "—"
          )}
        </dd>
        <dt>Resume version</dt>
        <dd>
          {application.resume_version_id && version ? (
            <Link
              to={`/resume-versions/${application.resume_version_id}`}
            >
              {`${draftLabel(version.version_number - 1)} (${draftStatusLabel(
                version.approved_at,
              )})`}
            </Link>
          ) : (
            "—"
          )}
        </dd>
      </dl>

      <div className="run-actions">
        <button
          type="button"
          onClick={handleMarkSubmitted}
          disabled={submitDisabled}
        >
          {isSubmitting ? "Submitting…" : "Mark Submitted"}
        </button>
        {reason ? <span className="application-gating">{reason}</span> : null}
      </div>

      {actionError ? (
        <p role="alert" className="error">
          {actionError}
        </p>
      ) : null}

      <h3>Timeline</h3>
      {events.length === 0 ? (
        <p className="settings-empty">No events yet.</p>
      ) : (
        <ul className="application-event-list">
          {events.map((event) => (
            <li key={event.id} className="application-event-item">
              <span className="application-event-time">
                {formatTimestamp(event.event_time)}
              </span>
              <strong>{event.event_type}</strong>
              {event.source ? (
                <span className="application-event-source">
                  {" "}
                  · {event.source}
                </span>
              ) : null}
              {event.notes ? (
                <p className="application-event-notes">{event.notes}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <h3>Record event</h3>
      <form onSubmit={handleAddEvent} noValidate>
        <label className="field">
          <span>Event type</span>
          <input
            type="text"
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            placeholder="e.g. response_received"
            required
          />
        </label>
        <label className="field">
          <span>Notes</span>
          <textarea
            value={eventNotes}
            onChange={(e) => setEventNotes(e.target.value)}
            rows={3}
          />
        </label>
        {eventError ? (
          <p role="alert" className="error">
            {eventError}
          </p>
        ) : null}
        <button type="submit" disabled={isAddingEvent}>
          {isAddingEvent ? "Adding…" : "Add event"}
        </button>
      </form>

      <details className="advanced-details">
        <summary>Advanced details</summary>
        <dl className="run-meta">
          <dt>Application id</dt>
          <dd>
            <code>{application.id}</code>
          </dd>
          {!job ? (
            <>
              <dt>Job id</dt>
              <dd>
                <code>{application.job_id}</code>
              </dd>
            </>
          ) : null}
          {application.resume_version_id && !version ? (
            <>
              <dt>Resume version id</dt>
              <dd>
                <code>{application.resume_version_id}</code>
              </dd>
            </>
          ) : null}
          <dt>Created</dt>
          <dd>{formatTimestamp(application.created_at)}</dd>
          <dt>Updated</dt>
          <dd>{formatTimestamp(application.updated_at)}</dd>
        </dl>
      </details>
    </section>
  );
}
