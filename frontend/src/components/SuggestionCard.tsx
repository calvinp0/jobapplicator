import { useState } from "react";
import type { ResumeSuggestion } from "../api/types";
import { Button } from "./ui";
import { StatusBadge } from "./ui";
import type { StatusBadgeVariant } from "./ui";

interface SuggestionCardProps {
  suggestion: ResumeSuggestion;
  onAccept: () => void;
  onReject: () => void;
  onRevise: (instruction: string) => void;
  busy?: boolean;
}

const STATUS_VARIANT: Record<string, StatusBadgeVariant> = {
  pending: "pending",
  accepted: "approved",
  rejected: "rejected",
  revised: "running",
};

function riskClass(risk: string): string {
  return `suggestion-risk suggestion-risk-${risk}`;
}

function formatConfidence(confidence: number | null): string | null {
  if (confidence === null || Number.isNaN(confidence)) return null;
  return `${Math.round(confidence * 100)}%`;
}

/**
 * One reviewable, evidence-backed resume edit. Renders the current/suggested
 * text, the rationale, evidence references and ATS keywords, plus accept /
 * reject / ask-to-revise controls. Accepted cards are visually marked so the
 * preview reflects the working state at a glance (task 113).
 */
export function SuggestionCard({
  suggestion,
  onAccept,
  onReject,
  onRevise,
  busy = false,
}: SuggestionCardProps) {
  const [reviseOpen, setReviseOpen] = useState(false);
  const [instruction, setInstruction] = useState(
    suggestion.revision_instruction ?? "",
  );

  const confidence = formatConfidence(suggestion.confidence);
  const variant = STATUS_VARIANT[suggestion.status] ?? "default";

  return (
    <article
      className={`suggestion-card suggestion-card-${suggestion.status}`}
      data-testid={`suggestion-card-${suggestion.id}`}
    >
      <header className="suggestion-card-header">
        <div className="suggestion-card-titles">
          <span className="suggestion-section">
            {suggestion.section_heading || suggestion.section_id}
          </span>
          <span className="suggestion-operation">{suggestion.operation}</span>
        </div>
        <div className="suggestion-card-flags">
          <StatusBadge
            variant={variant}
            data-testid={`suggestion-status-${suggestion.id}`}
          >
            {suggestion.status}
          </StatusBadge>
          <span className={riskClass(suggestion.risk)}>
            risk: {suggestion.risk}
          </span>
          {confidence ? (
            <span className="suggestion-confidence">
              confidence: {confidence}
            </span>
          ) : null}
        </div>
      </header>

      {suggestion.current_text ? (
        <div className="suggestion-text suggestion-text-current">
          <span className="suggestion-text-label">Current</span>
          <p>{suggestion.current_text}</p>
        </div>
      ) : null}

      {suggestion.suggested_text ? (
        <div className="suggestion-text suggestion-text-suggested">
          <span className="suggestion-text-label">Suggested</span>
          <p>{suggestion.suggested_text}</p>
        </div>
      ) : null}

      <p className="suggestion-reason">
        <span className="suggestion-text-label">Why</span>
        {suggestion.reason}
      </p>

      {suggestion.evidence_refs.length > 0 ? (
        <div className="suggestion-evidence">
          <span className="suggestion-text-label">Evidence</span>
          <ul>
            {suggestion.evidence_refs.map((ref, idx) => (
              <li key={idx}>
                <span className="suggestion-evidence-source">{ref.source}</span>
                {ref.quote ? `: “${ref.quote}”` : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {suggestion.ats_keywords.length > 0 ? (
        <div className="suggestion-keywords">
          <span className="suggestion-text-label">ATS keywords addressed</span>
          <div className="suggestion-keyword-chips">
            {suggestion.ats_keywords.map((kw) => (
              <span key={kw} className="suggestion-keyword-chip">
                {kw}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {suggestion.status === "revised" && suggestion.revision_instruction ? (
        <p className="suggestion-revision-note">
          <span className="suggestion-text-label">Revision requested</span>
          {suggestion.revision_instruction}
        </p>
      ) : null}

      <footer className="suggestion-card-actions">
        <Button
          variant="primary"
          size="sm"
          onClick={onAccept}
          disabled={busy || suggestion.status === "accepted"}
          data-testid={`accept-${suggestion.id}`}
        >
          Accept
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={onReject}
          disabled={busy || suggestion.status === "rejected"}
          data-testid={`reject-${suggestion.id}`}
        >
          Reject
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setReviseOpen((open) => !open)}
          disabled={busy}
          data-testid={`revise-toggle-${suggestion.id}`}
        >
          Ask to revise
        </Button>
      </footer>

      {reviseOpen ? (
        <div className="suggestion-revise-form">
          <textarea
            className="suggestion-revise-textarea"
            value={instruction}
            placeholder="e.g. Make this less startup-focused and more backend-systems focused."
            onChange={(event) => setInstruction(event.target.value)}
            data-testid={`revise-textarea-${suggestion.id}`}
          />
          <Button
            variant="primary"
            size="sm"
            disabled={busy || instruction.trim().length === 0}
            onClick={() => {
              onRevise(instruction.trim());
              setReviseOpen(false);
            }}
            data-testid={`revise-submit-${suggestion.id}`}
          >
            Save revision request
          </Button>
        </div>
      ) : null}
    </article>
  );
}
