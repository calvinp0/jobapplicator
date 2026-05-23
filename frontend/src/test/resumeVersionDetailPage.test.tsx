import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getResumeVersionMock,
  approveResumeVersionMock,
  openResumeVersionFileMock,
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
    getResumeVersionMock: vi.fn(),
    approveResumeVersionMock: vi.fn(),
    openResumeVersionFileMock: vi.fn(),
    getJobMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getResumeVersion: getResumeVersionMock,
  approveResumeVersion: approveResumeVersionMock,
  openResumeVersionFile: openResumeVersionFileMock,
  getJob: getJobMock,
  ApiError: ApiErrorMock,
}));

import { ResumeVersionDetailPage } from "../pages/ResumeVersionDetailPage";

function renderVersion(versionId: string) {
  return render(
    <MemoryRouter initialEntries={[`/resume-versions/${versionId}`]}>
      <Routes>
        <Route
          path="/resume-versions/:versionId"
          element={<ResumeVersionDetailPage />}
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
  description_text: "",
  application_method: null,
  created_from_capture_id: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const pendingVersion = {
  id: "version-1",
  job_id: "job-1",
  master_resume_id: "resume-1",
  claude_run_id: "run-1",
  version_number: 2,
  content_markdown: "# Resume markdown",
  docx_path: "runs/run-1/output/resume.docx",
  pdf_path: null,
  content_hash: "abcdef1234567890",
  prompt_hash: "1111111122222222",
  source: "claude_run",
  approved_at: null,
  created_at: "2026-05-22T12:06:00Z",
};

const approvedVersion = {
  ...pendingVersion,
  approved_at: "2026-05-22T13:00:00Z",
};

const versionWithoutDocx = {
  ...pendingVersion,
  docx_path: null,
};

describe("ResumeVersionDetailPage", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders metadata for the resume version", async () => {
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /resume version 2/i }),
      ).toBeInTheDocument(),
    );

    expect(getResumeVersionMock).toHaveBeenCalledWith("version-1");
    expect(screen.getByText("claude_run")).toBeInTheDocument();
    expect(screen.getByText("Not approved")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /senior engineer — acme corp/i }),
    ).toHaveAttribute("href", "/jobs/job-1");

    // DOCX path lives behind the Advanced details disclosure.
    const docxPath = screen.getByText("runs/run-1/output/resume.docx");
    expect(docxPath.closest("details")).toHaveClass("advanced-details");
  });

  it("renders summary fields by default and hides provenance behind Advanced details", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /resume version 2/i }),
      ).toBeInTheDocument(),
    );

    // Summary fields live outside the disclosure.
    expect(screen.getByText(/^Version$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Job$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Source$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Created$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Approved$/).closest("details")).toBeNull();

    // The disclosure renders with the heading "Advanced details", closed by default.
    const disclosure = screen.getByText(/^Advanced details$/);
    const detailsEl = disclosure.closest("details");
    expect(detailsEl).not.toBeNull();
    expect(detailsEl).toHaveClass("advanced-details");
    expect(detailsEl).not.toHaveAttribute("open");

    // Provenance fields live inside the disclosure.
    expect(screen.getByText(/^Resume version id$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText(/^Claude run id$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText(/^Content hash$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText(/^Prompt hash$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText(/^DOCX path$/).closest("details")).toBe(detailsEl);
    expect(screen.getByText(/^PDF path$/).closest("details")).toBe(detailsEl);

    // Expanding the disclosure surfaces the provenance fields to the user.
    await user.click(disclosure);
    expect(detailsEl).toHaveAttribute("open");
  });

  it("approves a pending version and reflects the approved state", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    approveResumeVersionMock.mockResolvedValue({ ...approvedVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /resume version 2/i }),
      ).toBeInTheDocument(),
    );

    const approveBtn = screen.getByRole("button", { name: /^approve$/i });
    expect(approveBtn).toBeEnabled();

    await user.click(approveBtn);

    await waitFor(() =>
      expect(approveResumeVersionMock).toHaveBeenCalledWith("version-1"),
    );

    await waitFor(() =>
      expect(screen.getByText(/Approved on /i)).toBeInTheDocument(),
    );

    expect(
      screen.getByRole("button", { name: /^approve$/i }),
    ).toBeDisabled();
  });

  it("disables Approve when the version is already approved", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...approvedVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(screen.getByText(/Approved on /i)).toBeInTheDocument(),
    );

    const approveBtn = screen.getByRole("button", { name: /^approve$/i });
    expect(approveBtn).toBeDisabled();

    await user.click(approveBtn);

    expect(approveResumeVersionMock).not.toHaveBeenCalled();
  });

  it("opens the DOCX exactly once when the button is clicked", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    openResumeVersionFileMock.mockResolvedValue(undefined);

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /resume version 2/i }),
      ).toBeInTheDocument(),
    );

    const openBtn = screen.getByRole("button", { name: /open docx/i });
    expect(openBtn).toBeEnabled();

    await user.click(openBtn);

    await waitFor(() =>
      expect(openResumeVersionFileMock).toHaveBeenCalledWith("version-1"),
    );
    expect(openResumeVersionFileMock).toHaveBeenCalledTimes(1);
  });

  it("disables Open DOCX when docx_path is null", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...versionWithoutDocx });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /resume version 2/i }),
      ).toBeInTheDocument(),
    );

    const openBtn = screen.getByRole("button", { name: /open docx/i });
    expect(openBtn).toBeDisabled();

    await user.click(openBtn);

    expect(openResumeVersionFileMock).not.toHaveBeenCalled();
  });
});
