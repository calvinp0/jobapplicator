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
    listRunsMock: vi.fn(),
    listApplicationsMock: vi.fn(),
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
  listRuns: listRunsMock,
  listApplications: listApplicationsMock,
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

const finishedRun = {
  ...inFlightRun,
  id: "run-finished",
  status: "completed-imported",
};

const otherJobRun = {
  ...inFlightRun,
  id: "run-other",
  job_id: "other-job",
  status: "running",
};

describe("JobDetailPage tailored resumes section", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue(versions);
    listRunsMock.mockResolvedValue([inFlightRun, finishedRun, otherJobRun]);
    listApplicationsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists only versions for this job and links to detail pages", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /tailored resumes/i }),
      ).toBeInTheDocument(),
    );

    const v1 = screen.getByRole("link", { name: /version 1/i });
    const v2 = screen.getByRole("link", { name: /version 2/i });

    expect(v1).toHaveAttribute("href", "/resume-versions/version-1");
    expect(v2).toHaveAttribute("href", "/resume-versions/version-2");

    expect(
      screen.queryByRole("link", { name: /version 3/i }),
    ).not.toBeInTheDocument();

    const statuses = screen.getAllByText(
      (_text, el) =>
        el?.classList.contains("resume-version-status") ?? false,
    );
    const statusTexts = statuses.map((el) => el.textContent);
    expect(statusTexts).toContain("Approved");
    expect(statusTexts).toContain("Pending");
  });

  it("renders the empty state when no versions exist for the job", async () => {
    listResumeVersionsMock.mockResolvedValue([]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /tailored resumes/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/no resume versions for this job yet/i),
    ).toBeInTheDocument();
  });

  it("lists in-flight runs for this job and links to /runs/:id", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 4, name: /in-flight runs/i }),
      ).toBeInTheDocument(),
    );

    const runLink = screen.getByRole("link", { name: /run-in-flight/i });
    expect(runLink).toHaveAttribute("href", "/runs/run-in-flight");

    expect(
      screen.queryByRole("link", { name: /run-finished/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /run-other/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the empty state for in-flight runs when none qualify", async () => {
    listRunsMock.mockResolvedValue([finishedRun]);

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 4, name: /in-flight runs/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/no runs in flight for this job/i),
    ).toBeInTheDocument();
  });

  it("highlights the Approved stage when only an approved version exists", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /tailored resumes/i }),
      ).toBeInTheDocument(),
    );

    const track = screen.getByTestId("job-status-track");
    const active = track.querySelector(".job-status-step-active");
    expect(active?.textContent).toMatch(/approved/i);
  });

  it("highlights the Captured stage when no runs exist", async () => {
    listResumeVersionsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);

    renderJob("job-1");

    await waitFor(() =>
      expect(screen.getByTestId("job-status-track")).toBeInTheDocument(),
    );

    const track = screen.getByTestId("job-status-track");
    const active = track.querySelector(".job-status-step-active");
    expect(active?.textContent).toMatch(/captured/i);
  });

  it("highlights the Tailoring stage when runs exist but nothing is approved", async () => {
    listResumeVersionsMock.mockResolvedValue([
      { ...versions[1] },
    ]);
    listRunsMock.mockResolvedValue([inFlightRun]);

    renderJob("job-1");

    await waitFor(() =>
      expect(screen.getByTestId("job-status-track")).toBeInTheDocument(),
    );

    const track = screen.getByTestId("job-status-track");
    const active = track.querySelector(".job-status-step-active");
    expect(active?.textContent).toMatch(/tailoring/i);
  });
});
