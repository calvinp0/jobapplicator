import type { PreviewDocument } from "../../lib/reviewModel";
import { ResumePage } from "./ResumePage";
import { ResumeHeaderPreview } from "./ResumeHeaderPreview";
import { ResumeSectionPreview } from "./ResumeSectionPreview";

interface ResumeDocumentPreviewProps {
  document: PreviewDocument;
  selectedKey: string | null;
  onSelectSection: (key: string) => void;
}

/**
 * Center panel: the live resume document. Renders the header and every section
 * onto a single page; sections are individually selectable so clicking one
 * opens its AI suggestions in the right panel.
 */
export function ResumeDocumentPreview({
  document,
  selectedKey,
  onSelectSection,
}: ResumeDocumentPreviewProps) {
  const isEmpty = !document.header && document.sections.length === 0;

  return (
    <div className="doc-preview" data-testid="resume-document-preview">
      <ResumePage>
        {document.header ? (
          <ResumeHeaderPreview header={document.header} />
        ) : null}

        {isEmpty ? (
          <p className="doc-paragraph doc-paragraph-empty">
            No resume content to preview yet.
          </p>
        ) : (
          document.sections.map((section) => (
            <ResumeSectionPreview
              key={section.key}
              section={section}
              selected={section.key === selectedKey}
              onSelect={onSelectSection}
            />
          ))
        )}
      </ResumePage>
    </div>
  );
}
