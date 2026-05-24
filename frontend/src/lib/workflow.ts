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
