import type { PreviewSection } from "../../lib/reviewModel";
import type { ResumeSuggestion } from "../../api/types";
import { SuggestionCard } from "../SuggestionCard";
import { EmptyState } from "../ui";

interface ReviewPanelProps {
  section: PreviewSection | null;
  busyId: string | null;
  onAccept: (suggestion: ResumeSuggestion) => void;
  onReject: (suggestion: ResumeSuggestion) => void;
  onRevise: (suggestion: ResumeSuggestion, instruction: string) => void;
}

/**
 * Right panel: the AI review / track-changes surface for the currently
 * selected section. Renders one SuggestionCard per suggestion (previous vs.
 * suggested text, reason, evidence, ATS keywords, risk, and accept / reject /
 * revise actions) or a useful empty state when the section has no suggestions.
 */
export function ReviewPanel({
  section,
  busyId,
  onAccept,
  onReject,
  onRevise,
}: ReviewPanelProps) {
  return (
    <aside className="review-panel" aria-label="AI review" data-testid="review-panel">
      <div className="review-panel-header">
        <span className="review-panel-eyebrow">AI Review</span>
        <h2 className="review-panel-title">
          {section ? section.heading : "No section selected"}
        </h2>
      </div>

      <div className="review-panel-body">
        {!section ? (
          <EmptyState
            variant="inline"
            title="Select a section"
            description="Click a section in the document to review its AI suggestions."
          />
        ) : section.suggestions.length === 0 ? (
          <EmptyState
            variant="inline"
            title="No AI suggestions available for this section yet."
            description="Run tailoring or open an existing tailored draft."
          />
        ) : (
          <div className="review-panel-cards">
            {section.suggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                busy={busyId === suggestion.id}
                onAccept={() => onAccept(suggestion)}
                onReject={() => onReject(suggestion)}
                onRevise={(instruction) => onRevise(suggestion, instruction)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
