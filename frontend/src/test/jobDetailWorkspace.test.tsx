import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
  getRunMock,
  importRunMock,
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
    getRunMock: vi.fn(),
    importRunMock: vi.fn(),
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
  getRun: getRunMock,
  importRun: importRunMock,
  getRunLog: vi.fn(() =>
    Promise.resolve({ run_id: "stub", lines: [], truncated: false }),
  ),
  getRunProgress: vi.fn(() =>
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
        <Route path="/runs/:runId" element={<div>run detail stub</div>} />
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
  description_text: "We are hiring. Build great things.",
  application_method: null,
  created_from_capture_id: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const resume = {
  id: "resume-1",
  name: "Generalist",
  source_path: null,
  content_markdown: "# Calvin",
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

describe("JobDetailPage five-step workspace", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([resume]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);
    listRevisionFeedbacksMock.mockResolvedValue([]);
    // Defensive defaults: the auto-import polling hook may fire `importRun`
    // and `getRun` in tests where a run lands in `completed` state. We
    // stall both with never-resolving promises so individual tests can
    // assert against the *initial* rendered state without racing the
    // auto-import effect's state updates.
    getRunMock.mockReturnValue(new Promise(() => {}));
    importRunMock.mockReturnValue(new Promise(() => {}));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders all five step headings in workflow order", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /senior engineer/i }),
      ).toBeInTheDocument(),
    );

    const headings = screen
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);

    expect(headings).toEqual([
      "Read the job description",
      "Choose resume source",
      "Generate a draft",
      "Review and approve drafts",
      "Send your application",
    ]);
  });

  it("exposes the job description as a clickable toggle button", async () => {
    const user = userEvent.setup();
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /senior engineer/i }),
      ).toBeInTheDocument(),
    );

    const toggle = screen.getByRole("button", {
      name: /read job description/i,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByText(/build great things/i),
    ).not.toBeInTheDocument();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/build great things/i)).toBeInTheDocument();
  });

  it("creates and invokes a run as one user action when clicking Generate draft", async () => {
    const user = userEvent.setup();
    createRunMock.mockResolvedValue({
      id: "run-new",
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      run_dir: "runs/run-new",
      status: "created",
      prompt_hash: null,
      input_hash: null,
      output_hash: null,
      created_at: "2026-05-22T12:00:00Z",
      started_at: null,
      completed_at: null,
      error_message: null,
    });
    invokeRunMock.mockResolvedValue({
      id: "run-new",
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      run_dir: "runs/run-new",
      status: "running",
      prompt_hash: null,
      input_hash: null,
      output_hash: null,
      created_at: "2026-05-22T12:00:00Z",
      started_at: "2026-05-22T12:00:01Z",
      completed_at: null,
      error_message: null,
    });

    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /senior engineer/i }),
      ).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText(/master resume/i),
      "resume-1",
    );
    await user.click(
      screen.getByRole("button", { name: /^generate draft$/i }),
    );

    await waitFor(() =>
      expect(createRunMock).toHaveBeenCalledTimes(1),
    );
    await waitFor(() => expect(invokeRunMock).toHaveBeenCalledWith("run-new"));
    expect(invokeRunMock).toHaveBeenCalledTimes(1);
  });

  it("renders the needs-import state when a completed run has no matching ResumeVersion", async () => {
    listRunsMock.mockResolvedValue([
      {
        id: "run-completed",
        job_id: "job-1",
        master_resume_id: "resume-1",
        evidence_bank_id: null,
        run_dir: "runs/run-completed",
        status: "completed",
        prompt_hash: null,
        input_hash: null,
        output_hash: null,
        created_at: "2026-05-22T13:00:00Z",
        started_at: "2026-05-22T13:00:01Z",
        completed_at: "2026-05-22T13:05:00Z",
        error_message: null,
      },
    ]);
    listResumeVersionsMock.mockResolvedValue([]);

    renderJob("job-1");

    const generateStep = await screen.findByRole("region", {
      name: /step 3: generate a draft/i,
    });

    const runLink = within(generateStep).getByRole("link", {
      name: /tailoring finished\. loading the generated draft/i,
    });
    expect(runLink).toHaveAttribute("href", "/runs/run-completed");
  });

  it("updates step 3 from `Tailoring in progress` to `Draft ready to review` after the poller observes completed → imported", async () => {
    const runningRun = {
      id: "run-1",
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      run_dir: "runs/run-1",
      status: "running",
      prompt_hash: null,
      input_hash: null,
      output_hash: null,
      created_at: "2026-05-22T13:00:00Z",
      started_at: "2026-05-22T13:00:01Z",
      completed_at: null,
      error_message: null,
    };
    const completedRunRecord = {
      ...runningRun,
      status: "completed",
      completed_at: "2026-05-22T13:05:00Z",
    };
    const importedRunRecord = {
      ...completedRunRecord,
      status: "imported",
    };
    const newVersion = {
      id: "version-1",
      job_id: "job-1",
      master_resume_id: "resume-1",
      claude_run_id: "run-1",
      version_number: 1,
      content_markdown: "# Resume",
      docx_path: "runs/run-1/output/resume.docx",
      pdf_path: null,
      content_hash: "abc",
      prompt_hash: "p",
      source: "claude_run",
      approved_at: null,
      created_at: "2026-05-22T13:06:00Z",
    };

    listRunsMock.mockResolvedValue([runningRun]);
    // Initial page-load fetch returns empty; the refresh triggered after a
    // successful auto-import returns the imported version. Matches real
    // backend behaviour after `POST /runs/{id}/import`.
    listResumeVersionsMock.mockReset();
    listResumeVersionsMock.mockResolvedValueOnce([]);
    listResumeVersionsMock.mockResolvedValue([newVersion]);
    getRunMock.mockReset();
    // First poll returns completed; second (post-import refresh) returns imported.
    getRunMock
      .mockResolvedValueOnce(completedRunRecord)
      .mockResolvedValueOnce(importedRunRecord);
    importRunMock.mockReset();
    importRunMock.mockResolvedValue(newVersion);

    // Fake timers must be active *before* render so the polling hook's
    // setInterval is mocked, not native.
    vi.useFakeTimers();
    try {
      renderJob("job-1");

      // Flush the initial-load microtasks (Promise.all of mocked API calls).
      await act(async () => {
        for (let i = 0; i < 8; i += 1) await Promise.resolve();
      });

      const generateStep = screen.getByRole("region", {
        name: /step 3: generate a draft/i,
      });
      expect(
        within(generateStep).getByText(/Tailoring in progress/i),
      ).toBeInTheDocument();

      // Advance one polling cycle. The poll observes `completed`; the
      // auto-import effect then fires `importRun` and follows with a
      // refetch that flips the run to `imported`.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      await act(async () => {
        for (let i = 0; i < 8; i += 1) await Promise.resolve();
      });

      expect(importRunMock).toHaveBeenCalledWith("run-1");

      const step3After = screen.getByRole("region", {
        name: /step 3: generate a draft/i,
      });
      expect(
        within(step3After).getByText(/Draft ready to review/i),
      ).toBeInTheDocument();
      expect(
        within(step3After).queryByText(/Tailoring in progress/i),
      ).not.toBeInTheDocument();

      // The newly-imported draft must appear in step 4 without the user
      // refreshing the page. This is the "show Draft 2, Draft 3
      // automatically" acceptance criterion.
      const step4 = screen.getByRole("region", {
        name: /step 4: review and approve drafts/i,
      });
      expect(within(step4).getByText(/Draft 1/i)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not show a multi-hour elapsed value for a brand-new run with a tz-less created_at", async () => {
    // Regression for the `3h 0m elapsed` bug. Backend timestamps from
    // SQLite arrive without a `Z` suffix; the page must treat them as
    // UTC and read elapsed time in seconds.
    const justCreatedRun = {
      id: "run-new",
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      run_dir: "runs/run-new",
      status: "running",
      prompt_hash: null,
      input_hash: null,
      output_hash: null,
      // No `Z` — the SQLite-naive shape.
      created_at: "2026-05-22T13:00:00",
      started_at: "2026-05-22T13:00:01",
      completed_at: null,
      error_message: null,
    };
    listRunsMock.mockResolvedValue([justCreatedRun]);
    listResumeVersionsMock.mockResolvedValue([]);

    // Freeze "now" three seconds after start. In a TZ != UTC environment
    // the pre-fix code would have rendered hours of elapsed time.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-22T13:00:04Z"));
    try {
      renderJob("job-1");

      await act(async () => {
        for (let i = 0; i < 8; i += 1) await Promise.resolve();
      });

      const generateStep = screen.getByRole("region", {
        name: /step 3: generate a draft/i,
      });
      // Within 5s of start → "just now". Definitely NOT `3h` or any hours value.
      expect(within(generateStep).getByText(/just now/i)).toBeInTheDocument();
      expect(within(generateStep).queryByText(/\d+h/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
