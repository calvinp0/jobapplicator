import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getJobMock,
  listMasterResumesMock,
  listEvidenceBanksMock,
  listEvidenceSourcesMock,
  createRunMock,
  getRunMock,
  listCapturesMock,
  listResumeVersionsMock,
  listRunsMock,
  listApplicationsMock,
  listRevisionFeedbacksMock,
  invokeRunMock,
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
    listEvidenceSourcesMock: vi.fn(),
    createRunMock: vi.fn(),
    getRunMock: vi.fn(),
    listCapturesMock: vi.fn(),
    listResumeVersionsMock: vi.fn(),
    listRunsMock: vi.fn(),
    listApplicationsMock: vi.fn(),
    listRevisionFeedbacksMock: vi.fn(),
    invokeRunMock: vi.fn(),
    importRunMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getJob: getJobMock,
  listMasterResumes: listMasterResumesMock,
  listEvidenceBanks: listEvidenceBanksMock,
  listEvidenceSources: listEvidenceSourcesMock,
  createRun: createRunMock,
  getRun: getRunMock,
  listCaptures: listCapturesMock,
  listResumeVersions: listResumeVersionsMock,
  listRuns: listRunsMock,
  listApplications: listApplicationsMock,
  listRevisionFeedbacks: listRevisionFeedbacksMock,
  invokeRun: invokeRunMock,
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
import { RunDetailPage } from "../pages/RunDetailPage";

function renderJob(jobId: string) {
  return render(
    <MemoryRouter initialEntries={[`/jobs/${jobId}`]}>
      <Routes>
        <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const job = {
  id: "job-1",
  source_platform: "linkedin",
  external_url: "https://www.linkedin.com/jobs/view/1",
  external_job_id: null,
  company: "Acme Corp",
  title: "Senior Engineer",
  location: "Remote",
  description_text: "Build cool things.",
  application_method: "easy_apply",
  created_from_capture_id: null,
  created_at: "2026-05-22T12:01:00Z",
  updated_at: "2026-05-22T12:01:00Z",
};

const resume = {
  id: "resume-1",
  name: "Calvin – Generalist",
  source_path: null,
  content_markdown: "# Calvin",
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const evidenceBank = {
  id: "bank-1",
  name: "Backend evidence",
  source_path: null,
  content_markdown: "# Evidence",
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const evidenceSourceBank = {
  id: "bank-1",
  name: "Backend evidence",
  source_type: "evidence_bank" as const,
  source_format: "md",
  source: "database" as const,
  source_path: null,
  updated_at: "2026-05-22T10:00:00Z",
  is_demo: false,
};

const evidenceSourceDocx = {
  id: "fs:qchemresume",
  name: "Quantum chemistry resume.docx",
  source_type: "resume_variant" as const,
  source_format: "docx",
  source: "filesystem" as const,
  source_path: "candidate_context/resume_variants/qchem.docx",
  updated_at: "2026-05-22T10:00:00Z",
  is_demo: false,
};

const evidenceSourceProjectNote = {
  id: "fs:arcnote",
  name: "ARC project notes.md",
  source_type: "project_note" as const,
  source_format: "md",
  source: "filesystem" as const,
  source_path: "candidate_context/project_notes/arc.md",
  updated_at: "2026-05-22T10:00:00Z",
  is_demo: false,
};

const newRun = {
  id: "run-1",
  job_id: "job-1",
  master_resume_id: "resume-1",
  evidence_bank_id: "bank-1",
  run_dir: "runs/run-1",
  status: "created",
  prompt_hash: "p",
  input_hash: "i",
  output_hash: null,
  created_at: "2026-05-22T12:02:00Z",
  started_at: null,
  completed_at: null,
  error_message: null,
};

const invokedRun = { ...newRun, status: "running" };

describe("JobDetailPage generate draft flow", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([resume]);
    listEvidenceBanksMock.mockResolvedValue([evidenceBank]);
    listEvidenceSourcesMock.mockResolvedValue([
      evidenceSourceDocx,
      evidenceSourceProjectNote,
      evidenceSourceBank,
    ]);
    getRunMock.mockResolvedValue(invokedRun);
    listCapturesMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);
    listRevisionFeedbacksMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("creates and invokes a run in one click and stays on the Job page with live progress", async () => {
    const user = userEvent.setup();
    createRunMock.mockResolvedValue(newRun);
    invokeRunMock.mockResolvedValue(invokedRun);
    // Stall getRun so the polling tick does not race the assertions.
    getRunMock.mockReturnValue(new Promise(() => {}));

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
    // Pick a single evidence source via the new multi-select checkbox
    // picker. The legacy ``evidence_bank_id`` field stays null in the
    // payload; the chosen source is sent in ``evidence_source_ids``.
    await waitFor(() =>
      expect(
        screen.getByRole("checkbox", { name: /backend evidence/i }),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("checkbox", { name: /backend evidence/i }),
    );

    await user.click(
      screen.getByRole("button", { name: /^generate automatically$/i }),
    );

    await waitFor(() =>
      expect(createRunMock).toHaveBeenCalledWith({
        job_id: "job-1",
        master_resume_id: "resume-1",
        evidence_bank_id: null,
        evidence_source_ids: ["bank-1"],
      }),
    );
    await waitFor(() =>
      expect(invokeRunMock).toHaveBeenCalledWith("run-1"),
    );
    // The user stays on the Job page — the live workspace shows progress
    // inline rather than redirecting to the run detail page.
    expect(
      screen.getByRole("heading", { level: 2, name: /senior engineer/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: /resume tailoring run/i,
      }),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText(/tailoring in progress/i),
      ).toBeInTheDocument(),
    );
  });

  it("supports selecting multiple evidence sources and sends them in the payload", async () => {
    const user = userEvent.setup();
    createRunMock.mockResolvedValue(newRun);
    invokeRunMock.mockResolvedValue(invokedRun);
    getRunMock.mockReturnValue(new Promise(() => {}));

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

    await waitFor(() =>
      expect(
        screen.getByRole("checkbox", { name: /quantum chemistry/i }),
      ).toBeInTheDocument(),
    );
    // Multi-select: pick two sources of different types.
    await user.click(
      screen.getByRole("checkbox", { name: /quantum chemistry/i }),
    );
    await user.click(
      screen.getByRole("checkbox", { name: /arc project notes/i }),
    );

    await user.click(
      screen.getByRole("button", { name: /^generate automatically$/i }),
    );

    await waitFor(() =>
      expect(createRunMock).toHaveBeenCalledWith({
        job_id: "job-1",
        master_resume_id: "resume-1",
        evidence_bank_id: null,
        evidence_source_ids: ["fs:qchemresume", "fs:arcnote"],
      }),
    );
  });

  it("renders format, type, and source badges for evidence sources", async () => {
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("checkbox", { name: /quantum chemistry/i }),
      ).toBeInTheDocument(),
    );
    const docxItem = screen
      .getByRole("checkbox", { name: /quantum chemistry/i })
      .closest("label");
    expect(docxItem).not.toBeNull();
    // DOCX file from a filesystem resume_variant — all three badges visible.
    expect(docxItem!.textContent).toMatch(/DOCX/);
    expect(docxItem!.textContent).toMatch(/resume variant/);
    expect(docxItem!.textContent).toMatch(/filesystem/);

    const bankItem = screen
      .getByRole("checkbox", { name: /backend evidence/i })
      .closest("label");
    expect(bankItem!.textContent).toMatch(/MD/);
    expect(bankItem!.textContent).toMatch(/evidence bank/);
    expect(bankItem!.textContent).toMatch(/database/);
  });

  it("omits evidence_source_ids when nothing is selected (legacy default path)", async () => {
    const user = userEvent.setup();
    createRunMock.mockResolvedValue(newRun);
    invokeRunMock.mockResolvedValue(invokedRun);
    getRunMock.mockReturnValue(new Promise(() => {}));

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
      screen.getByRole("button", { name: /^generate automatically$/i }),
    );

    await waitFor(() => expect(createRunMock).toHaveBeenCalledTimes(1));
    const payload = createRunMock.mock.calls[0][0];
    expect(payload).toMatchObject({
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
    });
    expect(payload.evidence_source_ids).toBeUndefined();
  });

  it("blocks generate when no master resume is selected", async () => {
    const user = userEvent.setup();
    renderJob("job-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /senior engineer/i }),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /^generate automatically$/i }),
    );

    expect(
      await screen.findByText(/pick a master resume/i),
    ).toBeInTheDocument();
    expect(createRunMock).not.toHaveBeenCalled();
    expect(invokeRunMock).not.toHaveBeenCalled();
  });
});
