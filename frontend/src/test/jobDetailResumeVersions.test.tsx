import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getJobMock,
  listMasterResumesMock,
  listEvidenceBanksMock,
  listResumeVersionsMock,
  listRunsMock,
  listApplicationsMock,
  listRevisionFeedbacksMock,
  createRunMock,
  invokeRunMock,
  createApplicationMock,
  ApiErrorMock,
} = vi.hoisted(() => {
  class ApiErrorMock extends Error {
    status: number;
    body: unknown;
    constructor(message: string, status: number, body: unknown) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
    }
  }
  return {
    getJobMock: vi.fn(),
    listMasterResumesMock: vi.fn(),
    listEvidenceBanksMock: vi.fn(),
    listResumeVersionsMock: vi.fn(),
    listRunsMock: vi.fn(),
    listApplicationsMock: vi.fn(),
    listRevisionFeedbacksMock: vi.fn(),
    createRunMock: vi.fn(),
    invokeRunMock: vi.fn(),
    createApplicationMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getJob: getJobMock,
  listMasterResumes: listMasterResumesMock,
  listEvidenceBanks: listEvidenceBanksMock,
  listResumeVersions: listResumeVersionsMock,
  listRuns: listRunsMock,
  listApplications: listApplicationsMock,
  listRevisionFeedbacks: listRevisionFeedbacksMock,
  createRun: createRunMock,
  invokeRun: invokeRunMock,
  createApplication: createApplicationMock,
  getRun: vi.fn(() => new Promise(() => {})),
  importRun: vi.fn(() => new Promise(() => {})),
  getRunLog: vi.fn(() =>
    Promise.resolve({ run_id: "stub", lines: [], truncated: false }),
  ),
  ApiError: ApiErrorMock,
}));

import { JobDetailPage } from "../pages/JobDetailPage";

function renderJob(jobId: string) {
  return render(
    <MemoryRouter initialEntries={[`/jobs/${jobId}`]}>
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const job = {
  id: "job-1",
  source_platform: "linkedin",
  external_url: null,
  external_job_id: null,
  company: "Acme Corp",
  title: "Senior Engineer",
  location: null,
  description_text: "Build things.",
  application_method: null,
  created_from_capture_id: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const versions = [
  {
    id: "version-1",
    job_id: "job-1",
    master_resume_id: "resume-1",
    claude_run_id: "run-1",
    version_number: 1,
    content_markdown: null,
    docx_path: null,
    pdf_path: null,
    content_hash: null,
    prompt_hash: null,
    source: "claude_run",
    approved_at: "2026-05-22T13:00:00Z",
    created_at: "2026-05-22T12:00:00Z",
  },
  {
    id: "version-2",
    job_id: "job-1",
    master_resume_id: "resume-1",
    claude_run_id: "run-2",
    version_number: 2,
    content_markdown: null,
    docx_path: null,
    pdf_path: null,
    content_hash: null,
    prompt_hash: null,
    source: "claude_run",
    approved_at: null,
    created_at: "2026-05-22T13:00:00Z",
  },
  {
    id: "version-3",
    job_id: "other-job",
    master_resume_id: "resume-1",
    claude_run_id: null,
    version_number: 1,
    content_markdown: null,
    docx_path: null,
    pdf_path: null,
    content_hash: null,
    prompt_hash: null,
    source: "manual",
    approved_at: null,
    created_at: "2026-05-22T11:00:00Z",
  },
];

const inFlightRun = {
  id: "run-in-flight",
  job_id: "job-1",
  master_resume_id: "resume-1",
  evidence_bank_id: null,
  run_dir: "/tmp/run",
  status: "running",
  prompt_hash: null,
  input_hash: null,
  output_hash: null,
  created_at: "2026-05-22T14:00:00Z",
  started_at: "2026-05-22T14:00:01Z",
  completed_at: null,
  error_message: null,
};

const importedRun = {
  ...inFlightRun,
  id: "run-imported",
  status: "imported",
  created_at: "2026-05-22T13:00:00Z",
};

const otherJobRun = {
  ...inFlightRun,
  id: "run-other",
  job_id: "other-job",
  status: "running",
};

describe("JobDetailPage step 4 — Review and approve drafts", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue(versions);
    listRunsMock.mockResolvedValue([inFlightRun, importedRun, otherJobRun]);
    listApplicationsMock.mockResolvedValue([]);
    listRevisionFeedbacksMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists drafts for this job using workflow language", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /review and approve drafts/i,
        }),
      ).toBeInTheDocument(),
    );

    const d1 = screen.getByRole("link", { name: /^draft 1$/i });
    const d2 = screen.getByRole("link", { name: /^draft 2$/i });

    expect(d1).toHaveAttribute("href", "/resume-versions/version-1");
    expect(d2).toHaveAttribute("href", "/resume-versions/version-2");

    expect(
      screen.queryByRole("link", { name: /version 3/i }),
    ).not.toBeInTheDocument();

    const statuses = screen.getAllByText(
      (_text, el) =>
        el?.classList.contains("resume-version-status") ?? false,
    );
    const statusTexts = statuses.map((el) => el.textContent);
    expect(statusTexts).toContain("Approved");
    expect(statusTexts).toContain("Awaiting review");
    expect(statusTexts.some((t) => t === "Pending")).toBe(false);
  });

  it("renders the empty state when no drafts exist for the job", async () => {
    listResumeVersionsMock.mockResolvedValue([]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /review and approve drafts/i,
        }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/no drafts yet/i),
    ).toBeInTheDocument();
  });

  it("shows a 'revises Draft N' pointer for drafts produced by a revision run", async () => {
    listRevisionFeedbacksMock.mockResolvedValue([
      {
        id: "rf-1",
        job_id: "job-1",
        source_resume_version_id: "version-1",
        followup_claude_run_id: "run-2",
        feedback_markdown: "Shorten.",
        status: "used",
        created_at: "2026-05-22T12:30:00Z",
      },
    ]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /review and approve drafts/i,
        }),
      ).toBeInTheDocument(),
    );

    await waitFor(() =>
      expect(screen.getByText(/^revises Draft 1$/)).toBeInTheDocument(),
    );

    // Draft 1 (the source) is not labeled as revising anything.
    const draft1Item = screen
      .getByRole("link", { name: /^draft 1$/i })
      .closest("li");
    expect(draft1Item).not.toBeNull();
    expect(draft1Item?.textContent ?? "").not.toMatch(/revises/i);
  });

  it("does not render a 'revises' pointer when no revision feedback matches", async () => {
    listRevisionFeedbacksMock.mockResolvedValue([]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /review and approve drafts/i,
        }),
      ).toBeInTheDocument(),
    );

    expect(screen.queryByText(/revises Draft/i)).toBeNull();
  });

  it("shows the latest run's user-facing status inside step 3", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /generate a draft/i,
        }),
      ).toBeInTheDocument(),
    );

    const runLink = screen.getByRole("link", { name: /tailoring in progress/i });
    expect(runLink).toHaveAttribute("href", "/runs/run-in-flight");
  });
});
