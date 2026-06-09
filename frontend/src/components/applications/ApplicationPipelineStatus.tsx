import type { PipelineStatusVariant } from "../../lib/applicationActions";

interface ApplicationPipelineStatusProps {
  variant: PipelineStatusVariant;
  label: string;
  "data-testid"?: string;
}

/**
 * Compact pipeline status: a small coloured dot followed by a single-line
 * label. Replaces the oversized rounded "PowerPoint" pill so the status never
 * wraps or dominates the row. Colour comes entirely from the dot; the label
 * stays the row's default text colour for a calm, scannable table.
 */
export function ApplicationPipelineStatus({
  variant,
  label,
  ...rest
}: ApplicationPipelineStatusProps) {
  return (
    <span
      className={`applications-status applications-status-${variant}`}
      data-testid={rest["data-testid"]}
    >
      <span className="applications-status-dot" aria-hidden="true" />
      <span className="applications-status-label">{label}</span>
    </span>
  );
}
