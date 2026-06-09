import type { ReactNode } from "react";
import type { PreviewDocument, PreviewSection } from "../../lib/reviewModel";
import type { ResumeSuggestion } from "../../api/types";
import { Button } from "../ui";
import { WorkflowRail } from "./WorkflowRail";
import type { WorkflowStep } from "./WorkflowRail";
import { ResumeDocumentPreview } from "./ResumeDocumentPreview";
import { ReviewPanel } from "./ReviewPanel";

interface ResumeReviewWorkspaceProps {
  targetLine: string;
  backLink: ReactNode;
  steps: WorkflowStep[];
  document: PreviewDocument;
  selectedKey: string | null;
  selectedSection: PreviewSection | null;
  onSelectSection: (key: string) => void;
  busyId: string | null;
  onAccept: (suggestion: ResumeSuggestion) => void;
  onReject: (suggestion: ResumeSuggestion) => void;
  onRevise: (suggestion: ResumeSuggestion, instruction: string) => void;
  acceptedCount: number;
  totalCount: number;
  appliedAt: string | null;
  onApply: () => void;
  isApplying: boolean;
  applyMessage: string | null;
  actionError: string | null;
}

/**
 * The three-panel resume review workspace (task 114):
 *   left   — workflow rail
 *   center — live resume document preview
 *   right  — AI change review panel
 * A slim top bar carries the document title, review progress, and the
 * Apply action so the surface reads as a document editor, not a dashboard.
 */
export function ResumeReviewWorkspace({
  targetLine,
  backLink,
  steps,
  document,
  selectedKey,
  selectedSection,
  onSelectSection,
  busyId,
  onAccept,
  onReject,
  onRevise,
  acceptedCount,
  totalCount,
  appliedAt,
  onApply,
  isApplying,
  applyMessage,
  actionError,
}: ResumeReviewWorkspaceProps) {
  return (
    <div className="review-workspace" data-testid="review-workspace">
      <header className="review-topbar">
        <div className="review-topbar-lead">
          {backLink}
          <div className="review-topbar-titles">
            <h1 className="review-topbar-title">Resume Review</h1>
            {targetLine ? (
              <p className="review-topbar-subtitle">{targetLine}</p>
            ) : null}
          </div>
        </div>
        <div className="review-topbar-actions">
          <span className="review-progress" data-testid="accepted-count">
            {acceptedCount} accepted · {totalCount} total
            {appliedAt ? " · working resume saved" : ""}
          </span>
          <Button
            variant="primary"
            size="sm"
            onClick={onApply}
            disabled={isApplying}
            data-testid="apply-suggestions"
          >
            {isApplying ? "Applying…" : "Apply accepted suggestions"}
          </Button>
        </div>
      </header>

      {actionError ? (
        <p className="review-banner review-banner-error" role="alert">
          {actionError}
        </p>
      ) : null}
      {applyMessage ? (
        <p
          className="review-banner review-banner-success"
          role="status"
          data-testid="apply-message"
        >
          {applyMessage}
        </p>
      ) : null}

      <div className="review-grid">
        <WorkflowRail steps={steps} />
        <main className="review-center">
          <ResumeDocumentPreview
            document={document}
            selectedKey={selectedKey}
            onSelectSection={onSelectSection}
          />
        </main>
        <div className="review-panel-column" data-testid="review-panel-column">
          <ReviewPanel
            section={selectedSection}
            busyId={busyId}
            onAccept={onAccept}
            onReject={onReject}
            onRevise={onRevise}
          />
        </div>
      </div>
    </div>
  );
}
