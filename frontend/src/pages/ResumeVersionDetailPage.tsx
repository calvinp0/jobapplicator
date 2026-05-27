import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  approveResumeVersion,
  getJob,
  getResumeVersion,
  getRun,
  getRunRecruiterReview,
  listEvidenceSources,
  listMasterResumes,
  openResumeVersionFile,
  submitRevisionFeedback,
} from "../api";
import type {
  EvidenceSource,
  Job,
  RecruiterReview,
  ResumeVersion,
} from "../api";
import { draftLabel, draftStatusLabel } from "../lib/workflow";
import { extractApiDetail } from "../lib/api-errors";

const COMMON_ASK_OPTIONS: { key: string; label: string }[] = [
  { key: "shorten", label: "Shorten" },
  { key: "reorder_sections", label: "Reorder sections" },
  { key: "emphasize_x_over_y", label: "Emphasize X over Y" },
];

function truncateHash(hash: string | null): string {
  if (!hash) return "—";
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function ResumeVersionDetailPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const navigate = useNavigate();
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [masterResumeName, setMasterResumeName] = useState<string | null>(null);
  const [evidenceSources, setEvidenceSources] = useState<EvidenceSource[]>([]);
  const [recruiterReview, setRecruiterReview] =
    useState<RecruiterReview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);
  const [isOpening, setIsOpening] = useState(false);
  const [revisionFormOpen, setRevisionFormOpen] = useState(false);
  const [feedbackMarkdown, setFeedbackMarkdown] = useState("");
  const [selectedFlags, setSelectedFlags] = useState<Record<string, boolean>>(
    {},
  );
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  useEffect(() => {
    if (!versionId) return;
    let cancelled = false;
    getResumeVersion(versionId)
      .then((v) => {
        if (cancelled) return;
        setVersion(v);
        // Job and provenance lookups are best-effort — the page still
        // renders the core surface if any of these endpoints are
        // unavailable. Each is fired independently so a single failure
        // doesn't cascade.
        try {
          getJob(v.job_id)
            .then((j) => {
              if (!cancelled && j) setJob(j);
            })
            .catch(() => {});
        } catch {
          /* getJob may be undefined in some test mocks */
        }
        try {
          listMasterResumes()
            .then((rows) => {
              if (cancelled) return;
              const match = rows.find((r) => r.id === v.master_resume_id);
              if (match) setMasterResumeName(match.name);
            })
            .catch(() => {});
        } catch {
          /* listMasterResumes may be undefined in some test mocks */
        }
        if (v.claude_run_id) {
          // The recruiter review lives under the draft's source run. The
          // endpoint reports available=false when the file has not been
          // written yet, so the catch block only fires on transport
          // errors — not on a legitimately absent review file.
          try {
            getRunRecruiterReview(v.claude_run_id)
              .then((review) => {
                if (!cancelled) setRecruiterReview(review);
              })
              .catch(() => {});
          } catch {
            /* getRunRecruiterReview may be undefined in some test mocks */
          }
          try {
            getRun(v.claude_run_id)
              .then((run) => {
                if (cancelled) return;
                const ids = run.evidence_source_ids ?? [];
                if (ids.length === 0) return;
                try {
                  listEvidenceSources()
                    .then((all) => {
                      if (cancelled) return;
                      const byId = new Map(all.map((s) => [s.id, s]));
                      const matched = ids
                        .map((id) => byId.get(id))
                        .filter((s): s is EvidenceSource => Boolean(s));
                      setEvidenceSources(matched);
                    })
                    .catch(() => {});
                } catch {
                  /* listEvidenceSources may be undefined */
                }
              })
              .catch(() => {});
          } catch {
            /* getRun may be undefined */
          }
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : "Failed to load resume draft";
        setLoadError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  async function handleApprove() {
    if (!versionId || !version || version.approved_at) return;
    setIsApproving(true);
    setActionError(null);
    try {
      const updated = await approveResumeVersion(versionId);
      setVersion(updated);
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsApproving(false);
    }
  }

  async function handleSubmitRevisionFeedback(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    if (!versionId) return;
    const trimmed = feedbackMarkdown.trim();
    if (!trimmed) return;
    setIsSubmittingFeedback(true);
    setActionError(null);
    const activeFlags = Object.entries(selectedFlags)
      .filter(([, on]) => on)
      .reduce<Record<string, boolean>>((acc, [key]) => {
        acc[key] = true;
        return acc;
      }, {});
    const body =
      Object.keys(activeFlags).length > 0
        ? { feedback_markdown: trimmed, structured_flags: activeFlags }
        : { feedback_markdown: trimmed };
    try {
      const feedback = await submitRevisionFeedback(versionId, body);
      if (feedback.followup_claude_run_id) {
        navigate(`/runs/${feedback.followup_claude_run_id}`);
      }
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsSubmittingFeedback(false);
    }
  }

  async function handleOpenDocx() {
    if (!versionId || !version || !version.docx_path) return;
    setIsOpening(true);
    setActionError(null);
    try {
      await openResumeVersionFile(versionId);
    } catch (err: unknown) {
      setActionError(extractApiDetail(err));
    } finally {
      setIsOpening(false);
    }
  }

  if (loadError) {
    return (
      <section className="resume-version-detail">
        <h2>Resume draft</h2>
        <p role="alert" className="error">
          {loadError}
        </p>
      </section>
    );
  }

  if (!version) {
    return (
      <section className="resume-version-detail">
        <h2>Resume draft</h2>
        <p>Loading…</p>
      </section>
    );
  }

  const approved = version.approved_at !== null;
  const draftName = draftLabel(version.version_number - 1);
  const statusLabel = draftStatusLabel(version.approved_at);
  const badgeVariant = approved ? "approved" : "draft";
  const heading = job
    ? `${draftName} for ${job.title} — ${job.company}`
    : draftName;

  return (
    <section className="resume-version-detail">
      <h2>
        {heading}
        <span className={`status-badge status-badge-${badgeVariant}`}>
          {statusLabel}
        </span>
      </h2>
      <dl className="run-meta">
        <dt>Draft</dt>
        <dd>{draftName}</dd>
        <dt>Job</dt>
        <dd>
          {job ? (
            <Link to={`/jobs/${version.job_id}`}>
              {job.title} — {job.company}
            </Link>
          ) : (
            <Link to={`/jobs/${version.job_id}`}>{version.job_id}</Link>
          )}
        </dd>
        <dt>Base master resume</dt>
        <dd>{masterResumeName ?? "—"}</dd>
        <dt>Original evidence sources</dt>
        <dd>
          {evidenceSources.length === 0
            ? "None"
            : `${evidenceSources.length} (${evidenceSources
                .map((s) => s.name)
                .join(", ")})`}
        </dd>
        <dt>Source</dt>
        <dd>{version.source}</dd>
        <dt>Created</dt>
        <dd>{formatTimestamp(version.created_at)}</dd>
        <dt>Approved</dt>
        <dd>
          {version.approved_at
            ? `Approved on ${formatTimestamp(version.approved_at)}`
            : "Not approved"}
        </dd>
      </dl>

      <div className="run-actions">
        <button
          type="button"
          onClick={handleOpenDocx}
          disabled={!version.docx_path || isOpening}
        >
          {isOpening ? "Opening…" : "Open draft file"}
        </button>
        {approved ? (
          <span className="approved-indicator" aria-label="Draft approved">
            Approved ✓
          </span>
        ) : (
          <>
            <button
              type="button"
              onClick={handleApprove}
              disabled={isApproving}
            >
              {isApproving ? "Approving…" : "Approve draft"}
            </button>
            <button
              type="button"
              onClick={() => setRevisionFormOpen((open) => !open)}
              aria-expanded={revisionFormOpen}
              aria-controls="revision-feedback-form"
            >
              Request revisions
            </button>
          </>
        )}
      </div>

      {!approved && revisionFormOpen ? (
        <form
          id="revision-feedback-form"
          className="revision-feedback-form"
          onSubmit={handleSubmitRevisionFeedback}
        >
          <label className="field">
            <span>What should change?</span>
            <textarea
              value={feedbackMarkdown}
              onChange={(e) => setFeedbackMarkdown(e.target.value)}
              rows={6}
              required
              placeholder="Describe the changes you want for the next draft."
            />
          </label>
          <fieldset className="revision-feedback-flags">
            <legend>Common asks (optional)</legend>
            {COMMON_ASK_OPTIONS.map((opt) => (
              <label key={opt.key} className="revision-feedback-flag">
                <input
                  type="checkbox"
                  checked={!!selectedFlags[opt.key]}
                  onChange={(e) =>
                    setSelectedFlags((prev) => ({
                      ...prev,
                      [opt.key]: e.target.checked,
                    }))
                  }
                />
                <span>{opt.label}</span>
              </label>
            ))}
          </fieldset>
          <div className="revision-feedback-actions">
            <button
              type="submit"
              disabled={
                isSubmittingFeedback || feedbackMarkdown.trim().length === 0
              }
            >
              {isSubmittingFeedback ? "Submitting…" : "Submit revision request"}
            </button>
          </div>
        </form>
      ) : null}

      {actionError ? (
        <p role="alert" className="error">
          {actionError}
        </p>
      ) : null}

      {recruiterReview && recruiterReview.available ? (
        <details className="recruiter-review">
          <summary>Open recruiter review</summary>
          <pre className="job-description">{recruiterReview.content}</pre>
        </details>
      ) : recruiterReview && !recruiterReview.available ? (
        <p className="recruiter-review-missing">
          Recruiter review not produced for this draft yet.
        </p>
      ) : null}

      <details className="advanced-details">
        <summary>Advanced details</summary>
        <dl className="run-meta">
          <dt>Resume version id</dt>
          <dd>
            <code>{version.id}</code>
          </dd>
          <dt>Claude run id</dt>
          <dd>
            {version.claude_run_id ? (
              <Link to={`/runs/${version.claude_run_id}`}>
                <code>{version.claude_run_id}</code>
              </Link>
            ) : (
              "—"
            )}
          </dd>
          <dt>Content hash</dt>
          <dd>
            <code>{truncateHash(version.content_hash)}</code>
          </dd>
          <dt>Prompt hash</dt>
          <dd>
            <code>{truncateHash(version.prompt_hash)}</code>
          </dd>
          <dt>DOCX path</dt>
          <dd>
            {version.docx_path ? <code>{version.docx_path}</code> : "—"}
          </dd>
          <dt>PDF path</dt>
          <dd>
            {version.pdf_path ? <code>{version.pdf_path}</code> : "—"}
          </dd>
        </dl>
      </details>

      {version.content_markdown ? (
        <details className="resume-version-markdown">
          <summary>Resume markdown</summary>
          <pre className="job-description">{version.content_markdown}</pre>
        </details>
      ) : null}
    </section>
  );
}
