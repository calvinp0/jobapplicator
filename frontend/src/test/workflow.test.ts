import { describe, expect, it } from "vitest";
import type {
  Application,
  ClaudeRun,
  Job,
  ResumeVersion,
} from "../api";
import {
  computeJobStage,
  draftLabel,
  draftStatusLabel,
  jobStageLabel,
  runIsActive,
  runIsComplete,
  runNeedsImport,
  runStatusLabel,
} from "../lib/workflow";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Acme",
    title: "Engineer",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
    ...overrides,
  };
}

function makeRun(overrides: Partial<ClaudeRun> = {}): ClaudeRun {
  return {
    id: "run-1",
    job_id: "job-1",
    master_resume_id: "mr-1",
    evidence_bank_id: null,
    run_dir: "/tmp/run-1",
    status: "created",
    prompt_hash: null,
    input_hash: null,
    output_hash: null,
    created_at: "2026-05-22T10:00:00Z",
    started_at: null,
    completed_at: null,
    error_message: null,
    ...overrides,
  };
}

function makeVersion(overrides: Partial<ResumeVersion> = {}): ResumeVersion {
  return {
    id: "version-1",
    job_id: "job-1",
    master_resume_id: "mr-1",
    claude_run_id: "run-1",
    version_number: 1,
    content_markdown: null,
    docx_path: null,
    pdf_path: null,
    content_hash: null,
    prompt_hash: null,
    source: "claude",
    approved_at: null,
    created_at: "2026-05-22T11:00:00Z",
    ...overrides,
  };
}

function makeApp(overrides: Partial<Application> = {}): Application {
  return {
    id: "app-1",
    job_id: "job-1",
    resume_version_id: "version-1",
    status: "draft",
    submitted_at: null,
    created_at: "2026-05-22T12:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    ...overrides,
  };
}

describe("runStatusLabel", () => {
  it("maps every known status to a user-facing label", () => {
    expect(runStatusLabel("created")).toBe("Queued");
    expect(runStatusLabel("running")).toBe("Tailoring in progress");
    expect(runStatusLabel("completed")).toBe("Tailoring finished — loading draft");
    expect(runStatusLabel("imported")).toBe("Draft ready to review");
    expect(runStatusLabel("failed")).toBe("Tailoring failed");
  });

  it("falls back to the raw value for unknown statuses", () => {
    expect(runStatusLabel("weird")).toBe("weird");
  });
});

describe("runIsActive", () => {
  it("is true only for created and running", () => {
    expect(runIsActive("created")).toBe(true);
    expect(runIsActive("running")).toBe(true);
    expect(runIsActive("completed")).toBe(false);
    expect(runIsActive("imported")).toBe(false);
    expect(runIsActive("failed")).toBe(false);
  });
});

describe("runIsComplete", () => {
  it("is true only for completed and imported", () => {
    expect(runIsComplete("completed")).toBe(true);
    expect(runIsComplete("imported")).toBe(true);
    expect(runIsComplete("created")).toBe(false);
    expect(runIsComplete("running")).toBe(false);
    expect(runIsComplete("failed")).toBe(false);
  });
});

describe("runNeedsImport", () => {
  it("is true when a completed run has no resume version referencing it", () => {
    const run = makeRun({ id: "run-1", status: "completed" });
    expect(runNeedsImport(run, [])).toBe(true);
    expect(
      runNeedsImport(run, [makeVersion({ claude_run_id: "other-run" })]),
    ).toBe(true);
  });

  it("is false when a completed run has been imported into a version", () => {
    const run = makeRun({ id: "run-1", status: "completed" });
    expect(
      runNeedsImport(run, [makeVersion({ claude_run_id: "run-1" })]),
    ).toBe(false);
  });

  it("is false for non-completed statuses regardless of versions", () => {
    expect(
      runNeedsImport(makeRun({ id: "run-1", status: "running" }), []),
    ).toBe(false);
    expect(
      runNeedsImport(makeRun({ id: "run-1", status: "imported" }), []),
    ).toBe(false);
    expect(
      runNeedsImport(makeRun({ id: "run-1", status: "failed" }), []),
    ).toBe(false);
    expect(
      runNeedsImport(makeRun({ id: "run-1", status: "created" }), []),
    ).toBe(false);
  });
});

describe("draftLabel", () => {
  it("returns 1-based Draft labels", () => {
    expect(draftLabel(0)).toBe("Draft 1");
    expect(draftLabel(1)).toBe("Draft 2");
    expect(draftLabel(4)).toBe("Draft 5");
  });
});

describe("draftStatusLabel", () => {
  it("returns Approved when an approval timestamp is present", () => {
    expect(draftStatusLabel("2026-05-22T10:00:00Z")).toBe("Approved");
  });

  it("returns Awaiting review when there is no approval timestamp", () => {
    expect(draftStatusLabel(null)).toBe("Awaiting review");
  });
});

describe("jobStageLabel", () => {
  it("maps each stage to its user-facing label", () => {
    expect(jobStageLabel("captured")).toBe("Awaiting tailoring");
    expect(jobStageLabel("tailoring")).toBe("Tailoring in progress");
    expect(jobStageLabel("draft_ready")).toBe("Draft ready to review");
    expect(jobStageLabel("approved")).toBe("Approved — ready to send");
    expect(jobStageLabel("sent")).toBe("Sent");
  });
});

describe("computeJobStage", () => {
  it("returns sent when the application is submitted", () => {
    const job = makeJob();
    const app = makeApp({ status: "submitted" });
    expect(computeJobStage(job, [], [], app)).toBe("sent");
  });

  it("returns approved when any version for the job is approved", () => {
    const job = makeJob();
    const versions = [makeVersion({ approved_at: "2026-05-22T13:00:00Z" })];
    expect(computeJobStage(job, [], versions, null)).toBe("approved");
  });

  it("returns draft_ready when versions exist but none are approved", () => {
    const job = makeJob();
    const versions = [makeVersion()];
    expect(computeJobStage(job, [], versions, null)).toBe("draft_ready");
  });

  it("returns tailoring when an active run exists with no versions yet", () => {
    const job = makeJob();
    const runs = [makeRun({ status: "running" })];
    expect(computeJobStage(job, runs, [], null)).toBe("tailoring");
  });

  it("returns tailoring when a completed run still needs import", () => {
    const job = makeJob();
    const runs = [makeRun({ status: "completed" })];
    expect(computeJobStage(job, runs, [], null)).toBe("tailoring");
  });

  it("returns captured when there are no runs, versions, or applications", () => {
    const job = makeJob();
    expect(computeJobStage(job, [], [], null)).toBe("captured");
  });

  it("ignores runs and versions belonging to other jobs", () => {
    const job = makeJob({ id: "job-1" });
    const runs = [makeRun({ job_id: "job-2", status: "running" })];
    const versions = [makeVersion({ job_id: "job-2" })];
    expect(computeJobStage(job, runs, versions, null)).toBe("captured");
  });

  it("treats a non-submitted application as not sent", () => {
    const job = makeJob();
    const app = makeApp({ status: "draft" });
    expect(computeJobStage(job, [], [], app)).toBe("captured");
  });
});
