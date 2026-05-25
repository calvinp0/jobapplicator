import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  classifyApplicationGmail,
  getApplication,
  getGmailStatus,
  searchApplicationGmail,
} from "../api";
import type {
  Application,
  GmailCandidateEmail,
  GmailClassificationResponse,
  GmailStatusResponse,
} from "../api";
import {
  emailStatusLabel,
  classificationLabel as sharedClassificationLabel,
} from "../lib/workflow";

interface Props {
  application: Application;
  onApplicationChanged: (app: Application) => void;
}

function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const diff = Date.now() - date.getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days} day${days === 1 ? "" : "s"} ago`;
  return date.toLocaleDateString();
}

function describeStatusLine(
  application: Application,
  status: GmailStatusResponse | null,
): string {
  if (status && !status.configured) return "Gmail: Not configured";
  if (status && !status.connected) return "Gmail: Not connected";
  const emailStatus = application.email_status;
  if (emailStatus === "not_watching") {
    return "Gmail: Not watching (submit the application first)";
  }
  if (emailStatus === "watching" && !application.last_gmail_check_at) {
    return "Gmail: Not checked";
  }
  if (emailStatus === "no_match") return "Gmail: No related emails found";
  if (emailStatus === "error") return "Gmail: Last check failed";
  return `Gmail: ${emailStatusLabel(emailStatus)}`;
}

export function GmailEvidence({ application, onApplicationChanged }: Props) {
  const [status, setStatus] = useState<GmailStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<GmailCandidateEmail[] | null>(
    null,
  );
  const [searchQuery, setSearchQuery] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [pendingClassifyId, setPendingClassifyId] = useState<string | null>(
    null,
  );
  const [classifyError, setClassifyError] = useState<string | null>(null);
  // Keyed by message_id so each candidate keeps its own result on screen.
  const [classifications, setClassifications] = useState<
    Record<string, GmailClassificationResponse>
  >({});

  useEffect(() => {
    let cancelled = false;
    getGmailStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Failed to load Gmail status";
        setStatusError(message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSearch() {
    setIsSearching(true);
    setSearchError(null);
    try {
      const result = await searchApplicationGmail(application.id, {
        max_results: 10,
        include_ats_terms: true,
      });
      setCandidates(result.candidates ?? []);
      setSearchQuery(result.gmail_query);
      if (!result.gmail_connected) {
        setSearchError(
          result.message ??
            "Connect Gmail before checking for application emails.",
        );
      }
      // Refresh application so last_gmail_check_at / email_status reflect
      // the result the backend just persisted.
      try {
        const refreshed = await getApplication(application.id);
        onApplicationChanged(refreshed);
      } catch {
        // Non-fatal: search succeeded, only the refresh failed.
      }
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not search Gmail. Try again.";
      setSearchError(message);
    } finally {
      setIsSearching(false);
    }
  }

  async function handleClassify(candidate: GmailCandidateEmail) {
    if (!candidate.message_id) {
      setClassifyError("Cannot classify a candidate without a message id.");
      return;
    }
    setPendingClassifyId(candidate.message_id);
    setClassifyError(null);
    try {
      const result = await classifyApplicationGmail(application.id, candidate);
      setClassifications((prev) => ({
        ...prev,
        [candidate.message_id as string]: result,
      }));
      // Backend may have moved Application.status; refresh so the rest of
      // the page reflects the change.
      try {
        const refreshed = await getApplication(application.id);
        onApplicationChanged(refreshed);
      } catch {
        // Non-fatal.
      }
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not classify this email. Try again or review manually.";
      setClassifyError(message);
    } finally {
      setPendingClassifyId(null);
    }
  }

  const isConnected = status?.connected === true;
  const isConfigured = status?.configured !== false;
  const statusLine = describeStatusLine(application, status);
  const lastChecked = application.last_gmail_check_at
    ? `Checked: ${formatRelative(application.last_gmail_check_at)}`
    : null;

  const latestClassification = application.latest_email_classification;
  const latestSubject = application.latest_email_subject;
  const latestFrom = application.latest_email_from;
  const latestConfidence = application.latest_email_confidence;
  const latestEvidence = application.latest_email_evidence;

  return (
    <section className="gmail-evidence" aria-labelledby="gmail-evidence-heading">
      <h3 id="gmail-evidence-heading">Gmail tracking</h3>

      <p className="gmail-privacy-note">
        Gmail is used read-only for application tracking. JobApplicator does
        not send, delete, archive, or label emails.
      </p>

      <dl className="run-meta gmail-evidence-summary">
        <dt>Gmail status</dt>
        <dd data-testid="gmail-status-line">{statusLine}</dd>
        {lastChecked ? (
          <>
            <dt>Last check</dt>
            <dd>{lastChecked}</dd>
          </>
        ) : null}
        {latestSubject ? (
          <>
            <dt>Latest email</dt>
            <dd>
              {latestSubject}
              {latestFrom ? ` — from ${latestFrom}` : ""}
            </dd>
          </>
        ) : null}
        {latestClassification ? (
          <>
            <dt>Latest classification</dt>
            <dd>
              {sharedClassificationLabel(latestClassification)}
              {typeof latestConfidence === "number" &&
              !Number.isNaN(latestConfidence)
                ? ` · confidence ${latestConfidence.toFixed(2)}`
                : ""}
            </dd>
          </>
        ) : null}
        {latestEvidence ? (
          <>
            <dt>Latest evidence</dt>
            <dd className="gmail-evidence-quote">{latestEvidence}</dd>
          </>
        ) : null}
      </dl>

      {statusError ? (
        <p role="alert" className="error">
          {statusError}
        </p>
      ) : null}

      <div className="gmail-evidence-actions">
        {!isConfigured ? (
          <p
            className="gmail-connect-hint"
            data-testid="gmail-connect-hint"
          >
            Gmail OAuth is not configured.{" "}
            <Link to="/settings">Configure it in Settings</Link> first.
          </p>
        ) : !isConnected ? (
          <p
            className="gmail-connect-hint"
            data-testid="gmail-connect-hint"
          >
            <Link to="/settings">Connect Gmail in Settings</Link> to check
            application emails.
          </p>
        ) : (
          <button
            type="button"
            onClick={handleSearch}
            disabled={isSearching}
            data-testid="gmail-check-button"
          >
            {isSearching
              ? "Checking…"
              : application.last_gmail_check_at
                ? "Check again"
                : "Check Gmail"}
          </button>
        )}
      </div>

      {searchError ? (
        <p role="alert" className="error">
          {searchError}
        </p>
      ) : null}

      {searchQuery ? (
        <p className="gmail-query-line">
          <span className="muted">Query:</span> <code>{searchQuery}</code>
        </p>
      ) : null}

      {candidates !== null ? (
        candidates.length === 0 ? (
          <p className="settings-empty">No related emails found.</p>
        ) : (
          <ul className="gmail-candidate-list">
            {candidates.map((candidate, idx) => {
              const key = candidate.message_id ?? `cand-${idx}`;
              const result = candidate.message_id
                ? classifications[candidate.message_id]
                : undefined;
              const isPending =
                pendingClassifyId !== null &&
                pendingClassifyId === candidate.message_id;
              return (
                <li key={key} className="gmail-candidate-item">
                  <div className="gmail-candidate-row">
                    <strong className="gmail-candidate-subject">
                      {candidate.subject || "(no subject)"}
                    </strong>
                    <span className="gmail-candidate-score">
                      Match score: {candidate.match_score.toFixed(2)}
                    </span>
                  </div>
                  <div className="gmail-candidate-meta">
                    <span>{candidate.from || "Unknown sender"}</span>
                    {candidate.date ? <span> · {candidate.date}</span> : null}
                  </div>
                  {candidate.snippet ? (
                    <p className="gmail-candidate-snippet">
                      {candidate.snippet}
                    </p>
                  ) : null}
                  {candidate.matched_signals.length > 0 ? (
                    <p className="gmail-candidate-signals">
                      Matched signals:{" "}
                      {candidate.matched_signals.join(", ")}
                    </p>
                  ) : null}
                  <div className="gmail-candidate-actions">
                    <button
                      type="button"
                      onClick={() => handleClassify(candidate)}
                      disabled={isPending || !candidate.message_id}
                    >
                      {isPending ? "Classifying…" : "Classify"}
                    </button>
                  </div>
                  {result ? (
                    <div
                      className="gmail-classification-result"
                      data-testid={`gmail-classification-${candidate.message_id}`}
                    >
                      <div className="gmail-classification-row">
                        <span className="gmail-classification-label">
                          Classification:{" "}
                          {sharedClassificationLabel(result.classification)}
                        </span>
                        <span className="gmail-classification-confidence">
                          Confidence: {Math.round(result.confidence * 100)}%
                        </span>
                      </div>
                      <p className="gmail-classification-reason">
                        {result.reason}
                      </p>
                      {result.evidence.length > 0 ? (
                        <ul className="gmail-evidence-list">
                          {result.evidence.map((item, evidenceIdx) => (
                            <li key={evidenceIdx}>
                              <span className="muted">{item.field}:</span>{" "}
                              <q>{item.text}</q>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {result.application_status_changed ? (
                        <p className="gmail-status-changed">
                          Application status updated to{" "}
                          <strong>{result.application_status}</strong>.
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )
      ) : null}

      {classifyError ? (
        <p role="alert" className="error">
          {classifyError}
        </p>
      ) : null}
    </section>
  );
}
