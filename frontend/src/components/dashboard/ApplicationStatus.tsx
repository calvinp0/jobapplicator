import type { ReactNode } from "react";
import type { ActiveJobStatusVariant } from "../../lib/dashboardJobs";

interface ApplicationStatusProps {
  variant: ActiveJobStatusVariant;
  children: ReactNode;
}

/**
 * Compact status indicator: a small coloured dot followed by a single-line
 * label. Replaces the old oversized rounded pill so the status never wraps or
 * dominates the card.
 */
export function ApplicationStatus({ variant, children }: ApplicationStatusProps) {
  return (
    <span className={`app-status app-status-${variant}`}>
      <span className="app-status-dot" aria-hidden="true" />
      <span className="app-status-label">{children}</span>
    </span>
  );
}
