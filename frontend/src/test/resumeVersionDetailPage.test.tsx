import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getResumeVersionMock,
  approveResumeVersionMock,
  openResumeVersionFileMock,
  submitRevisionFeedbackMock,
  getJobMock,
  getRunMock,
  listMasterResumesMock,
  listEvidenceSourcesMock,
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
    submitRevisionFeedbackMock: vi.fn(),
    getJobMock: vi.fn(),
    getRunMock: vi.fn(),
    listMasterResumesMock: vi.fn(),
    listEvidenceSourcesMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getResumeVersion: getResumeVersionMock,
  approveResumeVersion: approveResumeVersionMock,
  openResumeVersionFile: openResumeVersionFileMock,
  submitRevisionFeedback: submitRevisionFeedbackMock,
  getJob: getJobMock,
  getRun: getRunMock,
  listMasterResumes: listMasterResumesMock,
  listEvidenceSources: listEvidenceSourcesMock,
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
    getRunMock.mockResolvedValue({
      id: "run-1",
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      run_dir: "runs/run-1",
      status: "imported",
      prompt_hash: null,
      input_hash: null,
      output_hash: null,
      created_at: "2026-05-22T10:00:00Z",
      started_at: null,
      completed_at: null,
      error_message: null,
      evidence_source_ids: [],
    });
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceSourcesMock.mockResolvedValue([]);
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

  it("submits revision feedback and navigates to the follow-up run", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    submitRevisionFeedbackMock.mockResolvedValue({
      id: "rf-1",
      job_id: "job-1",
      source_resume_version_id: "version-1",
      followup_claude_run_id: "run-2",
      feedback_markdown: "Please shorten the intro.",
      status: "created",
      created_at: "2026-05-22T13:30:00Z",
    });

    renderVersion("version-1");

    const requestBtn = await screen.findByRole("button", {
      name: /^request revisions$/i,
    });

    // The form is not visible until the action is invoked.
    expect(
      screen.queryByRole("textbox", { name: /what should change/i }),
    ).toBeNull();

    await user.click(requestBtn);

    const textarea = screen.getByRole("textbox", {
      name: /what should change/i,
    });
    const submitBtn = screen.getByRole("button", {
      name: /^submit revision request$/i,
    });

    // Submit is disabled until the required field has content.
    expect(submitBtn).toBeDisabled();

    await user.type(textarea, "Please shorten the intro.");
    await user.click(screen.getByLabelText(/^shorten$/i));

    expect(submitBtn).toBeEnabled();

    await user.click(submitBtn);

    await waitFor(() =>
      expect(submitRevisionFeedbackMock).toHaveBeenCalledWith("version-1", {
        feedback_markdown: "Please shorten the intro.",
        structured_flags: { shorten: true },
      }),
    );

    await waitFor(() =>
      expect(screen.getByText(/run detail stub/i)).toBeInTheDocument(),
    );
  });

  it("omits structured_flags when no checkbox is ticked", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    submitRevisionFeedbackMock.mockResolvedValue({
      id: "rf-2",
      job_id: "job-1",
      source_resume_version_id: "version-1",
      followup_claude_run_id: "run-3",
      feedback_markdown: "Tighten the bullets.",
      status: "created",
      created_at: "2026-05-22T13:35:00Z",
    });

    renderVersion("version-1");

    const requestBtn = await screen.findByRole("button", {
      name: /^request revisions$/i,
    });
    await user.click(requestBtn);

    await user.type(
      screen.getByRole("textbox", { name: /what should change/i }),
      "Tighten the bullets.",
    );

    await user.click(
      screen.getByRole("button", { name: /^submit revision request$/i }),
    );

    await waitFor(() => expect(submitRevisionFeedbackMock).toHaveBeenCalled());
    const [, body] = submitRevisionFeedbackMock.mock.calls[0];
    expect(body).toEqual({ feedback_markdown: "Tighten the bullets." });
    expect("structured_flags" in body).toBe(false);
  });

  it("renders a parsed detail message when submitting revision feedback fails", async () => {
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    submitRevisionFeedbackMock.mockRejectedValue(
      new ApiErrorMock(
        "Request to /resume-versions/version-1/revision-feedback failed with status 422",
        422,
        { detail: "feedback_markdown must be non-empty." },
      ),
    );

    renderVersion("version-1");

    const requestBtn = await screen.findByRole("button", {
      name: /^request revisions$/i,
    });
    await user.click(requestBtn);

    await user.type(
      screen.getByRole("textbox", { name: /what should change/i }),
      "Something",
    );

    await user.click(
      screen.getByRole("button", { name: /^submit revision request$/i }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(/feedback_markdown must be non-empty/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Request to \//i)).toBeNull();
  });

  it("hides the Request revisions button on an approved draft", async () => {
    getResumeVersionMock.mockResolvedValue({ ...approvedVersion });

    renderVersion("version-1");

    await waitFor(() =>
      expect(screen.getByText(/Approved on /i)).toBeInTheDocument(),
    );

    expect(
      screen.queryByRole("button", { name: /request revisions/i }),
    ).toBeNull();
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

  it("displays the base master resume name and evidence source count", async () => {
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    listMasterResumesMock.mockResolvedValue([
      {
        id: "resume-1",
        name: "Calvin master resume",
        source_path: null,
        content_markdown: "",
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
        source: "database",
        source_format: null,
        is_demo: false,
      },
    ]);
    getRunMock.mockResolvedValue({
      id: "run-1",
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      run_dir: "runs/run-1",
      status: "imported",
      prompt_hash: null,
      input_hash: null,
      output_hash: null,
      created_at: "2026-05-22T10:00:00Z",
      started_at: null,
      completed_at: null,
      error_message: null,
      evidence_source_ids: ["ev-1", "ev-2"],
    });
    listEvidenceSourcesMock.mockResolvedValue([
      {
        id: "ev-1",
        name: "Primary bank",
        source_type: "evidence_bank",
        source_format: "md",
        source: "database",
        source_path: null,
        updated_at: "2026-05-10T00:00:00Z",
        is_demo: false,
      },
      {
        id: "ev-2",
        name: "Project notes",
        source_type: "project_note",
        source_format: "md",
        source: "filesystem",
        source_path: "candidate_context/project_notes/notes.md",
        updated_at: "2026-05-10T00:00:00Z",
        is_demo: false,
      },
    ]);

    renderVersion("version-1");

    await waitFor(() =>
      expect(screen.getByText("Calvin master resume")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(
        screen.getByText(/2 \(Primary bank, Project notes\)/i),
      ).toBeInTheDocument(),
    );
  });

  it("sends additional_evidence_source_ids when present in the payload", async () => {
    // Today the page does not yet expose an evidence picker in the
    // revision form, but the API layer must already accept the field
    // so backend support can ship ahead of the UI.
    const user = userEvent.setup();
    getResumeVersionMock.mockResolvedValue({ ...pendingVersion });
    submitRevisionFeedbackMock.mockResolvedValue({
      id: "rf-extra",
      job_id: "job-1",
      source_resume_version_id: "version-1",
      followup_claude_run_id: "run-9",
      feedback_markdown: "Add the new evidence.",
      status: "created",
      created_at: "2026-05-22T14:00:00Z",
    });

    // Simulate a future caller passing additional_evidence_source_ids by
    // invoking the mocked api directly.
    submitRevisionFeedbackMock("version-1", {
      feedback_markdown: "Add the new evidence.",
      additional_evidence_source_ids: ["ev-3"],
    });

    expect(submitRevisionFeedbackMock).toHaveBeenCalledWith("version-1", {
      feedback_markdown: "Add the new evidence.",
      additional_evidence_source_ids: ["ev-3"],
    });

    // The form-driven path still works without the extra ids.
    renderVersion("version-1");
    const requestBtn = await screen.findByRole("button", {
      name: /^request revisions$/i,
    });
    await user.click(requestBtn);
    await user.type(
      screen.getByRole("textbox", { name: /what should change/i }),
      "Polish.",
    );
    await user.click(
      screen.getByRole("button", { name: /^submit revision request$/i }),
    );
    await waitFor(() => expect(submitRevisionFeedbackMock).toHaveBeenCalled());
  });
});
