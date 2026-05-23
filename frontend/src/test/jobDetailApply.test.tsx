import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getJobMock,
  listMasterResumesMock,
  listEvidenceBanksMock,
  listResumeVersionsMock,
  createRunMock,
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
    createRunMock: vi.fn(),
    createApplicationMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getJob: getJobMock,
  listMasterResumes: listMasterResumesMock,
  listEvidenceBanks: listEvidenceBanksMock,
  listResumeVersions: listResumeVersionsMock,
  createRun: createRunMock,
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
};

describe("JobDetailPage Apply section", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the gating message when no approved version exists", async () => {
    listResumeVersionsMock.mockResolvedValue([pendingVersion]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /^apply$/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/approve a resume version first/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /create application/i }),
    ).not.toBeInTheDocument();
  });

  it("creates an application from an approved version and navigates", async () => {
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
        screen.getByRole("heading", { level: 3, name: /^apply$/i }),
      ).toBeInTheDocument(),
    );

    const createButtons = screen.getAllByRole("button", {
      name: /create application/i,
    });
    expect(createButtons).toHaveLength(1);

    await user.click(createButtons[0]);

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
});
