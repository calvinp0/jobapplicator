import type { Application } from "../api";

/**
 * Compact, colour-coded pipeline status the applications table surfaces as a
 * small dot + single-line label. Deliberately a small closed set mapped from
 * the server-derived ``timeline_stage`` so the table never renders raw backend
 * status enums or oversized pills.
 */
export type PipelineStatusVariant =
  | "draft"
  | "submitted"
  | "confirmation"
  | "response"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn"
  | "default";

const PIPELINE_VARIANTS: Record<string, PipelineStatusVariant> = {
  draft: "draft",
  sent: "submitted",
  confirmation_received: "confirmation",
  response_received: "response",
  interview: "interview",
  offer: "offer",
  rejected: "rejected",
  withdrawn: "withdrawn",
};

export function pipelineStatusVariant(stage: string): PipelineStatusVariant {
  return PIPELINE_VARIANTS[stage] ?? "default";
}

/**
 * Short one-line label for the pipeline dot. Deliberately shorter than the
 * full ``timelineStageLabel`` (e.g. "Confirmation" not "Confirmation
 * received") so the label never wraps inside the narrow Pipeline column; the
 * fuller context lives in the detail line beneath it.
 */
const PIPELINE_LABELS: Record<string, string> = {
  draft: "Draft",
  sent: "Submitted",
  confirmation_received: "Confirmation",
  response_received: "Response",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export function pipelineStatusLabel(stage: string): string {
  return PIPELINE_LABELS[stage] ?? stage;
}

/** A secondary action that navigates somewhere (rendered as a link). */
export interface ApplicationLinkAction {
  kind: "link";
  key: string;
  label: string;
  href: string;
}

/** A status-mutation kept behind the overflow menu (rendered as a button). */
export type ApplicationMutationKey = "submit" | "interview" | "rejected";

export interface ApplicationButtonAction {
  kind: "button";
  key: ApplicationMutationKey;
  label: string;
}

export type ApplicationMenuAction =
  | ApplicationLinkAction
  | ApplicationButtonAction;

export interface ApplicationRowActions {
  /** The single obvious next thing to do — also the primary button. */
  primary: ApplicationLinkAction;
  /** Everything else, surfaced behind the overflow ("⋯") menu. */
  secondary: ApplicationMenuAction[];
}

const TERMINAL_STATUSES = new Set(["rejected", "withdrawn"]);
const NON_INTERVIEW_STATUSES = new Set([
  "interview",
  "rejected",
  "withdrawn",
  "offer",
]);

/**
 * Reduce an application to the single primary action plus the secondary
 * actions that belong in its overflow menu. The mapping is deterministic and
 * mirrors the workflow the user thinks in: an active/failed tailoring run
 * trumps everything, then an approved draft ready to send, then a draft to
 * review, then the steady "open the detail" fallback for submitted-and-later
 * rows. Status mutations (mark submitted / interview / rejected) are never
 * primary — they always live in the menu so each row shows exactly one button.
 */
export function buildApplicationRowActions(
  app: Application,
): ApplicationRowActions {
  const detailHref = `/applications/${app.id}`;
  const runHref = app.latest_run_id ? `/runs/${app.latest_run_id}` : null;
  const resumeHref = app.resume_version_id
    ? `/resume-versions/${app.resume_version_id}`
    : null;
  const runStatus = app.latest_run_status;

  let primary: ApplicationLinkAction;
  if (runHref && (runStatus === "running" || runStatus === "created")) {
    primary = {
      kind: "link",
      key: "run",
      label: "View progress",
      href: runHref,
    };
  } else if (runHref && runStatus === "failed") {
    primary = {
      kind: "link",
      key: "run",
      label: "Review failure",
      href: runHref,
    };
  } else if (app.email_status === "needs_review") {
    primary = { kind: "link", key: "detail", label: "Review", href: detailHref };
  } else if (
    app.timeline_stage === "draft" &&
    app.submission_status === "not_submitted"
  ) {
    if (app.status === "approved") {
      primary = {
        kind: "link",
        key: "detail",
        label: "Continue",
        href: detailHref,
      };
    } else if (resumeHref) {
      primary = {
        kind: "link",
        key: "resume",
        label: "Review draft",
        href: resumeHref,
      };
    } else {
      primary = {
        kind: "link",
        key: "detail",
        label: "Generate draft",
        href: detailHref,
      };
    }
  } else {
    primary = { kind: "link", key: "detail", label: "Open", href: detailHref };
  }

  const secondary: ApplicationMenuAction[] = [];
  // Always offer a direct way to the application detail when it is not the
  // primary destination.
  if (primary.href !== detailHref) {
    secondary.push({
      kind: "link",
      key: "detail",
      label: "Open application",
      href: detailHref,
    });
  }
  if (resumeHref && primary.href !== resumeHref) {
    secondary.push({
      kind: "link",
      key: "resume",
      label: app.status === "approved" ? "Open resume" : "Open draft",
      href: resumeHref,
    });
  }
  if (runHref && primary.href !== runHref) {
    secondary.push({
      kind: "link",
      key: "run",
      label: "View latest run",
      href: runHref,
    });
  }
  if (app.submission_status === "not_submitted") {
    secondary.push({ kind: "button", key: "submit", label: "Mark submitted" });
  }
  if (!NON_INTERVIEW_STATUSES.has(app.status)) {
    secondary.push({
      kind: "button",
      key: "interview",
      label: "Mark interview",
    });
  }
  if (!TERMINAL_STATUSES.has(app.status)) {
    secondary.push({ kind: "button", key: "rejected", label: "Mark rejected" });
  }

  return { primary, secondary };
}
