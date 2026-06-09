export type WorkflowStepStatus =
  | "complete"
  | "active"
  | "blocked"
  | "failed"
  | "pending";

export interface WorkflowStep {
  label: string;
  status: WorkflowStepStatus;
}

interface WorkflowRailProps {
  steps: WorkflowStep[];
}

const STATUS_GLYPH: Record<WorkflowStepStatus, string> = {
  complete: "✓",
  active: "",
  blocked: "",
  failed: "!",
  pending: "",
};

/**
 * Narrow left rail showing the tailoring workflow. Each step shows a number (or
 * a tick once complete), its label, and a compact status word — no oversized
 * badges. The active step is highlighted with the accent bar.
 */
export function WorkflowRail({ steps }: WorkflowRailProps) {
  return (
    <nav className="workflow-rail" aria-label="Tailoring workflow">
      <p className="workflow-rail-title">Workflow</p>
      <ol className="workflow-steps">
        {steps.map((step, idx) => (
          <li
            key={step.label}
            className={`workflow-step workflow-step-${step.status}`}
            data-testid={`workflow-step-${idx + 1}`}
            aria-current={step.status === "active" ? "step" : undefined}
          >
            <span className="workflow-step-marker" aria-hidden="true">
              {STATUS_GLYPH[step.status] || idx + 1}
            </span>
            <span className="workflow-step-body">
              <span className="workflow-step-label">{step.label}</span>
              <span className="workflow-step-status">{step.status}</span>
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
