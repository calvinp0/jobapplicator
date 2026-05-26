import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
}

/**
 * Standard page header used by top-level pages. Renders a consistent title +
 * description block on the left and an optional action cluster on the right.
 * `meta` slots below the row for hints, sync summaries, or status lines.
 */
export function PageHeader({
  title,
  description,
  actions,
  meta,
}: PageHeaderProps) {
  return (
    <header className="page-header app-page-header">
      <div className="app-page-header-row">
        <div className="app-page-header-titles">
          <h2>{title}</h2>
          {description ? (
            <p className="page-subtitle">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="app-page-header-actions">{actions}</div>
        ) : null}
      </div>
      {meta ? <div className="app-page-header-meta">{meta}</div> : null}
    </header>
  );
}
