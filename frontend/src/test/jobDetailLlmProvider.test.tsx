import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
  createApplicationMock,
  getRunMock,
  importRunMock,
  getLlmProviderSettingMock,
  createWordHandoffMock,
  getWordHandoffPromptMock,
  getWordHandoffInstructionsMock,
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
    createApplicationMock: vi.fn(),
    getRunMock: vi.fn(),
    importRunMock: vi.fn(),
    getLlmProviderSettingMock: vi.fn(),
    createWordHandoffMock: vi.fn(),
    getWordHandoffPromptMock: vi.fn(),
    getWordHandoffInstructionsMock: vi.fn(),
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
  createApplication: createApplicationMock,
  getRun: getRunMock,
  importRun: importRunMock,
  getLlmProviderSetting: getLlmProviderSettingMock,
  createWordHandoff: createWordHandoffMock,
  getWordHandoffPrompt: getWordHandoffPromptMock,
  getWordHandoffInstructions: getWordHandoffInstructionsMock,
  importWordResult: importWordResultMock,
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
  description_text: "We are hiring. Build great things.",
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

const providers = [
  {
    id: "claude_code",
    display_name: "Claude Code",
    default_binary: "claude",
    binary_env_var: "JOBAPPLY_CLAUDE_BINARY",
  },
  {
    id: "codex",
    display_name: "Codex",
    default_binary: "codex",
    binary_env_var: "JOBAPPLY_CODEX_BINARY",
  },
  {
    id: "gemini",
    display_name: "Gemini",
    default_binary: "gemini",
    binary_env_var: "JOBAPPLY_GEMINI_BINARY",
  },
];

const baseRun = {
  id: "run-new",
  job_id: "job-1",
  master_resume_id: "resume-1",
  evidence_bank_id: null,
  run_dir: "runs/run-new",
  status: "created",
  prompt_hash: null,
  input_hash: null,
  output_hash: null,
  created_at: "2026-05-22T12:00:00Z",
  started_at: null,
  completed_at: null,
  error_message: null,
};

describe("JobDetailPage per-run LLM provider override", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listMasterResumesMock.mockResolvedValue([resume]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listResumeVersionsMock.mockResolvedValue([]);
    listRunsMock.mockResolvedValue([]);
    listApplicationsMock.mockResolvedValue([]);
    listRevisionFeedbacksMock.mockResolvedValue([]);
    getLlmProviderSettingMock.mockResolvedValue({
      default_provider: "codex",
      available: providers,
    });
    getRunMock.mockReturnValue(new Promise(() => {}));
    importRunMock.mockReturnValue(new Promise(() => {}));
    createRunMock.mockResolvedValue({ ...baseRun, llm_provider: "codex" });
    invokeRunMock.mockResolvedValue({
      ...baseRun,
      status: "running",
      started_at: "2026-05-22T12:00:01Z",
      llm_provider: "codex",
    });
    createWordHandoffMock.mockResolvedValue({
      run_id: "run-new",
      status: "word_handoff_prepared",
      tailoring_method: "word_handoff",
      handoff_dir: "runs/run-new/handoff",
      resume_docx: null,
      prompt_file: null,
      instructions_file: null,
      expected_output: "output/word_tailored_resume.docx",
    });
    getWordHandoffPromptMock.mockResolvedValue({
      run_id: "run-new",
      content: "PROMPT",
    });
    getWordHandoffInstructionsMock.mockResolvedValue({
      run_id: "run-new",
      content: "INSTRUCTIONS",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists the providers returned by the API in the selector", async () => {
    renderJob("job-1");
    const select = (await screen.findByRole("combobox", {
      name: /llm provider/i,
    })) as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((o) => o.textContent);
    expect(optionLabels).toEqual(["Claude Code", "Codex", "Gemini"]);
  });

  it("defaults the selector to the persisted default provider", async () => {
    renderJob("job-1");
    const select = (await screen.findByRole("combobox", {
      name: /llm provider/i,
    })) as HTMLSelectElement;
    expect(select.value).toBe("codex");
  });

  it("sends the chosen provider id when the user picks a non-default", async () => {
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
    const providerSelect = await screen.findByRole("combobox", {
      name: /llm provider/i,
    });
    await user.selectOptions(providerSelect, "gemini");

    await user.click(
      screen.getByRole("button", { name: /^generate automatically$/i }),
    );

    await waitFor(() => expect(createRunMock).toHaveBeenCalledTimes(1));
    expect(createRunMock).toHaveBeenCalledWith({
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
      llm_provider: "gemini",
    });
  });

  it("omits llm_provider when the selector is left at the default", async () => {
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
    // Selector is left at the default (codex).
    await user.click(
      screen.getByRole("button", { name: /^generate automatically$/i }),
    );

    await waitFor(() => expect(createRunMock).toHaveBeenCalledTimes(1));
    const payload = createRunMock.mock.calls[0][0];
    expect(payload).toEqual({
      job_id: "job-1",
      master_resume_id: "resume-1",
      evidence_bank_id: null,
    });
    expect(payload).not.toHaveProperty("llm_provider");
  });

  it("does not pass llm_provider when preparing the Claude for Word handoff", async () => {
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
    // Pick a non-default to prove the Word button still does not forward it.
    const providerSelect = await screen.findByRole("combobox", {
      name: /llm provider/i,
    });
    await user.selectOptions(providerSelect, "gemini");

    await user.click(
      screen.getByRole("button", { name: /prepare for claude for word/i }),
    );

    await waitFor(() => expect(createRunMock).toHaveBeenCalledTimes(1));
    const payload = createRunMock.mock.calls[0][0];
    expect(payload).not.toHaveProperty("llm_provider");
  });
});
