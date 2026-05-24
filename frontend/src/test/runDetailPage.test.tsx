import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  ApiError: ApiErrorMock,
}));

import { RunDetailPage } from "../pages/RunDetailPage";

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
  status: "created",
  prompt_hash: "promptpromptprompt",
  input_hash: "inputinputinput",
  output_hash: null,
  created_at: "2026-05-22T12:00:00Z",
  started_at: null,
  completed_at: null,
  error_message: null,
};

const completedRun = {
  ...baseRun,
  status: "completed",
  output_hash: "outputoutputoutput",
  started_at: "2026-05-22T12:01:00Z",
  completed_at: "2026-05-22T12:05:00Z",
};

const importedRun = {
  ...completedRun,
  status: "imported",
};

const failedRun = {
  ...baseRun,
  status: "failed",
  started_at: "2026-05-22T12:01:00Z",
  completed_at: "2026-05-22T12:02:00Z",
  error_message: "model error",
};

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

describe("RunDetailPage default UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getJobMock.mockResolvedValue(job);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("does not surface operator verbs `Invoke` or `Import outputs` in the default UI", async () => {
    // `failed` is a terminal state — no polling, no auto-import — so the
    // page is stable and we can assert the static structure of the UI.
    getRunMock.mockResolvedValue({ ...failedRun });
    listResumeVersionsMock.mockResolvedValue([]);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /resume tailoring run/i,
        }),
      ).toBeInTheDocument(),
    );

    expect(screen.queryByText(/^Invoke$/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^invoke$/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/import outputs/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /import outputs/i }),
    ).not.toBeInTheDocument();
  });

  it("renders the run status using runStatusLabel, not the raw enum", async () => {
    getRunMock.mockResolvedValue({ ...failedRun });
    listResumeVersionsMock.mockResolvedValue([]);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /resume tailoring run/i,
        }),
      ).toBeInTheDocument(),
    );

    const statusDt = screen.getByText(/^Status$/);
    expect(statusDt.nextElementSibling).toHaveTextContent(
      /Tailoring failed/i,
    );
    // The raw enum should not appear in the default Status field.
    expect(statusDt.nextElementSibling).not.toHaveTextContent(/^failed$/);
  });

  it("moves operator controls into Advanced details with the renamed labels", async () => {
    const user = userEvent.setup();
    getRunMock.mockResolvedValue({ ...failedRun });
    listResumeVersionsMock.mockResolvedValue([]);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /resume tailoring run/i,
        }),
      ).toBeInTheDocument(),
    );

    const disclosure = screen.getByText(/^Advanced details$/);
    const detailsEl = disclosure.closest("details");
    expect(detailsEl).not.toBeNull();
    expect(detailsEl).toHaveClass("advanced-details");
    expect(detailsEl).not.toHaveAttribute("open");

    // The renamed operator controls live inside the disclosure.
    const startBtn = within(detailsEl as HTMLElement).getByRole("button", {
      name: /start tailoring/i,
    });
    const retryBtn = within(detailsEl as HTMLElement).getByRole("button", {
      name: /retry import/i,
    });
    expect(startBtn).toBeInTheDocument();
    expect(retryBtn).toBeInTheDocument();

    // The raw status enum also lives inside Advanced details.
    expect(screen.getByText(/^Raw status$/).closest("details")).toBe(
      detailsEl,
    );

    // Expanding the disclosure surfaces the controls.
    await user.click(disclosure);
    expect(detailsEl).toHaveAttribute("open");
  });

  it("starts tailoring from the Advanced controls when status is created", async () => {
    const user = userEvent.setup();
    getRunMock.mockResolvedValueOnce({ ...baseRun });
    listResumeVersionsMock.mockResolvedValue([]);
    invokeRunMock.mockResolvedValue({ ...baseRun, status: "running" });

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /resume tailoring run/i,
        }),
      ).toBeInTheDocument(),
    );

    const startBtn = screen.getByRole("button", {
      name: /start tailoring/i,
    });
    expect(startBtn).toBeEnabled();

    await user.click(startBtn);

    await waitFor(() => expect(invokeRunMock).toHaveBeenCalledWith("run-1"));

    await waitFor(() => {
      const statusDt = screen.getByText(/^Status$/);
      expect(statusDt.nextElementSibling).toHaveTextContent(
        /Tailoring in progress/i,
      );
    });
  });

  it("renders import failures via extractApiDetail rather than the raw request/status string", async () => {
    // The auto-import effect fires on a completed run with no version yet.
    // The failing importRun should be parsed into the backend's `detail`.
    getRunMock.mockResolvedValueOnce({ ...completedRun });
    listResumeVersionsMock.mockResolvedValue([]);
    const apiError = new ApiErrorMock(
      "Request to /runs/run-1/import failed with status 400",
      400,
      { detail: "DOCX file is missing from the run directory" },
    );
    importRunMock.mockRejectedValue(apiError);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(importRunMock).toHaveBeenCalledWith("run-1"),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      /DOCX file is missing from the run directory/i,
    );
    expect(alert).not.toHaveTextContent(/Request to \/runs/i);
    expect(alert).not.toHaveTextContent(/status 400/i);
  });

  it("surfaces an existing resume version when the run is already imported", async () => {
    getRunMock.mockResolvedValue({ ...importedRun });
    listResumeVersionsMock.mockResolvedValue([resumeVersion]);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(screen.getByText(/Resume version:/i)).toBeInTheDocument(),
    );
    expect(importRunMock).not.toHaveBeenCalled();
    const versionLink = screen.getByRole("link", { name: "version-1" });
    expect(versionLink).toHaveAttribute(
      "href",
      "/resume-versions/version-1",
    );
  });

  it("renders summary fields by default and hides provenance behind Advanced details", async () => {
    getRunMock.mockResolvedValue({ ...failedRun });
    listResumeVersionsMock.mockResolvedValue([]);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /resume tailoring run/i,
        }),
      ).toBeInTheDocument(),
    );

    // Summary fields are visible outside the disclosure.
    expect(screen.getByText(/^Status$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Created$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Started$/).closest("details")).toBeNull();
    const completedDt = screen
      .getAllByText(/^Completed$/)
      .find((el) => el.tagName === "DT");
    expect(completedDt).toBeDefined();
    expect(completedDt!.closest("details")).toBeNull();

    // Provenance fields live inside the Advanced details disclosure.
    const detailsEl = screen
      .getByText(/^Advanced details$/)
      .closest("details");
    expect(detailsEl).not.toBeNull();
    expect(screen.getByText(/^Run id$/).closest("details")).toBe(detailsEl);
    expect(screen.getByText(/^Run directory$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText("runs/run-1").closest("details")).toBe(detailsEl);
    expect(screen.getByText(/^Prompt hash$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText(/^Input hash$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText(/^Output hash$/).closest("details")).toBe(
      detailsEl,
    );
  });
});
