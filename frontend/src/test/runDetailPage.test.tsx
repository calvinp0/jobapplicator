import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

describe("RunDetailPage actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getJobMock.mockResolvedValue(job);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("invokes a created run and reflects the updated status", async () => {
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
    // Pending badge renders for status="created".
    expect(screen.getByText("Pending")).toHaveClass("status-badge-pending");

    const invokeBtn = screen.getByRole("button", { name: /^invoke$/i });
    expect(invokeBtn).toBeEnabled();

    await user.click(invokeBtn);

    await waitFor(() =>
      expect(invokeRunMock).toHaveBeenCalledWith("run-1"),
    );

    await waitFor(() => {
      const statusDt = screen.getByText(/^Status$/);
      expect(statusDt.nextElementSibling).toHaveTextContent("running");
    });

    expect(
      screen.getByRole("button", { name: /^invoke$/i }),
    ).toBeDisabled();
  });

  it("imports outputs on a completed run and surfaces the new resume version", async () => {
    const user = userEvent.setup();
    getRunMock
      .mockResolvedValueOnce({ ...completedRun })
      .mockResolvedValueOnce({ ...importedRun });
    listResumeVersionsMock.mockResolvedValue([]);
    importRunMock.mockResolvedValue(resumeVersion);

    renderRunDetail("run-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /resume tailoring run/i,
        }),
      ).toBeInTheDocument(),
    );

    const importBtn = screen.getByRole("button", {
      name: /import outputs/i,
    });
    expect(importBtn).toBeEnabled();

    await user.click(importBtn);

    await waitFor(() =>
      expect(importRunMock).toHaveBeenCalledWith("run-1"),
    );

    await waitFor(() =>
      expect(screen.getByText(/Resume version:/i)).toBeInTheDocument(),
    );
    const versionLink = screen.getByRole("link", { name: "version-1" });
    expect(versionLink).toHaveAttribute(
      "href",
      "/resume-versions/version-1",
    );
  });

  it("does not call importRun when the run is not completed", async () => {
    const user = userEvent.setup();
    getRunMock.mockResolvedValue({ ...baseRun });
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

    const importBtn = screen.getByRole("button", {
      name: /import outputs/i,
    });
    expect(importBtn).toBeDisabled();

    await user.click(importBtn);

    expect(importRunMock).not.toHaveBeenCalled();
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
    const user = userEvent.setup();
    getRunMock.mockResolvedValue({ ...completedRun });
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

    // Summary fields are visible outside the disclosure. "Completed"
    // appears both as a dt label and as the status badge label, so
    // scope to the DT element.
    expect(screen.getByText(/^Status$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Created$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Started$/).closest("details")).toBeNull();
    const completedDt = screen
      .getAllByText(/^Completed$/)
      .find((el) => el.tagName === "DT");
    expect(completedDt).toBeDefined();
    expect(completedDt!.closest("details")).toBeNull();

    // The disclosure renders with the heading "Advanced details", closed by default.
    const disclosure = screen.getByText(/^Advanced details$/);
    const detailsEl = disclosure.closest("details");
    expect(detailsEl).not.toBeNull();
    expect(detailsEl).toHaveClass("advanced-details");
    expect(detailsEl).not.toHaveAttribute("open");

    // Provenance fields live inside the disclosure.
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

    // Expanding the disclosure surfaces the provenance fields to the user.
    await user.click(disclosure);
    expect(detailsEl).toHaveAttribute("open");
  });
});
