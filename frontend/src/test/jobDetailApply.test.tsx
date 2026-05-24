import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  ApiError: ApiErrorMock,
}));

import { JobDetailPage } from "../pages/JobDetailPage";

function renderJob(jobId: string) {
  return render(
    <MemoryRouter initialEntries={[`/jobs/${jobId}`]}>
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        <Route
          path="/applications/:applicationId"
          element={<div>application detail stub</div>}
        />
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

const approvedVersion = {
  id: "version-approved",
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
};

const pendingVersion = {
  ...approvedVersion,
  id: "version-pending",
  approved_at: null,
  version_number: 2,
  created_at: "2026-05-22T13:00:00Z",
};

describe("JobDetailPage step 5 — Send your application", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);
    listRevisionFeedbacksMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the workflow-language gating copy when no approved draft exists", async () => {
    listResumeVersionsMock.mockResolvedValue([pendingVersion]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /send your application/i,
        }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/pick an approved draft on the job page first/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /start application/i }),
    ).not.toBeInTheDocument();
  });

  it("creates an application from an approved draft and navigates", async () => {
    const user = userEvent.setup();
    listResumeVersionsMock.mockResolvedValue([approvedVersion, pendingVersion]);
    createApplicationMock.mockResolvedValue({
      id: "app-1",
      job_id: "job-1",
      resume_version_id: "version-approved",
      status: "approved",
      submitted_at: null,
      created_at: "2026-05-22T15:00:00Z",
      updated_at: "2026-05-22T15:00:00Z",
    });

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /send your application/i,
        }),
      ).toBeInTheDocument(),
    );

    const startButtons = screen.getAllByRole("button", {
      name: /start application/i,
    });
    expect(startButtons).toHaveLength(1);

    await user.click(startButtons[0]);

    await waitFor(() =>
      expect(createApplicationMock).toHaveBeenCalledWith({
        job_id: "job-1",
        resume_version_id: "version-approved",
        status: "approved",
      }),
    );

    await waitFor(() =>
      expect(screen.getByText(/application detail stub/i)).toBeInTheDocument(),
    );
  });

  it("lists applications for this job and links to /applications/:id", async () => {
    listResumeVersionsMock.mockResolvedValue([approvedVersion]);
    listApplicationsMock.mockResolvedValue([
      {
        id: "app-1",
        job_id: "job-1",
        resume_version_id: "version-approved",
        status: "approved",
        submitted_at: null,
        created_at: "2026-05-22T15:00:00Z",
        updated_at: "2026-05-22T15:00:00Z",
      },
      {
        id: "app-other",
        job_id: "other-job",
        resume_version_id: null,
        status: "approved",
        submitted_at: null,
        created_at: "2026-05-22T15:00:00Z",
        updated_at: "2026-05-22T15:00:00Z",
      },
    ]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /send your application/i,
        }),
      ).toBeInTheDocument(),
    );

    const link = screen.getByRole("link", { name: /application opened/i });
    expect(link).toHaveAttribute("href", "/applications/app-1");

    expect(
      screen.queryByRole("link", { name: /app-other/i }),
    ).not.toBeInTheDocument();
  });

  it("hides Start application buttons when a Sent application exists", async () => {
    listResumeVersionsMock.mockResolvedValue([approvedVersion]);
    listApplicationsMock.mockResolvedValue([
      {
        id: "app-1",
        job_id: "job-1",
        resume_version_id: "version-approved",
        status: "submitted",
        submitted_at: "2026-05-22T16:00:00Z",
        created_at: "2026-05-22T15:00:00Z",
        updated_at: "2026-05-22T16:00:00Z",
      },
    ]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: /send your application/i,
        }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.queryByRole("button", { name: /start application/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/^sent on /i)).toBeInTheDocument();
  });
});
