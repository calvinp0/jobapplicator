import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  listJobsMock,
  listApplicationsMock,
  listRunsMock,
  listResumeVersionsMock,
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
    listJobsMock: vi.fn(),
    listApplicationsMock: vi.fn(),
    listRunsMock: vi.fn(),
    listResumeVersionsMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listJobs: listJobsMock,
  listApplications: listApplicationsMock,
  listRuns: listRunsMock,
  listResumeVersions: listResumeVersionsMock,
  ApiError: ApiErrorMock,
}));

import { DashboardPage } from "../pages/DashboardPage";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const jobs = [
  {
    id: "job-1",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Acme Corp",
    title: "Senior Engineer",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
];

const runs = [
  {
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
  },
];

const applications = [
  {
    id: "app-1",
    job_id: "job-1",
    resume_version_id: "version-1",
    status: "submitted",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:30:00Z",
    updated_at: "2026-05-22T12:00:00Z",
  },
];

describe("DashboardPage", () => {
  beforeEach(() => {
    listJobsMock.mockResolvedValue(jobs);
    listApplicationsMock.mockResolvedValue(applications);
    listRunsMock.mockResolvedValue(runs);
    listResumeVersionsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the loading state before fetches resolve", () => {
    listJobsMock.mockReturnValue(new Promise(() => {}));
    listApplicationsMock.mockReturnValue(new Promise(() => {}));
    listRunsMock.mockReturnValue(new Promise(() => {}));
    listResumeVersionsMock.mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument();
  });

  it("renders sections, summary counts, and links when data is populated", async () => {
    // job-1 has a submitted application, so no active jobs.
    // Add a second job that is still active.
    listJobsMock.mockResolvedValue([
      ...jobs,
      {
        id: "job-2",
        source_platform: "linkedin",
        external_url: null,
        external_job_id: null,
        company: "Beta Inc",
        title: "Platform Lead",
        location: null,
        description_text: "",
        application_method: null,
        created_from_capture_id: null,
        created_at: "2026-05-22T09:00:00Z",
        updated_at: "2026-05-22T09:00:00Z",
      },
    ]);

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /application cockpit/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/1 active jobs · 1 in-flight runs · 1 applications submitted/i),
    ).toBeInTheDocument();

    const links = screen.getAllByRole("link");
    const jobLink = links.find(
      (l) => l.getAttribute("href") === "/jobs/job-2",
    );
    expect(jobLink).toBeDefined();
    expect(screen.getAllByText(/platform lead/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/beta inc/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/awaiting tailoring/i)).toBeInTheDocument();

    const runLink = links.find(
      (l) => l.getAttribute("href") === "/runs/run-1",
    );
    expect(runLink).toBeDefined();
    const appLink = links.find(
      (l) => l.getAttribute("href") === "/applications/app-1",
    );
    expect(appLink).toBeDefined();

    expect(screen.getByText(/drafts approved/i)).toBeInTheDocument();
    expect(screen.queryByText(/resumes ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ready to apply/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/tailoring in progress/i).length).toBeGreaterThan(0);
  });

  it("renders the Approved — ready to send stage label for jobs with an approved draft", async () => {
    listJobsMock.mockResolvedValue([
      {
        id: "job-3",
        source_platform: "linkedin",
        external_url: null,
        external_job_id: null,
        company: "Gamma Co",
        title: "Staff Engineer",
        location: null,
        description_text: "",
        application_method: null,
        created_from_capture_id: null,
        created_at: "2026-05-22T08:00:00Z",
        updated_at: "2026-05-22T08:00:00Z",
      },
    ]);
    listApplicationsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue([
      {
        id: "v-3",
        job_id: "job-3",
        master_resume_id: "mr-1",
        claude_run_id: null,
        version_number: 1,
        content_markdown: null,
        docx_path: null,
        pdf_path: null,
        content_hash: null,
        prompt_hash: null,
        source: "claude",
        approved_at: "2026-05-22T09:00:00Z",
        created_at: "2026-05-22T08:30:00Z",
      },
    ]);

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /application cockpit/i }),
      ).toBeInTheDocument(),
    );

    expect(screen.getByText(/approved — ready to send/i)).toBeInTheDocument();
  });

  it("renders empty-state messages for every section when there is no data", async () => {
    listJobsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue([]);

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /application cockpit/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(/no active jobs yet — capture a job from the extension/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/no runs in progress/i)).toBeInTheDocument();
    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });

  it("renders an error message when one fetch rejects", async () => {
    listRunsMock.mockRejectedValue(
      new ApiErrorMock("backend exploded", 500, null),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/backend exploded/i),
    );
  });
});
