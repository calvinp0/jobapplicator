import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getJobMock,
  listMasterResumesMock,
  listEvidenceBanksMock,
  listResumeVersionsMock,
  createRunMock,
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
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getJob: getJobMock,
  listMasterResumes: listMasterResumesMock,
  listEvidenceBanks: listEvidenceBanksMock,
  listResumeVersions: listResumeVersionsMock,
  createRun: createRunMock,
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

describe("JobDetailPage resume versions section", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue(versions);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists only versions for this job and links to detail pages", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /resume versions/i }),
      ).toBeInTheDocument(),
    );

    const v1 = screen.getByRole("link", { name: /version 1/i });
    const v2 = screen.getByRole("link", { name: /version 2/i });

    expect(v1).toHaveAttribute("href", "/resume-versions/version-1");
    expect(v2).toHaveAttribute("href", "/resume-versions/version-2");

    expect(
      screen.queryByRole("link", { name: /version 3/i }),
    ).not.toBeInTheDocument();

    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders the empty state when no versions exist for the job", async () => {
    listResumeVersionsMock.mockResolvedValue([]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /resume versions/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/no resume versions for this job yet/i),
    ).toBeInTheDocument();
  });
});
