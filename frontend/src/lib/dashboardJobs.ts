import type { Application, ClaudeRun, Job, ResumeVersion } from "../api";
import {
  computeJobStage,
  formatElapsedSince,
  parseTimestamp,
  runIsActive,
  runNeedsImport,
  runStartTimestamp,
  type JobStage,
} from "./workflow";

/**
 * Per-job snapshot the dashboard "Active jobs" section renders from. The
 * caller passes the full run / version / application sets; everything is
 * filtered down to a single job here so the card components stay dumb
 * renderers that never inspect raw backend records.
 */
export interface JobView {
  job: Job;
  stage: JobStage;
  approvedVersion: ResumeVersion | null;
  pendingVersion: ResumeVersion | null;
  inFlightRun: ClaudeRun | null;
  latestRun: ClaudeRun | null;
  submittedApp: Application | null;
  openApp: Application | null;
}

export function buildJobView(
  job: Job,
  versions: ResumeVersion[],
  applications: Application[],
  runs: ClaudeRun[],
): JobView {
  const jobApps = applications.filter((a) => a.job_id === job.id);
  const submittedApp = jobApps.find((a) => a.status === "submitted") ?? null;
  const openApp = jobApps.find((a) => a.status !== "submitted") ?? null;
  const relevantApp = submittedApp ?? openApp;
  const stage = computeJobStage(job, runs, versions, relevantApp);
  const jobVersions = versions
    .filter((v) => v.job_id === job.id)
    .sort((a, b) => b.version_number - a.version_number);
  const approvedVersion =
    jobVersions.find((v) => v.approved_at !== null) ?? null;
  const pendingVersion =
    jobVersions.find((v) => v.approved_at === null) ?? null;
  const jobRuns = runs.filter((r) => r.job_id === job.id);
  const inFlightRun =
    jobRuns.find(
      (r) => runIsActive(r.status) || runNeedsImport(r, versions),
    ) ?? null;
  const latestRun =
    jobRuns
      .slice()
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null;
  return {
    job,
    stage,
    approvedVersion,
    pendingVersion,
    inFlightRun,
    latestRun,
    submittedApp,
    openApp,
  };
}

/**
 * Compact, colour-coded status the active-job card surfaces. Deliberately a
 * small closed set so the dot + label treatment stays consistent and never
 * leaks raw backend status enums.
 */
export type ActiveJobStatusVariant =
  | "running"
  | "failed"
  | "draft_ready"
  | "approved"
  | "captured";

export interface ActiveJobAction {
  label: string;
  href: string;
}

export interface ActiveJobCard {
  jobId: string;
  title: string;
  company: string;
  location: string | null;
  statusVariant: ActiveJobStatusVariant;
  statusLabel: string;
  /** The single obvious next thing to do — also the primary button label. */
  primary: ActiveJobAction;
  /** Short phrase rendered after "Next:" to make the flow explicit. */
  nextLabel: string;
  /** Everything else, surfaced behind the overflow menu. */
  secondary: ActiveJobAction[];
  /** Muted one-line recent-activity summary, or null when unavailable. */
  activity: string | null;
  /** Concise failure message for the failed state, else null. */
  error: string | null;
}

/** Relative "x ago" label, or null when the timestamp is missing/unparseable. */
export function formatAgo(
  value: string | null | undefined,
  now: Date = new Date(),
): string | null {
  const then = parseTimestamp(value ?? null);
  if (!then) return null;
  const minutes = Math.round((now.getTime() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return then.toLocaleDateString();
}

/** First line of a run error, trimmed to a card-friendly length. */
function conciseError(message: string | null): string {
  const first = (message ?? "").split("\n")[0].trim();
  if (!first) return "Run failed — open the run for details.";
  return first.length > 120 ? `${first.slice(0, 117)}…` : first;
}

/**
 * Every action available for a job, in menu order. The primary action is
 * filtered out of this list by the caller so the overflow menu never
 * duplicates the main button.
 */
function allActions(view: JobView): ActiveJobAction[] {
  const out: ActiveJobAction[] = [
    { label: "Review job", href: `/jobs/${view.job.id}` },
  ];
  if (view.approvedVersion) {
    out.push({
      label: "Open resume",
      href: `/resume-versions/${view.approvedVersion.id}`,
    });
  }
  if (view.pendingVersion) {
    out.push({
      label: "Open draft",
      href: `/resume-versions/${view.pendingVersion.id}`,
    });
  }
  if (view.openApp) {
    out.push({
      label: "View application",
      href: `/applications/${view.openApp.id}`,
    });
  }
  if (view.latestRun) {
    out.push({
      label: "View latest run",
      href: `/runs/${view.latestRun.id}`,
    });
  }
  return out;
}

/**
 * Reduce a {@link JobView} to the single primary action, compact status, and
 * secondary menu the card renders. Priority mirrors the workflow: a live run
 * trumps everything, then approved, then a draft to review, then a failed run,
 * then the freshly-captured fallback.
 */
export function buildActiveJobCard(
  view: JobView,
  now: Date = new Date(),
): ActiveJobCard {
  const base = {
    jobId: view.job.id,
    title: view.job.title,
    company: view.job.company,
    location: view.job.location,
  };
  const lastRunAgo = formatAgo(view.latestRun?.created_at ?? null, now);

  let card: Omit<ActiveJobCard, keyof typeof base | "secondary"> & {
    primary: ActiveJobAction;
  };

  if (view.inFlightRun) {
    const elapsed = formatElapsedSince(
      runStartTimestamp(view.inFlightRun),
      now,
    );
    const elapsedOk = elapsed !== "elapsed time unavailable";
    card = {
      statusVariant: "running",
      statusLabel: "Running",
      primary: {
        label: "View progress",
        href: `/runs/${view.inFlightRun.id}`,
      },
      nextLabel: "View progress",
      activity: elapsedOk
        ? `Tailoring resume · ${elapsed} elapsed`
        : "Tailoring resume",
      error: null,
    };
  } else if (view.stage === "approved" && view.approvedVersion) {
    const href = view.openApp
      ? `/applications/${view.openApp.id}`
      : `/jobs/${view.job.id}`;
    card = {
      statusVariant: "approved",
      statusLabel: "Approved",
      primary: { label: "Continue application", href },
      nextLabel: "Continue application",
      activity: lastRunAgo ? `Last run: ${lastRunAgo} · Resume ready` : "Resume ready",
      error: null,
    };
  } else if (view.stage === "draft_ready" && view.pendingVersion) {
    card = {
      statusVariant: "draft_ready",
      statusLabel: "Draft ready",
      primary: {
        label: "Review draft",
        href: `/resume-versions/${view.pendingVersion.id}`,
      },
      nextLabel: "Review resume changes",
      activity: lastRunAgo ? `Last run: ${lastRunAgo} · Draft ready` : "Draft ready",
      error: null,
    };
  } else if (view.latestRun && view.latestRun.status === "failed") {
    card = {
      statusVariant: "failed",
      statusLabel: "Failed",
      primary: { label: "View failure", href: `/runs/${view.latestRun.id}` },
      nextLabel: "Review failure",
      activity: lastRunAgo ? `Last run failed · ${lastRunAgo}` : "Last run failed",
      error: conciseError(view.latestRun.error_message),
    };
  } else {
    card = {
      statusVariant: "captured",
      statusLabel: "Captured",
      primary: { label: "Review job", href: `/jobs/${view.job.id}` },
      nextLabel: "Review job & start tailoring",
      activity: lastRunAgo ? `Last run: ${lastRunAgo}` : null,
      error: null,
    };
  }

  const secondary = allActions(view).filter(
    (a) => a.href !== card.primary.href,
  );

  return { ...base, ...card, secondary };
}
