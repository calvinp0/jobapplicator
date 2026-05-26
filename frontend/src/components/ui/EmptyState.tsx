import type { ReactNode } from "react";

interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  variant?: "card" | "inline";
  className?: string;
}

/**
 * Shared empty-state block. `card` (default) is a bordered surface used as a
 * page-level "no records yet" placeholder; `inline` is a lighter version
 * used inside a SectionCard for the empty body of that section.
 */
export function EmptyState({
  title,
  description,
  actions,
  variant = "card",
  className,
}: EmptyStateProps) {
  const classes = [`empty-state empty-state-${variant}`];
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")} role="status">
      <div className="empty-state-title">{title}</div>
      {description ? (
        <p className="empty-state-description">{description}</p>
      ) : null}
      {actions ? <div className="empty-state-actions">{actions}</div> : null}
    </div>
  );
}
