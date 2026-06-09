import type { PreviewDocument } from "../../lib/reviewModel";
import { paginateDocument } from "../../lib/reviewModel";
import { ResumePage } from "./ResumePage";
import { ResumeHeaderPreview } from "./ResumeHeaderPreview";
import { ResumeSectionSlice } from "./ResumeSectionSlice";

interface ResumeDocumentPreviewProps {
  document: PreviewDocument;
  selectedKey: string | null;
  onSelectSection: (key: string) => void;
}

/**
 * Center panel: the live resume document. The header and sections flow across
 * one or more visible pages using block-level pagination, so a section can
 * begin near the bottom of a page and continue onto the next — the way a real
 * Word/Docs resume fills pages — instead of bumping whole sections to a fresh
 * page. Sections remain individually selectable so clicking one opens its AI
 * suggestions in the right panel.
 */
export function ResumeDocumentPreview({
  document,
  selectedKey,
  onSelectSection,
}: ResumeDocumentPreviewProps) {
  const isEmpty = !document.header && document.sections.length === 0;
  const pages = paginateDocument(document);

  return (
    <div className="doc-preview" data-testid="resume-document-preview">
      <div className="doc-page-shell">
        {pages.map((page, pageIndex) => (
          <ResumePage
            key={pageIndex}
            pageNumber={pageIndex + 1}
            totalPages={pages.length}
          >
            {page.hasHeader && document.header ? (
              <ResumeHeaderPreview header={document.header} />
            ) : null}

            {isEmpty && pageIndex === 0 ? (
              <p className="doc-paragraph doc-paragraph-empty">
                No resume content to preview yet.
              </p>
            ) : (
              page.slices.map((slice, sliceIndex) => (
                <ResumeSectionSlice
                  key={`${slice.key}-${sliceIndex}`}
                  slice={slice}
                  selected={slice.key === selectedKey}
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
