import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  createApplicationEmailLink,
  createApplicationEvent,
  getApplication,
  getJob,
  getResumeVersion,
  listApplicationEmailLinks,
  listApplicationEvents,
  submitApplication,
} from "../api";
import type {
  Application,
  ApplicationEvent,
  EmailLink,
  Job,
  ResumeVersion,
} from "../api";
import {
  draftLabel,
  draftStatusLabel,
  timelineStageLabel,
  timelineStageVariant,
} from "../lib/workflow";
import { GmailEvidence } from "../components/GmailEvidence";

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

const APPLICATION_STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  generated: "In progress",
  approved: "Approved",
  submitted: "Sent",
  response_received: "Response received",
  rejected: "Rejected",
  interview: "Interview",
  offer: "Offer",
  withdrawn: "Withdrawn",
};

function applicationStatusLabel(status: string): string {
  return APPLICATION_STATUS_LABELS[status] ?? status;
}

const EMAIL_CLASSIFICATION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "confirmation", label: "Confirmation" },
  { value: "rejection", label: "Rejection" },
  { value: "next_step", label: "Next step" },
  { value: "offer", label: "Offer" },
  { value: "other", label: "Other" },
];

const EMAIL_CLASSIFICATION_LABELS: Record<string, string> =
  EMAIL_CLASSIFICATION_OPTIONS.reduce<Record<string, string>>(
    (acc, { value, label }) => {
      acc[value] = label;
      return acc;
    },
    {},
  );

function classificationLabel(value: string | null): string {
  if (!value) return "Unclassified";
  return EMAIL_CLASSIFICATION_LABELS[value] ?? value;
}

function newManualMessageId(): string {
  return `manual:${crypto.randomUUID()}`;
}

function datetimeLocalToIso(value: string): string | null {
  if (!value.trim()) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function gatingReason(
  application: Application,
  version: ResumeVersion | null,
): string | null {
  if (application.status === "submitted") return "Already sent.";
  if (!application.resume_version_id)
    return "Pick an approved draft on the job page first.";
  if (!version || !version.approved_at)
    return "This draft has not been approved yet. Approve it on the job page first.";
  return null;
}

export function ApplicationDetailPage() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const [application, setApplication] = useState<Application | null>(null);
  const [events, setEvents] = useState<ApplicationEvent[] | null>(null);
  const [emailLinks, setEmailLinks] = useState<EmailLink[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [emailListError, setEmailListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [eventType, setEventType] = useState("");
  const [eventNotes, setEventNotes] = useState("");
  const [isAddingEvent, setIsAddingEvent] = useState(false);
  const [eventError, setEventError] = useState<string | null>(null);

  const [emailMessageId, setEmailMessageId] = useState<string>(() =>
    newManualMessageId(),
  );
  const [emailClassifiedStatus, setEmailClassifiedStatus] =
    useState<string>("confirmation");
  const [emailSender, setEmailSender] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailReceivedAt, setEmailReceivedAt] = useState("");
  const [emailConfidence, setEmailConfidence] = useState("");
  const [isAddingEmail, setIsAddingEmail] = useState(false);
  const [emailCreateError, setEmailCreateError] = useState<string | null>(null);

  useEffect(() => {
    if (!applicationId) return;
    let cancelled = false;
    getApplication(applicationId)
      .then(async (app) => {
        if (cancelled) return;
        setApplication(app);
        const [eventList, jobRow, versionRow, links] = await Promise.all([
          listApplicationEvents(applicationId),
          getJob(app.job_id),
          app.resume_version_id
            ? getResumeVersion(app.resume_version_id)
            : Promise.resolve(null),
          listApplicationEmailLinks(applicationId).catch((err: unknown) => {
            if (!cancelled) {
              const message =
                err instanceof ApiError
                  ? err.message
                  : "Failed to load email evidence";
              setEmailListError(message);
            }
            return [] as EmailLink[];
          }),
        ]);
        if (cancelled) return;
        setEvents(eventList);
        setJob(jobRow);
        setVersion(versionRow);
        setEmailLinks(links);
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
        err instanceof ApiError ? err.message : "Failed to record send";
      setActionError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAddEmail(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!applicationId) return;
    const trimmedId = emailMessageId.trim();
    if (!trimmedId) {
      setEmailCreateError("Gmail message id is required.");
      return;
    }
    let confidenceValue: number | null = null;
    if (emailConfidence.trim()) {
      const parsed = Number(emailConfidence);
      if (Number.isNaN(parsed)) {
        setEmailCreateError("Confidence must be a number.");
        return;
      }
      confidenceValue = parsed;
    }
    setIsAddingEmail(true);
    setEmailCreateError(null);
    try {
      await createApplicationEmailLink(applicationId, {
        gmail_message_id: trimmedId,
        classified_status: emailClassifiedStatus,
        sender: emailSender.trim() || null,
        subject: emailSubject.trim() || null,
        received_at: datetimeLocalToIso(emailReceivedAt),
        confidence: confidenceValue,
      });
      const [updatedApp, links] = await Promise.all([
        getApplication(applicationId),
        listApplicationEmailLinks(applicationId),
      ]);
      setApplication(updatedApp);
      setEmailLinks(links);
      setEmailListError(null);
      setEmailMessageId(newManualMessageId());
      setEmailClassifiedStatus("confirmation");
      setEmailSender("");
      setEmailSubject("");
      setEmailReceivedAt("");
      setEmailConfidence("");
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Failed to record email";
      setEmailCreateError(message);
    } finally {
      setIsAddingEmail(false);
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

  if (!application || events === null || emailLinks === null) {
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
  const badge = {
    label: timelineStageLabel(application.timeline_stage),
    variant: timelineStageVariant(application.timeline_stage),
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
        <dd>{applicationStatusLabel(application.status)}</dd>
        <dt>Sent at</dt>
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
          {isSubmitting ? "Recording…" : "I've sent it"}
        </button>
        {reason ? <span className="application-gating">{reason}</span> : null}
      </div>

      {actionError ? (
        <p role="alert" className="error">
          {actionError}
        </p>
      ) : null}

      <GmailEvidence
        application={application}
        onApplicationChanged={(updated) => setApplication(updated)}
      />

      <h3>Email evidence</h3>
      {emailListError ? (
        <p role="alert" className="error">
          {emailListError}
        </p>
      ) : null}
      {emailLinks.length === 0 ? (
        <p className="settings-empty">
          No emails recorded yet. The Gmail integration is not enabled — you
          can record an email by hand.
        </p>
      ) : (
        <ul className="email-link-list">
          {emailLinks.map((link) => (
            <li key={link.id} className="email-link-item">
              <div className="email-link-row">
                <span
                  className={`status-badge status-badge-${
                    link.classified_status ?? "default"
                  }`}
                >
                  {classificationLabel(link.classified_status)}
                </span>
                <strong className="email-link-subject">
                  {link.subject || "(no subject)"}
                </strong>
              </div>
              <div className="email-link-meta">
                <span>{link.sender || "Unknown sender"}</span>
                <span> · {formatTimestamp(link.received_at)}</span>
                {link.confidence !== null ? (
                  <span> · confidence {link.confidence.toFixed(2)}</span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <h3>Record email</h3>
      <form onSubmit={handleAddEmail} noValidate>
        <label className="field">
          <span>Gmail message id</span>
          <input
            type="text"
            value={emailMessageId}
            onChange={(e) => setEmailMessageId(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span>Classification</span>
          <select
            value={emailClassifiedStatus}
            onChange={(e) => setEmailClassifiedStatus(e.target.value)}
          >
            {EMAIL_CLASSIFICATION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Sender</span>
          <input
            type="text"
            value={emailSender}
            onChange={(e) => setEmailSender(e.target.value)}
            placeholder="e.g. recruiting@acme.com"
          />
        </label>
        <label className="field">
          <span>Subject</span>
          <input
            type="text"
            value={emailSubject}
            onChange={(e) => setEmailSubject(e.target.value)}
            placeholder="e.g. Your application to Acme"
          />
        </label>
        <label className="field">
          <span>Received at</span>
          <input
            type="datetime-local"
            value={emailReceivedAt}
            onChange={(e) => setEmailReceivedAt(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Confidence (optional)</span>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={emailConfidence}
            onChange={(e) => setEmailConfidence(e.target.value)}
          />
        </label>
        {emailCreateError ? (
          <p role="alert" className="error">
            {emailCreateError}
          </p>
        ) : null}
        <button type="submit" disabled={isAddingEmail}>
          {isAddingEmail ? "Recording…" : "Record email"}
        </button>
      </form>

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
