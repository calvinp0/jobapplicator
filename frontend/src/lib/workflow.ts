import type { Application, ClaudeRun, Job, ResumeVersion } from "../api";

const RUN_STATUS_LABELS: Record<string, string> = {
  created: "Queued",
  running: "Tailoring in progress",
  completed: "Tailoring finished — loading draft",
  imported: "Draft ready to review",
  failed: "Tailoring failed",
};

export function runStatusLabel(status: string): string {
  return RUN_STATUS_LABELS[status] ?? status;
}

/**
 * Parse a backend ISO-8601 timestamp into a Date.
 *
 * The backend writes timezone-aware UTC datetimes, but SQLite drops the
 * tzinfo so Pydantic serializes them without a `Z` suffix (e.g.
 * `"2026-05-24T14:38:01.599305"`). JavaScript's `Date` parser interprets
 * such tz-less strings as **local** time, so a freshly-started run can
 * appear several hours old to a non-UTC user. Normalize by appending `Z`
 * when no timezone designator is present.
 *
 * Returns `null` if the value is missing or unparseable so callers can
 * render an "unavailable" state rather than `NaN`.
 */
export function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  // Already has a timezone designator (Z or ±hh:mm) — parse as-is. Look
  // only at the time portion (after `T` or space) so a date like
  // `2026-05-22` is not mistaken for having a tz because of its `-`.
  const sepIndex = Math.max(trimmed.indexOf("T"), trimmed.indexOf(" "));
  const timePart = sepIndex >= 0 ? trimmed.slice(sepIndex + 1) : "";
  const hasTz =
    /Z$/i.test(trimmed) || /[+-]\d{2}:?\d{2}$/.test(timePart);
  const normalized = hasTz ? trimmed.replace(" ", "T") : `${trimmed.replace(" ", "T")}Z`;
  const ms = Date.parse(normalized);
  if (Number.isNaN(ms)) return null;
  return new Date(ms);
}

/**
 * Pick the most accurate "run started" timestamp for elapsed-time display.
 * Prefers ``started_at`` (set when the worker begins) and falls back to
 * ``created_at`` (set on the create_run() call).
 */
export function runStartTimestamp(run: ClaudeRun): string | null {
  return run.started_at ?? run.created_at ?? null;
}

/**
 * Format an elapsed duration into a compact human label.
 *
 * Returns the duration WITHOUT a trailing " elapsed" suffix so callers can
 * compose their own surrounding copy (e.g. "12s elapsed" vs "12s ago").
 * Returns `"elapsed time unavailable"` when the start timestamp is missing
 * or invalid, or when the computed duration is negative.
 *
 *   under 5s   → "just now"
 *   under 60s  → "12s"
 *   under 60m  → "1m 04s"  (or "5m" once past 5 minutes — drop the seconds)
 *   60m+       → "1h 02m"
 */
export function formatElapsedSince(
  startTimestamp: string | null | undefined,
  now: Date = new Date(),
): string {
  const started = parseTimestamp(startTimestamp ?? null);
  if (!started) return "elapsed time unavailable";
  const seconds = Math.floor((now.getTime() - started.getTime()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "elapsed time unavailable";
  }
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remSeconds = seconds % 60;
  if (minutes < 5) {
    return `${minutes}m ${remSeconds.toString().padStart(2, "0")}s`;
  }
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${(minutes % 60).toString().padStart(2, "0")}m`;
}

export function runIsActive(status: string): boolean {
  return status === "created" || status === "running";
}

export function runIsComplete(status: string): boolean {
  return status === "completed" || status === "imported";
}

export function runNeedsImport(
  run: ClaudeRun,
  versions: ResumeVersion[],
): boolean {
  if (run.status !== "completed") return false;
  return !versions.some((v) => v.claude_run_id === run.id);
}

export function draftLabel(versionIndex: number): string {
  return `Draft ${versionIndex + 1}`;
}

export function draftStatusLabel(approval: string | null): string {
  return approval ? "Approved" : "Awaiting review";
}

/**
 * The workflow stage a job currently sits in. These are the only stages the
 * UI exposes to the user; backend status enums (run.status, application.status)
 * must not appear in default UI surfaces.
 *
 * - `captured`     — job was captured, nothing tailored yet.
 * - `tailoring`    — a tailoring run is active or has completed but not been
 *                    imported into a ResumeVersion yet.
 * - `draft_ready`  — at least one draft exists for the job, none approved yet.
 * - `approved`     — at least one draft is approved, no application sent yet.
 * - `sent`         — the application has been submitted.
 */
export type JobStage =
  | "captured"
  | "tailoring"
  | "draft_ready"
  | "approved"
  | "sent";

const JOB_STAGE_LABELS: Record<JobStage, string> = {
  captured: "Awaiting tailoring",
  tailoring: "Tailoring in progress",
  draft_ready: "Draft ready to review",
  approved: "Approved — ready to send",
  sent: "Sent",
};

export function jobStageLabel(stage: JobStage): string {
  return JOB_STAGE_LABELS[stage];
}

/**
 * Compute the workflow stage of a single job from its related run, version,
 * and application records.
 *
 * The caller picks the most relevant `application` for the job (usually the
 * submitted one if any, else the latest open one, else `null`). `runs` and
 * `versions` may include records for other jobs — they are filtered to
 * `job.id` here.
 *
 * Stage priority: sent > approved > draft_ready > tailoring > captured.
 */
export function computeJobStage(
  job: Job,
  runs: ClaudeRun[],
  versions: ResumeVersion[],
  application: Application | null,
): JobStage {
  if (application && application.status === "submitted") return "sent";
  const jobVersions = versions.filter((v) => v.job_id === job.id);
  if (jobVersions.some((v) => v.approved_at !== null)) return "approved";
  if (jobVersions.length > 0) return "draft_ready";
  const jobRuns = runs.filter((r) => r.job_id === job.id);
  const hasActiveRun = jobRuns.some(
    (r) => runIsActive(r.status) || runNeedsImport(r, versions),
  );
  if (hasActiveRun) return "tailoring";
  return "captured";
}

/**
 * Application timeline-stage labels. The stage strings are server-derived
 * per docs/contracts/application_status.md and the canonical set is
 * `draft | sent | confirmation_received | response_received | rejected |
 *  interview | offer | withdrawn`.
 */
const TIMELINE_STAGE_LABELS: Record<string, string> = {
  draft: "Draft",
  sent: "Sent",
  confirmation_received: "Confirmation received",
  response_received: "Response received",
  rejected: "Rejected",
  interview: "Interview",
  offer: "Offer",
  withdrawn: "Withdrawn",
};

export function timelineStageLabel(stage: string): string {
  return TIMELINE_STAGE_LABELS[stage] ?? stage;
}

const TIMELINE_STAGE_VARIANTS: Record<string, string> = {
  draft: "draft",
  sent: "submitted",
  confirmation_received: "completed",
  response_received: "running",
  rejected: "rejected",
  interview: "interview",
  offer: "offer",
  withdrawn: "draft",
};

export function timelineStageVariant(stage: string): string {
  return TIMELINE_STAGE_VARIANTS[stage] ?? "default";
}

const EMAIL_CLASSIFICATION_LABELS: Record<string, string> = {
  confirmation: "Confirmation",
  rejection: "Rejection",
  next_step: "Next step",
  offer: "Offer",
  other: "Email",
};

function formatEmailRelative(
  value: string | null | undefined,
  now: Date = new Date(),
): string | null {
  const then = parseTimestamp(value ?? null);
  if (!then) return null;
  const diffMs = now.getTime() - then.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return then.toLocaleDateString();
}

/**
 * One-line summary of the most recently received email attached to an
 * application, suitable for inline display in the list. Returns null when
 * the application has no attached email.
 */
export function lastEmailSummary(
  app: Application,
  now: Date = new Date(),
): string | null {
  const link = app.last_email_link;
  if (!link) return null;
  const label = link.classified_status
    ? EMAIL_CLASSIFICATION_LABELS[link.classified_status] ?? "Email"
    : "Email";
  const senderPart = link.sender ? ` from ${link.sender}` : "";
  const ago = formatEmailRelative(link.received_at, now);
  const timePart = ago ? ` · ${ago}` : "";
  return `${label}${senderPart}${timePart}`;
}
