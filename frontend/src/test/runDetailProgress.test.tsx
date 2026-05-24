import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getRunMock,
  invokeRunMock,
  importRunMock,
  listResumeVersionsMock,
  getJobMock,
  getRunLogMock,
  getRunProgressMock,
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
    getRunMock: vi.fn(),
    invokeRunMock: vi.fn(),
    importRunMock: vi.fn(),
    listResumeVersionsMock: vi.fn(),
    getJobMock: vi.fn(),
    getRunLogMock: vi.fn(),
    getRunProgressMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getRun: getRunMock,
  invokeRun: invokeRunMock,
  importRun: importRunMock,
  listResumeVersions: listResumeVersionsMock,
  getJob: getJobMock,
  getRunLog: getRunLogMock,
  getRunProgress: getRunProgressMock,
  ApiError: ApiErrorMock,
}));

import {
  RunDetailPage,
  RUN_PROGRESS_POLL_INTERVAL_MS,
} from "../pages/RunDetailPage";

function renderRunDetail(runId: string) {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}`]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const baseRun = {
  id: "run-1",
  job_id: "job-1",
  master_resume_id: "resume-1",
  evidence_bank_id: null,
  run_dir: "runs/run-1",
  status: "running",
  prompt_hash: "p",
  input_hash: "i",
  output_hash: null,
  created_at: "2026-05-22T12:00:00Z",
  started_at: "2026-05-22T12:01:00Z",
  completed_at: null,
  error_message: null,
};

const failedMissingOutputs = {
  ...baseRun,
  status: "failed",
  completed_at: "2026-05-22T12:02:00Z",
  error_message:
    "expected output file missing: output/tailored_resume.docx",
};

const job = {
  id: "job-1",
  source_platform: "linkedin",
  external_url: null,
  external_job_id: null,
  company: "Acme",
  title: "Senior Engineer",
  location: null,
  description_text: "",
  application_method: null,
  created_from_capture_id: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

describe("RunDetailPage progress-events panel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getJobMock.mockResolvedValue(job);
    listResumeVersionsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("prefers user-facing progress lines over the raw run.log in the default activity panel", async () => {
    // Both feeds have content; the panel must render the progress lines.
    getRunMock.mockResolvedValue({ ...baseRun });
    getRunProgressMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "Reading job description",
        "Reviewing master resume",
        "Drafting tailored resume markdown",
      ],
      truncated: false,
    });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "jobapply: launching Claude Code with cwd=/tmp/run",
        "jobapply: permission mode=acceptEdits",
        "jobapply: output directory=/tmp/run/output",
      ],
      truncated: false,
    });

    renderRunDetail("run-1");

    expect(
      await screen.findByText(/Reading job description/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Drafting tailored resume markdown/),
    ).toBeInTheDocument();

    // The default activity panel must NOT surface the technical jobapply:
    // milestones when user-facing progress is available.
    const recentActivityLabel = screen.getByText(/Recent activity/);
    const activityPanel = recentActivityLabel.closest("div");
    expect(activityPanel).not.toBeNull();
    expect(
      within(activityPanel as HTMLElement).queryByText(
        /launching Claude Code/,
      ),
    ).not.toBeInTheDocument();
    expect(
      within(activityPanel as HTMLElement).queryByText(
        /permission mode=acceptEdits/,
      ),
    ).not.toBeInTheDocument();
  });

  it("falls back to the run.log feed when there are no user-facing progress lines yet", async () => {
    getRunMock.mockResolvedValue({ ...baseRun });
    getRunProgressMock.mockResolvedValue({
      run_id: "run-1",
      lines: [],
      truncated: false,
    });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "jobapply: preparing tailoring inputs",
        "jobapply: launching Claude Code",
      ],
      truncated: false,
    });

    renderRunDetail("run-1");

    // Worker milestones (jobapply: prefix stripped by sanitizer) render as
    // a fallback so the panel is never empty just because Claude hasn't
    // produced a progress line yet.
    await waitFor(() =>
      expect(
        screen.getByText(/preparing tailoring inputs/),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/launching Claude Code/)).toBeInTheDocument();
  });

  it("keeps the final progress lines visible above the failure error message", async () => {
    getRunMock.mockResolvedValue({ ...failedMissingOutputs });
    getRunProgressMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "Reading job description",
        "Reviewing master resume",
        "Drafting tailored resume markdown",
        "Validating required outputs",
      ],
      truncated: false,
    });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: ["jobapply: marking run failed"],
      truncated: false,
    });

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByText(/Validating required outputs/),
      ).toBeInTheDocument(),
    );
    // The user-facing failure error message is still present.
    expect(
      screen.getByText(
        /expected output file missing: output\/tailored_resume\.docx/,
      ),
    ).toBeInTheDocument();
    // And the four progress phases are still rendered above it.
    expect(screen.getByText(/Reading job description/)).toBeInTheDocument();
    expect(screen.getByText(/Reviewing master resume/)).toBeInTheDocument();
    expect(
      screen.getByText(/Drafting tailored resume markdown/),
    ).toBeInTheDocument();
  });

  it("polls getRunProgress repeatedly while the run is still active", async () => {
    vi.useFakeTimers();
    try {
      getRunMock.mockResolvedValue({ ...baseRun });
      getRunProgressMock.mockResolvedValue({
        run_id: "run-1",
        lines: ["Reading job description"],
        truncated: false,
      });
      getRunLogMock.mockResolvedValue({
        run_id: "run-1",
        lines: [],
        truncated: false,
      });

      renderRunDetail("run-1");
      await act(async () => {
        for (let i = 0; i < 6; i += 1) await Promise.resolve();
      });
      const initialCallCount = getRunProgressMock.mock.calls.length;
      expect(initialCallCount).toBeGreaterThanOrEqual(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(RUN_PROGRESS_POLL_INTERVAL_MS);
      });
      expect(getRunProgressMock.mock.calls.length).toBeGreaterThan(
        initialCallCount,
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops polling getRunProgress once the run reaches a terminal state", async () => {
    vi.useFakeTimers();
    try {
      getRunMock.mockResolvedValue({ ...failedMissingOutputs });
      getRunProgressMock.mockResolvedValue({
        run_id: "run-1",
        lines: ["Validating required outputs"],
        truncated: false,
      });
      getRunLogMock.mockResolvedValue({
        run_id: "run-1",
        lines: [],
        truncated: false,
      });

      renderRunDetail("run-1");

      await act(async () => {
        for (let i = 0; i < 6; i += 1) await Promise.resolve();
      });

      const initialCallCount = getRunProgressMock.mock.calls.length;
      expect(initialCallCount).toBeGreaterThanOrEqual(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(
          RUN_PROGRESS_POLL_INTERVAL_MS * 5,
        );
      });
      expect(getRunProgressMock.mock.calls.length).toBe(initialCallCount);
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders the full technical run.log inside Advanced details so debugging info isn't lost", async () => {
    getRunMock.mockResolvedValue({ ...failedMissingOutputs });
    getRunProgressMock.mockResolvedValue({
      run_id: "run-1",
      lines: ["Reading job description"],
      truncated: false,
    });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "jobapply: launching Claude Code with cwd=/tmp/run",
        "jobapply: permission mode=acceptEdits",
        "jobapply: marking run failed",
      ],
      truncated: false,
    });

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByText(/Reading job description/),
      ).toBeInTheDocument(),
    );

    const detailsEl = screen
      .getByText(/^Advanced details$/)
      .closest("details");
    expect(detailsEl).not.toBeNull();
    expect(
      within(detailsEl as HTMLElement).getByText(/Technical run log/i),
    ).toBeInTheDocument();
    expect(
      within(detailsEl as HTMLElement).getByText(
        /launching Claude Code with cwd=/,
      ),
    ).toBeInTheDocument();
    expect(
      within(detailsEl as HTMLElement).getByText(/permission mode=acceptEdits/),
    ).toBeInTheDocument();
  });
});
