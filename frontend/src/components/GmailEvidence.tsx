import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  classifyApplicationGmail,
  getApplication,
  getGmailStatus,
  linkGmailEmail,
  listGmailCandidates,
  listLinkedGmailEmails,
  searchApplicationGmail,
  unlinkGmailEmail,
} from "../api";
import type {
  Application,
  EmailLink,
  GmailCandidateEmail,
  GmailClassificationResponse,
  GmailManualCandidate,
  GmailStatusResponse,
  ManualLinkClassification,
} from "../api";
import {
  emailStatusLabel,
  classificationLabel as sharedClassificationLabel,
} from "../lib/workflow";

interface Props {
  application: Application;
  onApplicationChanged: (app: Application) => void;
}

interface LinkAction {
  label: string;
  classification: ManualLinkClassification;
}

const LINK_ACTIONS: LinkAction[] = [
  { label: "Link as confirmation", classification: "submission_confirmation" },
  { label: "Link as rejection", classification: "rejection" },
  { label: "Link as interview", classification: "interview_request" },
  { label: "Link as assessment", classification: "assessment" },
  { label: "Link as neutral/update", classification: "application_update" },
];

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
  if (emailStatus === "needs_review") {
    return "Gmail: No strong match — review possible emails";
  }
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

  // Manual-linking surface (task 093).
  const [manualCandidates, setManualCandidates] = useState<
    GmailManualCandidate[] | null
  >(null);
  const [manualStrongCount, setManualStrongCount] = useState(0);
  const [manualPossibleCount, setManualPossibleCount] = useState(0);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualQueryInput, setManualQueryInput] = useState("");
  const [pendingLinkId, setPendingLinkId] = useState<string | null>(null);
  const [linkedEmails, setLinkedEmails] = useState<EmailLink[]>([]);
  const [pendingUnlinkId, setPendingUnlinkId] = useState<string | null>(null);

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

  useEffect(() => {
    let cancelled = false;
    listLinkedGmailEmails(application.id)
      .then((resp) => {
        if (!cancelled) setLinkedEmails(resp.linked_emails ?? []);
      })
      .catch(() => {
        // Non-fatal; the linked-emails section just stays empty.
      });
    return () => {
      cancelled = true;
    };
  }, [application.id]);

  async function refreshApplication() {
    try {
      const refreshed = await getApplication(application.id);
      onApplicationChanged(refreshed);
    } catch {
      // Non-fatal.
    }
  }

  async function refreshLinkedEmails() {
    try {
      const resp = await listLinkedGmailEmails(application.id);
      setLinkedEmails(resp.linked_emails ?? []);
    } catch {
      // Non-fatal.
    }
  }

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
      await refreshApplication();
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

  async function loadCandidates(opts: { query?: string } = {}) {
    setIsLoadingCandidates(true);
    setManualError(null);
    try {
      const result = await listGmailCandidates(application.id, {
        query: opts.query ?? null,
        include_low_confidence: true,
        max_results: 20,
      });
      setManualCandidates(result.candidates ?? []);
      setManualStrongCount(result.strong_count);
      setManualPossibleCount(result.possible_count);
      setSearchQuery(result.query_used);
      if (!result.gmail_connected) {
        setManualError(
          result.message ?? "Connect Gmail to review application emails.",
        );
      }
      await refreshApplication();
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not load Gmail candidates. Try again.";
      setManualError(message);
    } finally {
      setIsLoadingCandidates(false);
    }
  }

  async function handleManualSearchSubmit(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const trimmed = manualQueryInput.trim();
    if (!trimmed) return;
    await loadCandidates({ query: trimmed });
  }

  async function handleLinkCandidate(
    candidate: GmailManualCandidate,
    classification: ManualLinkClassification,
  ) {
    if (!candidate.message_id) {
      setManualError("Cannot link a candidate without a message id.");
      return;
    }
    setPendingLinkId(candidate.message_id);
    setManualError(null);
    try {
      await linkGmailEmail(application.id, {
        message_id: candidate.message_id,
        thread_id: candidate.thread_id,
        classification,
        sender: candidate.from,
        subject: candidate.subject,
        snippet: candidate.snippet,
        match_score: candidate.match_score,
        user_confirmed: true,
      });
      await Promise.all([refreshApplication(), refreshLinkedEmails()]);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not link this email. Try again.";
      setManualError(message);
    } finally {
      setPendingLinkId(null);
    }
  }

  async function handleNotRelated(candidate: GmailManualCandidate) {
    // "Not related" just drops the candidate from the local view — no
    // backend call is made because we never want to persist a "user
    // dismissed this" row in the database.
    if (!manualCandidates) return;
    setManualCandidates(
      manualCandidates.filter((c) => c.message_id !== candidate.message_id),
    );
  }

  async function handleUnlink(link: EmailLink) {
    setPendingUnlinkId(link.id);
    setManualError(null);
    try {
      await unlinkGmailEmail(application.id, link.id);
      await Promise.all([refreshApplication(), refreshLinkedEmails()]);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Could not unlink this email. Try again.";
      setManualError(message);
    } finally {
      setPendingUnlinkId(null);
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
      await refreshApplication();
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

  const hasStrongCandidate =
    candidates !== null &&
    candidates.some((c) => (c.match_score ?? 0) >= 0.7);
  const noStrongCandidates =
    candidates !== null && candidates.length > 0 && !hasStrongCandidate;

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
          <>
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
            <button
              type="button"
              onClick={() => loadCandidates()}
              disabled={isLoadingCandidates}
              data-testid="gmail-review-candidates-button"
            >
              {isLoadingCandidates
                ? "Loading possible emails…"
                : "Review possible emails"}
            </button>
          </>
        )}
      </div>

      {isConnected ? (
        <form
          className="gmail-manual-search"
          onSubmit={handleManualSearchSubmit}
          data-testid="gmail-manual-search-form"
        >
          <label htmlFor="gmail-manual-query" className="muted">
            Search Gmail manually
          </label>
          <input
            id="gmail-manual-query"
            type="text"
            value={manualQueryInput}
            onChange={(e) => setManualQueryInput(e.target.value)}
            placeholder="e.g. Infinity Labs"
            data-testid="gmail-manual-query-input"
          />
          <button
            type="submit"
            disabled={
              isLoadingCandidates || manualQueryInput.trim().length === 0
            }
          >
            Search
          </button>
        </form>
      ) : null}

      {searchError ? (
        <p role="alert" className="error">
          {searchError}
        </p>
      ) : null}
      {manualError ? (
        <p role="alert" className="error">
          {manualError}
        </p>
      ) : null}

      {searchQuery ? (
        <p className="gmail-query-line">
          <span className="muted">Query:</span> <code>{searchQuery}</code>
        </p>
      ) : null}

      {candidates !== null ? (
        candidates.length === 0 ? (
          <div className="gmail-empty-state">
            <p className="settings-empty">No related emails found.</p>
            <p className="muted">
              Try a manual Gmail search above, or click <em>Review possible
              emails</em> to surface low-confidence candidates.
            </p>
          </div>
        ) : (
          <>
            {noStrongCandidates ? (
              <p
                className="gmail-needs-review-banner"
                data-testid="gmail-needs-review-banner"
              >
                No strong Gmail match found. Possible related emails are
                available for review.
              </p>
            ) : null}
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
          </>
        )
      ) : null}

      {/* Manual-linking candidate list (task 093) */}
      {manualCandidates !== null ? (
        manualCandidates.length === 0 ? (
          <p
            className="settings-empty"
            data-testid="gmail-manual-empty"
          >
            No related Gmail emails found. Try a manual Gmail search.
          </p>
        ) : (
          <div data-testid="gmail-manual-candidates">
            {manualStrongCount === 0 && manualPossibleCount > 0 ? (
              <p
                className="gmail-needs-review-banner"
                data-testid="gmail-manual-needs-review"
              >
                No strong match found. Review possible Gmail emails.
              </p>
            ) : null}
            <ul className="gmail-candidate-list">
              {manualCandidates.map((candidate, idx) => {
                const key = candidate.message_id ?? `mcand-${idx}`;
                const isLinking =
                  pendingLinkId !== null &&
                  pendingLinkId === candidate.message_id;
                return (
                  <li
                    key={key}
                    className="gmail-candidate-item"
                    data-testid={`gmail-manual-candidate-${candidate.message_id}`}
                  >
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
                    {candidate.classification_guess ? (
                      <p className="gmail-candidate-guess">
                        Guess:{" "}
                        {sharedClassificationLabel(
                          candidate.classification_guess,
                        )}
                      </p>
                    ) : null}
                    <div className="gmail-candidate-actions">
                      {LINK_ACTIONS.map((action) => (
                        <button
                          key={action.classification}
                          type="button"
                          onClick={() =>
                            handleLinkCandidate(candidate, action.classification)
                          }
                          disabled={isLinking || !candidate.message_id}
                          data-testid={`gmail-link-${action.classification}-${candidate.message_id}`}
                        >
                          {isLinking ? "Linking…" : action.label}
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => handleNotRelated(candidate)}
                        disabled={isLinking}
                      >
                        Not related
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )
      ) : null}

      {classifyError ? (
        <p role="alert" className="error">
          {classifyError}
        </p>
      ) : null}

      {linkedEmails.length > 0 ? (
        <div
          className="gmail-linked-emails"
          data-testid="gmail-linked-emails"
        >
          <h4>Email evidence</h4>
          <ul className="gmail-linked-emails-list">
            {linkedEmails.map((link) => (
              <li
                key={link.id}
                className="gmail-linked-email-item"
                data-testid={`gmail-linked-email-${link.id}`}
              >
                <div className="gmail-candidate-row">
                  <strong>{link.subject || "(no subject)"}</strong>
                  {link.linked_by_user ? (
                    <span className="muted">Linked manually</span>
                  ) : null}
                </div>
                <div className="gmail-candidate-meta">
                  <span>{link.sender || "Unknown sender"}</span>
                  {link.classified_status ? (
                    <span>
                      {" "}
                      ·{" "}
                      {sharedClassificationLabel(link.classified_status)}
                    </span>
                  ) : null}
                </div>
                {link.snippet ? (
                  <p className="gmail-candidate-snippet">{link.snippet}</p>
                ) : null}
                <div className="gmail-candidate-actions">
                  <button
                    type="button"
                    onClick={() => handleUnlink(link)}
                    disabled={pendingUnlinkId === link.id}
                  >
                    {pendingUnlinkId === link.id ? "Unlinking…" : "Unlink"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
