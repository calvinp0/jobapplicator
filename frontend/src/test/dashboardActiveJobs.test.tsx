import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import type { Application, ClaudeRun, Job, ResumeVersion } from "../api";
import { buildActiveJobCard, buildJobView } from "../lib/dashboardJobs";
import { DashboardActiveJobs } from "../components/dashboard";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Example Aero Labs",
    title: "Scientific Machine Learning Engineer",
    location: "Remote",
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
    status: "running",
    prompt_hash: null,
    input_hash: null,
    output_hash: null,
    created_at: "2026-05-22T11:00:00Z",
    started_at: "2026-05-22T11:00:01Z",
    completed_at: null,
    error_message: null,
    ...overrides,
  };
}

function makeVersion(overrides: Partial<ResumeVersion> = {}): ResumeVersion {
  return {
    id: "v-1",
    job_id: "job-1",
    master_resume_id: "mr-1",
    claude_run_id: null,
    version_number: 1,
    content_markdown: null,
    docx_path: null,
    pdf_path: null,
    content_hash: null,
    prompt_hash: null,
    source: "claude",
    approved_at: null,
    created_at: "2026-05-22T11:30:00Z",
    ...overrides,
  };
}

function makeApp(overrides: Partial<Application> = {}): Application {
  return {
    id: "app-1",
    job_id: "job-1",
    resume_version_id: null,
    status: "draft",
    submitted_at: null,
    created_at: "2026-05-22T12:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    timeline_stage: "draft",
    last_email_link: null,
    email_link_count: 0,
    submission_status: "not_submitted",
    email_status: "not_watching",
    next_action: "",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: null,
    ...overrides,
  };
}

function view(
  job: Job,
  versions: ResumeVersion[] = [],
  apps: Application[] = [],
  runs: ClaudeRun[] = [],
) {
  return buildJobView(job, versions, apps, runs);
}

function renderSection(views: ReturnType<typeof view>[]) {
  return render(
    <MemoryRouter>
      <DashboardActiveJobs views={views} />
    </MemoryRouter>,
  );
}

describe("buildActiveJobCard next-action mapping", () => {
  it("maps a running tailoring run to View progress", () => {
    const card = buildActiveJobCard(
      view(makeJob(), [], [], [makeRun({ status: "running" })]),
    );
    expect(card.statusVariant).toBe("running");
    expect(card.statusLabel).toBe("Running");
    expect(card.primary.label).toBe("View progress");
    expect(card.primary.href).toBe("/runs/run-1");
  });

  it("maps a pending draft to Review draft", () => {
    const card = buildActiveJobCard(
      view(makeJob(), [makeVersion({ id: "v-9", approved_at: null })]),
    );
    expect(card.statusVariant).toBe("draft_ready");
    expect(card.statusLabel).toBe("Draft ready");
    expect(card.primary.label).toBe("Review draft");
    expect(card.primary.href).toBe("/resume-versions/v-9");
  });

  it("maps an approved draft to Continue application", () => {
    const card = buildActiveJobCard(
      view(
        makeJob(),
        [makeVersion({ id: "v-5", approved_at: "2026-05-22T12:00:00Z" })],
        [makeApp({ id: "app-7", status: "draft" })],
      ),
    );
    expect(card.statusVariant).toBe("approved");
    expect(card.statusLabel).toBe("Approved");
    expect(card.primary.label).toBe("Continue application");
    expect(card.primary.href).toBe("/applications/app-7");
  });

  it("maps a failed run to View failure with a concise error", () => {
    const card = buildActiveJobCard(
      view(
        makeJob(),
        [],
        [],
        [
          makeRun({
            status: "failed",
            error_message: "Missing tailored_resume.json\nstack trace here",
          }),
        ],
      ),
    );
    expect(card.statusVariant).toBe("failed");
    expect(card.statusLabel).toBe("Failed");
    expect(card.primary.label).toBe("View failure");
    expect(card.primary.href).toBe("/runs/run-1");
    expect(card.error).toBe("Missing tailored_resume.json");
  });

  it("falls back to Review job for a freshly captured job", () => {
    const card = buildActiveJobCard(view(makeJob()));
    expect(card.statusVariant).toBe("captured");
    expect(card.primary.label).toBe("Review job");
    expect(card.primary.href).toBe("/jobs/job-1");
  });

  it("never duplicates the primary action inside the overflow menu", () => {
    const card = buildActiveJobCard(
      view(makeJob(), [makeVersion({ id: "v-9", approved_at: null })]),
    );
    expect(
      card.secondary.some((a) => a.href === card.primary.href),
    ).toBe(false);
  });
});

describe("DashboardActiveJobs rendering", () => {
  it("renders one card per active job", () => {
    renderSection([
      view(makeJob({ id: "job-1", title: "SML Engineer" })),
      view(makeJob({ id: "job-2", title: "Staff Engineer" })),
    ]);
    expect(screen.getByText("SML Engineer")).toBeInTheDocument();
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders status as a compact indicator, not a large pill", () => {
    const { container } = renderSection([
      view(makeJob(), [makeVersion({ approved_at: null })]),
    ]);
    expect(container.querySelector(".app-status")).not.toBeNull();
    expect(container.querySelector(".app-status-dot")).not.toBeNull();
    // The old oversized pill class must not appear on these cards.
    expect(container.querySelector(".status-badge")).toBeNull();
  });

  it("shows exactly one primary action button per card", () => {
    const { container } = renderSection([
      view(makeJob(), [makeVersion({ approved_at: null })]),
    ]);
    expect(container.querySelectorAll(".application-card-primary")).toHaveLength(
      1,
    );
  });

  it("keeps secondary actions hidden behind an overflow menu", async () => {
    const user = userEvent.setup();
    renderSection([
      view(makeJob(), [makeVersion({ id: "v-9", approved_at: null })]),
    ]);
    // Secondary action is not visible until the menu is opened.
    expect(screen.queryByRole("menuitem", { name: /review job/i })).toBeNull();
    await user.click(screen.getByRole("button", { name: /more actions/i }));
    expect(
      screen.getByRole("menuitem", { name: /review job/i }),
    ).toBeInTheDocument();
  });

  it("renders the Next: line describing the primary action", () => {
    renderSection([
      view(makeJob(), [makeVersion({ id: "v-9", approved_at: null })]),
    ]);
    expect(screen.getByText(/next:/i)).toBeInTheDocument();
    expect(screen.getByText(/review resume changes/i)).toBeInTheDocument();
  });

  it("surfaces a failure summary when the latest run failed", () => {
    renderSection([
      view(
        makeJob(),
        [],
        [],
        [
          makeRun({
            status: "failed",
            error_message: "Missing tailored_resume.json",
          }),
        ],
      ),
    ]);
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(
      screen.getByText(/missing tailored_resume\.json/i),
    ).toBeInTheDocument();
  });

  it("renders a polished empty state with Add job and Open captures", () => {
    renderSection([]);
    expect(screen.getByText(/no active applications yet/i)).toBeInTheDocument();
    const region = screen.getByRole("status");
    expect(
      within(region).getByRole("link", { name: /add job/i }),
    ).toHaveAttribute("href", "/jobs");
    expect(
      within(region).getByRole("link", { name: /open captures/i }),
    ).toHaveAttribute("href", "/captures");
  });
});
