import type { ReactNode } from "react";

interface SectionCardProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}

/**
 * Surface card used to group related content within a page (e.g. each
 * Settings sub-section, the Gmail integration block, etc.). Provides a
 * consistent header (title + optional description + actions slot) and a
 * body that callers fill with their own content.
 */
export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  ...rest
}: SectionCardProps) {
  const classes = ["section-card"];
  if (className) classes.push(className);
  return (
    <section className={classes.join(" ")} data-testid={rest["data-testid"]}>
      <header className="section-card-header">
        <div className="section-card-titles">
          <h3>{title}</h3>
          {description ? (
            <p className="section-card-description">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="section-card-actions">{actions}</div>
        ) : null}
      </header>
      <div className="section-card-body">{children}</div>
    </section>
  );
}
