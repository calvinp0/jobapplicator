import { describe, expect, it } from "vitest";
import {
  buildApplicationRowActions,
  pipelineStatusLabel,
  pipelineStatusVariant,
} from "../lib/applicationActions";
import type { Application } from "../api";

function makeApp(overrides: Partial<Application> = {}): Application {
  return {
    id: "app-1",
    job_id: "job-1",
    resume_version_id: null,
    status: "approved",
    submitted_at: null,
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T11:00:00Z",
    timeline_stage: "draft",
    last_email_link: null,
    email_link_count: 0,
    submission_status: "not_submitted",
    email_status: "not_watching",
    next_action: "Ready to submit",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: null,
    ...overrides,
  };
}

describe("pipelineStatusLabel / pipelineStatusVariant", () => {
  it("maps timeline stages to short labels", () => {
    expect(pipelineStatusLabel("confirmation_received")).toBe("Confirmation");
    expect(pipelineStatusLabel("sent")).toBe("Submitted");
    expect(pipelineStatusLabel("draft")).toBe("Draft");
  });

  it("maps timeline stages to colour variants", () => {
    expect(pipelineStatusVariant("sent")).toBe("submitted");
    expect(pipelineStatusVariant("rejected")).toBe("rejected");
    expect(pipelineStatusVariant("something-new")).toBe("default");
  });
});

describe("buildApplicationRowActions primary action", () => {
  it("returns Continue for an approved draft ready to send", () => {
    const { primary } = buildApplicationRowActions(makeApp());
    expect(primary.label).toBe("Continue");
    expect(primary.href).toBe("/applications/app-1");
  });

  it("returns Review draft (to the resume version) for an un-approved draft", () => {
    const { primary } = buildApplicationRowActions(
      makeApp({ status: "generated", resume_version_id: "v-9" }),
    );
    expect(primary.label).toBe("Review draft");
    expect(primary.href).toBe("/resume-versions/v-9");
  });

  it("returns Generate draft when a draft has no resume version", () => {
    const { primary } = buildApplicationRowActions(
      makeApp({ status: "draft", resume_version_id: null }),
    );
    expect(primary.label).toBe("Generate draft");
  });

  it("returns Open for a submitted/confirmation row", () => {
    const { primary } = buildApplicationRowActions(
      makeApp({
        status: "submitted",
        submission_status: "submitted",
        submitted_at: "2026-05-22T12:00:00Z",
        timeline_stage: "confirmation_received",
        next_action: "Waiting for response",
      }),
    );
    expect(primary.label).toBe("Open");
    expect(primary.href).toBe("/applications/app-1");
  });

  it("returns View progress for a running tailoring run", () => {
    const { primary } = buildApplicationRowActions(
      makeApp({ latest_run_id: "run-3", latest_run_status: "running" }),
    );
    expect(primary.label).toBe("View progress");
    expect(primary.href).toBe("/runs/run-3");
  });

  it("returns Review failure for a failed tailoring run", () => {
    const { primary } = buildApplicationRowActions(
      makeApp({ latest_run_id: "run-3", latest_run_status: "failed" }),
    );
    expect(primary.label).toBe("Review failure");
  });

  it("returns Review when the email needs review", () => {
    const { primary } = buildApplicationRowActions(
      makeApp({
        status: "submitted",
        submission_status: "submitted",
        timeline_stage: "sent",
        email_status: "needs_review",
      }),
    );
    expect(primary.label).toBe("Review");
  });
});

describe("buildApplicationRowActions secondary menu", () => {
  it("keeps the mutation actions out of the primary slot", () => {
    const { primary, secondary } = buildApplicationRowActions(makeApp());
    expect(primary.kind).toBe("link");
    const buttons = secondary.filter((a) => a.kind === "button");
    expect(buttons.map((b) => b.key).sort()).toEqual([
      "interview",
      "rejected",
      "submit",
    ]);
  });

  it("omits mutation actions that do not apply to a rejected row", () => {
    const { secondary } = buildApplicationRowActions(
      makeApp({
        status: "rejected",
        submission_status: "submitted",
        timeline_stage: "rejected",
      }),
    );
    expect(secondary.some((a) => a.kind === "button")).toBe(false);
  });

  it("never duplicates the primary destination in the menu", () => {
    const { primary, secondary } = buildApplicationRowActions(
      makeApp({
        status: "submitted",
        submission_status: "submitted",
        timeline_stage: "sent",
        latest_run_id: "run-1",
        latest_run_status: "imported",
        resume_version_id: "v-1",
      }),
    );
    const links = secondary.filter((a) => a.kind === "link");
    expect(links.every((a) => a.href !== primary.href)).toBe(true);
  });
});
