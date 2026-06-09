import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ApiError,
  acceptSuggestion,
  applyResumeSuggestions,
  getResumeSuggestions,
  rejectSuggestion,
  reviseSuggestion,
} from "../api";
import type { ResumeSuggestion, ResumeSuggestions } from "../api/types";
import { buildPreviewDocument } from "../lib/reviewModel";
import { ResumeReviewWorkspace } from "../components/review/ResumeReviewWorkspace";
import type { WorkflowStep } from "../components/review/WorkflowRail";
import { EmptyState } from "../components/ui";

/**
 * Resume Review workspace (task 114). Replaces the earlier card stack with a
 * three-panel, Word-like document review surface: workflow rail (left), live
 * resume document preview (center), and AI change panel (right). Data still
 * comes from the task-113 suggestion endpoints; the structured ``base_resume``
 * / ``working_resume`` now power the document preview.
 */
export function ResumeReviewPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const [data, setData] = useState<ResumeSuggestions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!versionId) return;
    let cancelled = false;
    getResumeSuggestions(versionId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setLoadError(
            "This draft has no AI suggestions to review. Suggestions are " +
              "produced by newer tailoring runs.",
          );
        } else {
          setLoadError("Failed to load resume suggestions.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  const document = useMemo(
    () => (data ? buildPreviewDocument(data) : null),
    [data],
  );

  // Default the selection to the first section that actually has suggestions,
  // so the right panel opens on something meaningful.
  useEffect(() => {
    if (!document || selectedKey !== null) return;
    const firstWithSuggestions = document.sections.find(
      (s) => s.suggestions.length > 0,
    );
    const fallback = document.sections[0];
    const target = firstWithSuggestions ?? fallback;
    if (target) setSelectedKey(target.key);
  }, [document, selectedKey]);

  const selectedSection = useMemo(
    () =>
      document?.sections.find((s) => s.key === selectedKey) ?? null,
    [document, selectedKey],
  );

  const acceptedCount = useMemo(
    () =>
      data ? data.suggestions.filter((s) => s.status === "accepted").length : 0,
    [data],
  );

  function replaceSuggestion(updated: ResumeSuggestion) {
    setData((prev) =>
      prev
        ? {
            ...prev,
            suggestions: prev.suggestions.map((s) =>
              s.id === updated.id ? updated : s,
            ),
          }
        : prev,
    );
  }

  async function runAction(
    suggestionId: string,
    action: () => Promise<ResumeSuggestion>,
  ) {
    if (!versionId) return;
    setBusyId(suggestionId);
    setActionError(null);
    try {
      replaceSuggestion(await action());
    } catch {
      setActionError("Could not update the suggestion. Please try again.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleApply() {
    if (!versionId) return;
    setIsApplying(true);
    setActionError(null);
    setApplyMessage(null);
    try {
      const result = await applyResumeSuggestions(versionId);
      setApplyMessage(
        `Applied ${result.accepted_count} accepted suggestion${
          result.accepted_count === 1 ? "" : "s"
        } to the working resume.`,
      );
      // Refresh so applied_at / working_resume reflect the new state.
      const refreshed = await getResumeSuggestions(versionId);
      setData(refreshed);
    } catch {
      setActionError("Could not apply suggestions. Please try again.");
    } finally {
      setIsApplying(false);
    }
  }

  const steps = useMemo<WorkflowStep[]>(() => {
    const exported = Boolean(data?.applied_at);
    return [
      { label: "Job", status: "complete" },
      { label: "Evidence", status: "complete" },
      { label: "Tailoring", status: "complete" },
      { label: "Review", status: "active" },
      { label: "Export", status: exported ? "complete" : "blocked" },
    ];
  }, [data?.applied_at]);

  if (loadError) {
    return (
      <div className="page">
        <EmptyState
          title="No suggestions to review"
          description={loadError}
          actions={
            versionId ? (
              <Link to={`/resume-versions/${versionId}`}>Back to draft</Link>
            ) : null
          }
        />
      </div>
    );
  }

  if (!data || !document) {
    return (
      <div className="page">
        <p>Loading review workspace…</p>
      </div>
    );
  }

  const targetLine = [data.target_job_title, data.target_company]
    .filter(Boolean)
    .join(" · ");

  return (
    <ResumeReviewWorkspace
      targetLine={targetLine}
      backLink={
        versionId ? (
          <Link className="review-back-link" to={`/resume-versions/${versionId}`}>
            ← Draft
          </Link>
        ) : null
      }
      steps={steps}
      document={document}
      selectedKey={selectedKey}
      selectedSection={selectedSection}
      onSelectSection={setSelectedKey}
      busyId={busyId}
      onAccept={(s) =>
        runAction(s.id, () => acceptSuggestion(versionId!, s.id))
      }
      onReject={(s) =>
        runAction(s.id, () => rejectSuggestion(versionId!, s.id))
      }
      onRevise={(s, instruction) =>
        runAction(s.id, () => reviseSuggestion(versionId!, s.id, instruction))
      }
      acceptedCount={acceptedCount}
      totalCount={data.suggestions.length}
      appliedAt={data.applied_at}
      onApply={handleApply}
      isApplying={isApplying}
      applyMessage={applyMessage}
      actionError={actionError}
    />
  );
}
