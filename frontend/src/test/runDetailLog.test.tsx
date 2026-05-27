import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
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
  getRunRecruiterReview: vi.fn(() =>
    Promise.resolve({
      run_id: "stub",
      available: false,
      content: null,
      path: null,
    }),
  ),
  ApiError: ApiErrorMock,
}));

import {
  RunDetailPage,
  RUN_LOG_POLL_INTERVAL_MS,
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

const failedMissingOutputs = {
  ...baseRun,
  status: "failed",
  completed_at: "2026-05-22T12:02:00Z",
  error_message:
    "expected output file missing: output/tailored_resume.docx, output/change_log.md",
};

describe("RunDetailPage recent-activity panel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getJobMock.mockResolvedValue(job);
    listResumeVersionsMock.mockResolvedValue([]);
    // Default: progress feed is empty so the existing tests exercise the
    // run.log fallback path. Per-test overrides can install real progress
    // lines via getRunProgressMock.mockResolvedValue(...).
    getRunProgressMock.mockResolvedValue({
      run_id: "run-1",
      lines: [],
      truncated: false,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the 'Waiting for the tailoring agent to start…' empty state when the log has no lines yet", async () => {
    getRunMock.mockResolvedValue({ ...baseRun });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: [],
      truncated: false,
    });

    renderRunDetail("run-1");

    expect(
      await screen.findByText(/Waiting for the tailoring agent to start/i),
    ).toBeInTheDocument();
  });

  it("renders worker milestones with the jobapply: prefix stripped", async () => {
    getRunMock.mockResolvedValue({ ...baseRun });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "jobapply: preparing tailoring inputs",
        "jobapply: launching Claude Code",
        "jobapply: Claude Code process started",
      ],
      truncated: false,
    });

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByText(/preparing tailoring inputs/),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/launching Claude Code/)).toBeInTheDocument();
    expect(
      screen.getByText(/Claude Code process started/),
    ).toBeInTheDocument();
    // The prefix is hidden so the bullet list reads cleanly.
    expect(
      screen.queryByText(/^jobapply:/),
    ).not.toBeInTheDocument();
  });

  it("shows the missing-outputs explanation and the final activity lines for a failed run", async () => {
    getRunMock.mockResolvedValue({ ...failedMissingOutputs });
    getRunLogMock.mockResolvedValue({
      run_id: "run-1",
      lines: [
        "jobapply: Claude Code process exited with code 0",
        "jobapply: validating output files",
        "jobapply: missing expected output file: output/tailored_resume.docx",
        "jobapply: marking run failed",
      ],
      truncated: false,
    });

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByText(
          /tailoring process finished without producing the required output files/i,
        ),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/Claude Code process exited with code 0/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/missing expected output file: output\/tailored_resume\.docx/),
    ).toBeInTheDocument();
    expect(screen.getByText(/marking run failed/)).toBeInTheDocument();
  });

  it("stops polling getRunLog once the run reaches a terminal state", async () => {
    vi.useFakeTimers();
    try {
      // failed is terminal — we should see exactly one log fetch (initial mount).
      getRunMock.mockResolvedValue({ ...failedMissingOutputs });
      getRunLogMock.mockResolvedValue({
        run_id: "run-1",
        lines: ["jobapply: marking run failed"],
        truncated: false,
      });

      renderRunDetail("run-1");

      await act(async () => {
        for (let i = 0; i < 6; i += 1) await Promise.resolve();
      });

      const initialCallCount = getRunLogMock.mock.calls.length;
      expect(initialCallCount).toBeGreaterThanOrEqual(1);

      // Advance well past several poll intervals. The hook must not tick again
      // because the run is in a terminal state.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(RUN_LOG_POLL_INTERVAL_MS * 5);
      });
      expect(getRunLogMock.mock.calls.length).toBe(initialCallCount);
    } finally {
      vi.useRealTimers();
    }
  });

  it("polls getRunLog repeatedly while the run is still active", async () => {
    vi.useFakeTimers();
    try {
      getRunMock.mockResolvedValue({ ...baseRun });
      getRunLogMock.mockResolvedValue({
        run_id: "run-1",
        lines: ["jobapply: preparing tailoring inputs"],
        truncated: false,
      });

      renderRunDetail("run-1");
      await act(async () => {
        for (let i = 0; i < 6; i += 1) await Promise.resolve();
      });
      const initialCallCount = getRunLogMock.mock.calls.length;
      expect(initialCallCount).toBeGreaterThanOrEqual(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(RUN_LOG_POLL_INTERVAL_MS);
      });
      expect(getRunLogMock.mock.calls.length).toBeGreaterThan(
        initialCallCount,
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
