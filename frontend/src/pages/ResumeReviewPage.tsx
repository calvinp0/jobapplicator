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
import { SuggestionCard } from "../components/SuggestionCard";
import { Button, EmptyState, PageHeader, SectionCard } from "../components/ui";

interface SectionGroup {
  key: string;
  heading: string;
  suggestions: ResumeSuggestion[];
}

function groupBySection(suggestions: ResumeSuggestion[]): SectionGroup[] {
  const order: string[] = [];
  const groups = new Map<string, SectionGroup>();
  for (const suggestion of suggestions) {
    const key = suggestion.section_id || suggestion.section_heading;
    if (!groups.has(key)) {
      order.push(key);
      groups.set(key, {
        key,
        heading: suggestion.section_heading || suggestion.section_id,
        suggestions: [],
      });
    }
    groups.get(key)!.suggestions.push(suggestion);
  }
  return order.map((key) => groups.get(key)!);
}

export function ResumeReviewPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const [data, setData] = useState<ResumeSuggestions | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);

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

  const groups = useMemo(
    () => (data ? groupBySection(data.suggestions) : []),
    [data],
  );

  const acceptedCount = useMemo(
    () => (data ? data.suggestions.filter((s) => s.status === "accepted").length : 0),
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
      // Refresh so applied_at / has_working_resume reflect the new state.
      const refreshed = await getResumeSuggestions(versionId);
      setData(refreshed);
    } catch {
      setActionError("Could not apply suggestions. Please try again.");
    } finally {
      setIsApplying(false);
    }
  }

  if (loadError) {
    return (
      <div className="page">
        <PageHeader title="Resume Review" />
        <EmptyState
          title="No suggestions"
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

  if (!data) {
    return (
      <div className="page">
        <PageHeader title="Resume Review" />
        <p>Loading suggestions…</p>
      </div>
    );
  }

  const targetLine = [data.target_job_title, data.target_company]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="page resume-review-page">
      <PageHeader
        title="Resume Review"
        description={
          targetLine
            ? `AI suggestions for ${targetLine}`
            : "Review AI suggestions section by section."
        }
        actions={
          <Button
            variant="primary"
            onClick={handleApply}
            disabled={isApplying}
            data-testid="apply-suggestions"
          >
            {isApplying ? "Applying…" : "Apply accepted suggestions"}
          </Button>
        }
        meta={
          <span className="resume-review-summary" data-testid="accepted-count">
            {acceptedCount} accepted ·{" "}
            {data.suggestions.length} total
            {data.applied_at ? " · working resume saved" : ""}
          </span>
        }
      />

      {actionError ? (
        <p className="form-error" role="alert">
          {actionError}
        </p>
      ) : null}
      {applyMessage ? (
        <p className="form-success" role="status" data-testid="apply-message">
          {applyMessage}
        </p>
      ) : null}

      {data.suggestions.length === 0 ? (
        <EmptyState
          title="No suggestions"
          description="This run produced no section-level suggestions to review."
        />
      ) : (
        <div className="resume-review-sections">
          {groups.map((group) => (
            <SectionCard
              key={group.key}
              title={group.heading}
              data-testid={`review-section-${group.key}`}
            >
              <div className="suggestion-list">
                {group.suggestions.map((suggestion) => (
                  <SuggestionCard
                    key={suggestion.id}
                    suggestion={suggestion}
                    busy={busyId === suggestion.id}
                    onAccept={() =>
                      runAction(suggestion.id, () =>
                        acceptSuggestion(versionId!, suggestion.id),
                      )
                    }
                    onReject={() =>
                      runAction(suggestion.id, () =>
                        rejectSuggestion(versionId!, suggestion.id),
                      )
                    }
                    onRevise={(instruction) =>
                      runAction(suggestion.id, () =>
                        reviseSuggestion(versionId!, suggestion.id, instruction),
                      )
                    }
                  />
                ))}
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </div>
  );
}
