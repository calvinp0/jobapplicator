import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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
  createWordHandoffMock,
  getWordHandoffPromptMock,
  getWordHandoffInstructionsMock,
  getWordHandoffStatusMock,
  importWordResultMock,
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
    createWordHandoffMock: vi.fn(),
    getWordHandoffPromptMock: vi.fn(),
    getWordHandoffInstructionsMock: vi.fn(),
    getWordHandoffStatusMock: vi.fn(),
    importWordResultMock: vi.fn(),
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
  createApplication: vi.fn(),
  createWordHandoff: createWordHandoffMock,
  getWordHandoffPrompt: getWordHandoffPromptMock,
  getWordHandoffInstructions: getWordHandoffInstructionsMock,
  getWordHandoffStatus: getWordHandoffStatusMock,
  importWordResult: importWordResultMock,
  getRun: vi.fn(() => new Promise(() => {})),
  importRun: vi.fn(() => new Promise(() => {})),
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
  description_text: "Build great things.",
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

const newRun = {
  id: "run-word-1",
  job_id: "job-1",
  master_resume_id: "resume-1",
  evidence_bank_id: null,
  run_dir: "runs/run-word-1",
  status: "created",
  prompt_hash: null,
  input_hash: null,
  output_hash: null,
  created_at: "2026-05-22T12:00:00Z",
  started_at: null,
  completed_at: null,
  error_message: null,
};

const metadata = {
  run_id: "run-word-1",
  status: "word_handoff_ready",
  tailoring_method: "word_handoff",
  handoff_dir: "runs/run-word-1/word_handoff",
  resume_docx: "runs/run-word-1/word_handoff/01_resume_for_claude_word.docx",
  prompt_file: "runs/run-word-1/word_handoff/02_prompt_for_claude_word.txt",
  instructions_file: "runs/run-word-1/word_handoff/03_instructions.md",
  expected_output: "runs/run-word-1/output/word_tailored_resume.docx",
};

function makeStatus(overrides: Partial<{
  state: "not_prepared" | "prepared" | "missing_files" | "import_ready" | "imported";
  resume_docx: boolean;
  prompt_txt: boolean;
  instructions_md: boolean;
  expected_output_docx: boolean;
  final_resume_docx: boolean;
  missing_required_files: string[];
}> = {}) {
  const state = overrides.state ?? "prepared";
  return {
    run_id: "run-word-1",
    state,
    handoff_dir: "runs/run-word-1/word_handoff",
    handoff_dir_exists: state !== "not_prepared",
    files: {
      resume_docx: {
        name: "01_resume_for_claude_word.docx",
        path: "runs/run-word-1/word_handoff/01_resume_for_claude_word.docx",
        exists: overrides.resume_docx ?? true,
      },
      prompt_txt: {
        name: "02_prompt_for_claude_word.txt",
        path: "runs/run-word-1/word_handoff/02_prompt_for_claude_word.txt",
        exists: overrides.prompt_txt ?? true,
      },
      instructions_md: {
        name: "03_instructions.md",
        path: "runs/run-word-1/word_handoff/03_instructions.md",
        exists: overrides.instructions_md ?? true,
      },
      expected_output_docx: {
        name: "word_tailored_resume.docx",
        path: "runs/run-word-1/output/word_tailored_resume.docx",
        exists: overrides.expected_output_docx ?? false,
      },
      final_resume_docx: {
        name: "final_resume.docx",
        path: "runs/run-word-1/output/final_resume.docx",
        exists: overrides.final_resume_docx ?? false,
      },
    },
    missing_required_files: overrides.missing_required_files ?? [],
    message: "test status",
  };
}

describe("JobDetailPage Claude for Word handoff flow", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([resume]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);
    listRevisionFeedbacksMock.mockResolvedValue([]);
    createRunMock.mockResolvedValue(newRun);
    invokeRunMock.mockResolvedValue({ ...newRun, status: "running" });
    createWordHandoffMock.mockResolvedValue(metadata);
    getWordHandoffPromptMock.mockResolvedValue({
      run_id: "run-word-1",
      content: "PROMPT BODY HERE",
    });
    getWordHandoffInstructionsMock.mockResolvedValue({
      run_id: "run-word-1",
      content: "INSTRUCTIONS BODY HERE",
    });
    getWordHandoffStatusMock.mockResolvedValue(makeStatus({ state: "prepared" }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders both Generate Automatically and Prepare for Claude for Word buttons", async () => {
    renderJob("job-1");
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /senior engineer/i }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /^generate automatically$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    ).toBeInTheDocument();
  });

  it("preserves the existing auto generation flow on the primary button", async () => {
    const user = userEvent.setup();
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
    await waitFor(() =>
      expect(invokeRunMock).toHaveBeenCalledWith("run-word-1"),
    );
    expect(createWordHandoffMock).not.toHaveBeenCalled();
  });

  it("calls the word handoff endpoint and renders prompt + instructions", async () => {
    const user = userEvent.setup();
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    await waitFor(() =>
      expect(createWordHandoffMock).toHaveBeenCalledWith("run-word-1"),
    );
    // Auto path's invokeRun must NOT fire for the Word handoff button.
    expect(invokeRunMock).not.toHaveBeenCalled();

    const panel = await screen.findByRole("region", {
      name: /claude for word handoff/i,
    });
    expect(
      within(panel).getByLabelText(/claude for word prompt/i),
    ).toHaveValue("PROMPT BODY HERE");
    expect(
      within(panel).getByText(/INSTRUCTIONS BODY HERE/i),
    ).toBeInTheDocument();
    expect(
      within(panel).getAllByText(/output\/word_tailored_resume\.docx/i).length,
    ).toBeGreaterThan(0);
  });

  it("shows the waiting message when import response is not completed", async () => {
    const user = userEvent.setup();
    importWordResultMock.mockResolvedValue({
      run_id: "run-word-1",
      status: "waiting_for_word_result",
      message: "save it first",
      expected_output: "runs/run-word-1/output/word_tailored_resume.docx",
    });
    // Pretend the operator saved the file so the Import button renders.
    getWordHandoffStatusMock.mockResolvedValue(
      makeStatus({ state: "import_ready", expected_output_docx: true }),
    );
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    const panel = await screen.findByRole("region", {
      name: /claude for word handoff/i,
    });
    await user.click(
      within(panel).getByRole("button", { name: /import word result/i }),
    );
    await waitFor(() =>
      expect(importWordResultMock).toHaveBeenCalledWith("run-word-1"),
    );
    expect(
      await within(panel).findByText(/waiting for word result/i),
    ).toBeInTheDocument();
  });

  it("does not show the handoff panel when status reports not_prepared", async () => {
    const user = userEvent.setup();
    // Even after the POST returns, if the filesystem check says no folder,
    // the UI must not claim the handoff is prepared (task 112).
    getWordHandoffStatusMock.mockResolvedValue(
      makeStatus({ state: "not_prepared", resume_docx: false, prompt_txt: false, instructions_md: false }),
    );
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    await waitFor(() => expect(createWordHandoffMock).toHaveBeenCalled());
    expect(
      screen.queryByRole("region", { name: /claude for word handoff/i }),
    ).not.toBeInTheDocument();
  });

  it("renders folder path and file existence indicators when prepared", async () => {
    const user = userEvent.setup();
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    const panel = await screen.findByRole("region", {
      name: /claude for word handoff/i,
    });
    // Folder path is shown so the operator knows where the files live.
    expect(
      within(panel).getAllByText(/runs\/run-word-1\/word_handoff/i).length,
    ).toBeGreaterThan(0);
    // Each required file is listed with its name.
    expect(
      within(panel).getAllByText(/01_resume_for_claude_word\.docx/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(panel).getAllByText(/02_prompt_for_claude_word\.txt/i).length,
    ).toBeGreaterThan(0);
    expect(
      within(panel).getAllByText(/03_instructions\.md/i).length,
    ).toBeGreaterThan(0);
  });

  it("hides the Import button until the Word result file is on disk", async () => {
    const user = userEvent.setup();
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    const panel = await screen.findByRole("region", {
      name: /claude for word handoff/i,
    });
    expect(
      within(panel).queryByRole("button", { name: /import word result/i }),
    ).not.toBeInTheDocument();
    expect(
      within(panel).getByText(/word result not detected yet/i),
    ).toBeInTheDocument();
  });

  it("offers a regenerate action when files are missing", async () => {
    const user = userEvent.setup();
    getWordHandoffStatusMock.mockResolvedValue(
      makeStatus({
        state: "missing_files",
        prompt_txt: false,
        missing_required_files: ["02_prompt_for_claude_word.txt"],
      }),
    );
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    const panel = await screen.findByRole("region", {
      name: /claude for word handoff/i,
    });
    expect(
      within(panel).getByRole("button", { name: /regenerate handoff/i }),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(/02_prompt_for_claude_word\.txt/i),
    ).toBeInTheDocument();
  });

  it("shows the final resume location when import succeeds", async () => {
    const user = userEvent.setup();
    importWordResultMock.mockResolvedValue({
      run_id: "run-word-1",
      status: "completed",
      message: "imported",
      word_result: "runs/run-word-1/output/word_tailored_resume.docx",
      final_resume: "runs/run-word-1/output/final_resume.docx",
    });
    getWordHandoffStatusMock.mockResolvedValue(
      makeStatus({ state: "import_ready", expected_output_docx: true }),
    );
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
      screen.getByRole("button", { name: /^prepare for claude for word$/i }),
    );
    const panel = await screen.findByRole("region", {
      name: /claude for word handoff/i,
    });
    await user.click(
      within(panel).getByRole("button", { name: /import word result/i }),
    );
    expect(
      await within(panel).findByText(
        /runs\/run-word-1\/output\/final_resume\.docx/i,
      ),
    ).toBeInTheDocument();
  });
});
