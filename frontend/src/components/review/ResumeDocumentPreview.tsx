import type { PreviewDocument } from "../../lib/reviewModel";
import { paginateSections } from "../../lib/reviewModel";
import { ResumePage } from "./ResumePage";
import { ResumeHeaderPreview } from "./ResumeHeaderPreview";
import { ResumeSectionPreview } from "./ResumeSectionPreview";

interface ResumeDocumentPreviewProps {
  document: PreviewDocument;
  selectedKey: string | null;
  onSelectSection: (key: string) => void;
}

/**
 * Center panel: the live resume document. The header and sections are laid out
 * across one or more visible pages (estimated pagination) so the reviewer can
 * see where page 1 ends and page 2 begins. Sections are individually
 * selectable so clicking one opens its AI suggestions in the right panel.
 */
export function ResumeDocumentPreview({
  document,
  selectedKey,
  onSelectSection,
}: ResumeDocumentPreviewProps) {
  const isEmpty = !document.header && document.sections.length === 0;
  const pages = paginateSections(document);

  return (
    <div className="doc-preview" data-testid="resume-document-preview">
      <div className="doc-page-shell">
        {pages.map((sections, pageIndex) => (
          <ResumePage
            key={pageIndex}
            pageNumber={pageIndex + 1}
            totalPages={pages.length}
          >
            {pageIndex === 0 && document.header ? (
              <ResumeHeaderPreview header={document.header} />
            ) : null}

            {isEmpty && pageIndex === 0 ? (
              <p className="doc-paragraph doc-paragraph-empty">
                No resume content to preview yet.
              </p>
            ) : (
              sections.map((section) => (
                <ResumeSectionPreview
                  key={section.key}
                  section={section}
                  selected={section.key === selectedKey}
                  onSelect={onSelectSection}
                />
              ))
            )}
          </ResumePage>
        ))}
      </div>
    </div>
  );
}
