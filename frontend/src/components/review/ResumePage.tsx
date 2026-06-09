import type { ReactNode } from "react";

interface ResumePageProps {
  children: ReactNode;
}

/**
 * The physical "page": a white Letter-proportioned sheet with a soft shadow on
 * a neutral background, the way a document preview in Word or Google Docs reads.
 */
export function ResumePage({ children }: ResumePageProps) {
  return (
    <div className="doc-page-shell">
      <article className="doc-page" data-testid="resume-page">
        {children}
      </article>
    </div>
  );
}
