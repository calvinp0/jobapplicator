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

  it("renders metadata for the resume draft", async () => {
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^draft 2/i }),
      ).toBeInTheDocument(),
    );

    expect(getResumeVersionMock).toHaveBeenCalledWith("version-1");
    expect(screen.getByText("claude_run")).toBeInTheDocument();
    expect(screen.getByText("Not approved")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /senior engineer — acme corp/i }),
    ).toHaveAttribute("href", "/jobs/job-1");

    // Awaiting review badge renders while approved_at is null.
    expect(screen.getByText("Awaiting review")).toHaveClass(
      "status-badge-draft",
    );

    // Once the job loads, the heading includes "Senior Engineer — Acme Corp".
    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          level: 2,
          name: /^draft 2 for senior engineer — acme corp/i,
        }),
      ).toBeInTheDocument(),
    );

    // No "Version N" copy leaks into the user-facing surface.
    expect(screen.queryByText(/^Version 2$/)).toBeNull();
    expect(screen.queryByText(/^Version$/)).toBeNull();

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
        screen.getByRole("heading", { level: 2, name: /^draft 2/i }),
      ).toBeInTheDocument(),
    );

    // Summary fields live outside the disclosure.
    expect(screen.getByText(/^Draft$/).closest("details")).toBeNull();
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

  it("approves a pending draft and swaps the button for an Approved indicator", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    approveResumeVersionMock.mockResolvedValue({ ...approvedVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^draft 2/i }),
      ).toBeInTheDocument(),
    );

    const approveBtn = screen.getByRole("button", { name: /^approve draft$/i });
    expect(approveBtn).toBeEnabled();

    await user.click(approveBtn);

    await waitFor(() =>
      expect(approveResumeVersionMock).toHaveBeenCalledWith("version-1"),
    );

    await waitFor(() =>
      expect(screen.getByText(/Approved on /i)).toBeInTheDocument(),
    );

    // Badge flips to Approved.
    const approvedBadge = screen
      .getAllByText("Approved")
      .find((el) => el.classList.contains("status-badge"));
    expect(approvedBadge).toBeDefined();
    expect(approvedBadge).toHaveClass("status-badge-approved");

    // The active Approve button is replaced by a read-only indicator.
    expect(
      screen.queryByRole("button", { name: /approve draft/i }),
    ).toBeNull();
    expect(screen.getByText(/Approved ✓/)).toBeInTheDocument();
  });

  it("shows the Approved indicator and no Approve button when already approved", async () => {
    getResumeVersionMock.mockResolvedValue({ ...approvedVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(screen.getByText(/Approved on /i)).toBeInTheDocument(),
    );

    expect(
      screen.queryByRole("button", { name: /approve draft/i }),
    ).toBeNull();
    expect(screen.getByText(/Approved ✓/)).toBeInTheDocument();
  });

  it("renders a parsed detail message when approving fails", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    approveResumeVersionMock.mockRejectedValue(
      new ApiErrorMock("Request to /resume-versions/version-1/approve failed with status 409", 409, {
        detail: "Cannot approve a draft that was already approved.",
      }),
    );

    renderVersion("version-1");

    const approveBtn = await screen.findByRole("button", {
      name: /^approve draft$/i,
    });

    await user.click(approveBtn);

    await waitFor(() =>
      expect(
        screen.getByText(/cannot approve a draft that was already approved/i),
      ).toBeInTheDocument(),
    );
    // The raw "Request to /..." string never reaches the user.
    expect(screen.queryByText(/Request to \//i)).toBeNull();
  });

  it("renders a parsed detail message when opening the DOCX fails", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    openResumeVersionFileMock.mockRejectedValue(
      new ApiErrorMock("Request to /resume-versions/version-1/open failed with status 500", 500, {
        detail: "Could not open the draft file on this machine.",
      }),
    );

    renderVersion("version-1");

    const openBtn = await screen.findByRole("button", {
      name: /open draft file/i,
    });

    await user.click(openBtn);

    await waitFor(() =>
      expect(
        screen.getByText(/could not open the draft file on this machine/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Request to \//i)).toBeNull();
  });

  it("opens the DOCX exactly once when the button is clicked", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    openResumeVersionFileMock.mockResolvedValue(undefined);

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^draft 2/i }),
      ).toBeInTheDocument(),
    );

    const openBtn = screen.getByRole("button", { name: /open draft file/i });
    expect(openBtn).toBeEnabled();

    await user.click(openBtn);

    await waitFor(() =>
      expect(openResumeVersionFileMock).toHaveBeenCalledWith("version-1"),
    );
    expect(openResumeVersionFileMock).toHaveBeenCalledTimes(1);
  });

  it("disables Open draft file when docx_path is null", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...versionWithoutDocx });

    renderVersion("version-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^draft 2/i }),
      ).toBeInTheDocument(),
    );

    const openBtn = screen.getByRole("button", { name: /open draft file/i });
    expect(openBtn).toBeDisabled();

    await user.click(openBtn);

    expect(openResumeVersionFileMock).not.toHaveBeenCalled();
  });
});
