import type { ReactNode } from "react";

interface ResumePageProps {
  children: ReactNode;
  pageNumber: number;
  totalPages: number;
}

/**
 * One physical "page": a labeled white Letter-proportioned sheet with a soft
 * shadow, the way a document preview in Word or Google Docs reads. The page
 * label sits above the sheet so the page boundaries are visually obvious.
 */
export function ResumePage({ children, pageNumber, totalPages }: ResumePageProps) {
  return (
    <div className="doc-page-block" data-testid={`doc-page-block-${pageNumber}`}>
      <p className="doc-page-label" data-testid={`page-label-${pageNumber}`}>
        Page {pageNumber}
        {totalPages > 1 ? ` of ${totalPages}` : ""}
      </p>
      <article className="doc-page" data-testid="resume-page">
        {children}
      </article>
    </div>
  );
}
