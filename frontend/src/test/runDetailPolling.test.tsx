import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getRunMock,
  invokeRunMock,
  importRunMock,
  listResumeVersionsMock,
  getJobMock,
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
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getRun: getRunMock,
  invokeRun: invokeRunMock,
  importRun: importRunMock,
  listResumeVersions: listResumeVersionsMock,
  getJob: getJobMock,
  getRunLog: vi.fn(() =>
    Promise.resolve({ run_id: "stub", lines: [], truncated: false }),
  ),
  getRunProgress: vi.fn(() =>
    Promise.resolve({ run_id: "stub", lines: [], truncated: false }),
  ),
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

import { RunDetailPage, RUN_POLL_INTERVAL_MS } from "../pages/RunDetailPage";

function renderRunDetail(runId: string) {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}`]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetailPage />} />
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
  description_text: "",
  application_method: null,
  created_from_capture_id: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const runningRun = {
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

const completedRun = {
  ...runningRun,
  status: "completed",
  output_hash: "o",
  completed_at: "2026-05-22T12:05:00Z",
};

const importedRun = {
  ...completedRun,
  status: "imported",
};

const failedRun = {
  ...runningRun,
  status: "failed",
  completed_at: "2026-05-22T12:02:00Z",
  error_message: "model error",
};

const resumeVersion = {
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
  created_at: "2026-05-22T12:06:00Z",
};

async function flushMicrotasks() {
  // Resolve any chains of awaited promises. `act` keeps React state
  // updates batched and avoids "not wrapped in act" warnings.
  await act(async () => {
    for (let i = 0; i < 6; i += 1) {
      await Promise.resolve();
    }
  });
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("RunDetailPage polling and auto-import", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    getJobMock.mockResolvedValue(job);
    listResumeVersionsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("polls getRun every 5 seconds while the run is active", async () => {
    getRunMock
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...runningRun });

    renderRunDetail("run-1");

    await flushMicrotasks();
    expect(getRunMock).toHaveBeenCalledTimes(1);

    await advance(RUN_POLL_INTERVAL_MS);
    expect(getRunMock).toHaveBeenCalledTimes(2);

    await advance(RUN_POLL_INTERVAL_MS);
    expect(getRunMock).toHaveBeenCalledTimes(3);
  });

  it("stops polling once the run reaches the terminal `imported` state", async () => {
    // Sequence: initial running → poll observes completed → auto-import
    // refreshes to imported. After that, no further getRun calls.
    getRunMock
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...completedRun })
      .mockResolvedValueOnce({ ...importedRun });
    importRunMock.mockResolvedValue(resumeVersion);

    renderRunDetail("run-1");
    await flushMicrotasks();
    expect(getRunMock).toHaveBeenCalledTimes(1);

    await advance(RUN_POLL_INTERVAL_MS);
    await flushMicrotasks();

    expect(importRunMock).toHaveBeenCalledTimes(1);
    // Two getRun (initial + poll) + one from auto-import's refresh after success.
    expect(getRunMock).toHaveBeenCalledTimes(3);

    // Now run is imported. Advancing timers further must not fire getRun again.
    await advance(RUN_POLL_INTERVAL_MS * 3);
    expect(getRunMock).toHaveBeenCalledTimes(3);
  });

  it("stops polling once the run reaches the terminal `failed` state", async () => {
    getRunMock
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...failedRun });

    renderRunDetail("run-1");
    await flushMicrotasks();
    expect(getRunMock).toHaveBeenCalledTimes(1);

    await advance(RUN_POLL_INTERVAL_MS);
    expect(getRunMock).toHaveBeenCalledTimes(2);

    // No further getRun once we observe `failed`.
    await advance(RUN_POLL_INTERVAL_MS * 3);
    expect(getRunMock).toHaveBeenCalledTimes(2);
    expect(importRunMock).not.toHaveBeenCalled();
  });

  it("auto-imports exactly once on transition into `completed`", async () => {
    getRunMock
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...completedRun })
      .mockResolvedValueOnce({ ...importedRun });
    importRunMock.mockResolvedValue(resumeVersion);

    renderRunDetail("run-1");
    await flushMicrotasks();

    await advance(RUN_POLL_INTERVAL_MS);
    await flushMicrotasks();
    expect(importRunMock).toHaveBeenCalledTimes(1);

    // Advance more — no second import call.
    await advance(RUN_POLL_INTERVAL_MS * 5);
    expect(importRunMock).toHaveBeenCalledTimes(1);

    // The imported resume version link is rendered.
    expect(screen.getByText(/Resume version:/i)).toBeInTheDocument();
  });

  it("does not leak intervals after unmount", async () => {
    getRunMock.mockResolvedValue({ ...runningRun });

    const { unmount } = renderRunDetail("run-1");
    await flushMicrotasks();
    expect(getRunMock).toHaveBeenCalledTimes(1);

    unmount();

    await advance(RUN_POLL_INTERVAL_MS * 5);
    // No further calls after unmount.
    expect(getRunMock).toHaveBeenCalledTimes(1);
  });

  it("calls importRun at most once even when subsequent polls keep returning `completed` after a failure", async () => {
    // This is the regression test for the spam bug:
    //   POST /runs/{id}/import → 400
    //   POST /runs/{id}/import → 400  (every poll)
    //
    // The auto-import effect must fire exactly once per run and stay
    // off after a failure — only an explicit retry should fire it again.
    getRunMock
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...completedRun })
      .mockResolvedValue({ ...completedRun });
    const apiError = new ApiErrorMock(
      "Request to /runs/run-1/import failed with status 400",
      400,
      { detail: "expected output file missing: output/tailored_resume.docx" },
    );
    importRunMock.mockRejectedValue(apiError);

    renderRunDetail("run-1");
    await flushMicrotasks();
    expect(getRunMock).toHaveBeenCalledTimes(1);

    // First poll observes `completed` and fires auto-import once.
    await advance(RUN_POLL_INTERVAL_MS);
    await flushMicrotasks();
    expect(importRunMock).toHaveBeenCalledTimes(1);

    // Subsequent polls keep observing `completed`. importRun must NOT be
    // re-fired — that's the bug this guards against.
    await advance(RUN_POLL_INTERVAL_MS * 5);
    await flushMicrotasks();
    expect(importRunMock).toHaveBeenCalledTimes(1);
  });

  it("retries import only when the user clicks `Retry loading draft`", async () => {
    getRunMock
      .mockResolvedValueOnce({ ...runningRun })
      .mockResolvedValueOnce({ ...completedRun })
      .mockResolvedValue({ ...completedRun });
    const apiError = new ApiErrorMock(
      "Request to /runs/run-1/import failed with status 400",
      400,
      { detail: "expected output file missing: output/tailored_resume.docx" },
    );
    // First import call fails, second succeeds after the user retries.
    importRunMock.mockRejectedValueOnce(apiError);
    importRunMock.mockResolvedValueOnce(resumeVersion);

    renderRunDetail("run-1");
    await flushMicrotasks();
    await advance(RUN_POLL_INTERVAL_MS);
    await flushMicrotasks();

    expect(importRunMock).toHaveBeenCalledTimes(1);

    // Use real timers briefly so userEvent can resolve its delays.
    vi.useRealTimers();
    try {
      const userEvent = (
        await import("@testing-library/user-event")
      ).default;
      const user = userEvent.setup();
      const retryBtn = await screen.findByRole("button", {
        name: /retry loading draft/i,
      });
      await user.click(retryBtn);
    } finally {
      vi.useFakeTimers();
    }

    await flushMicrotasks();
    expect(importRunMock).toHaveBeenCalledTimes(2);
  });
});
