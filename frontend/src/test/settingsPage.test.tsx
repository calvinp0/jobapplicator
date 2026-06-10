import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  listMasterResumesMock,
  listEvidenceSourcesMock,
  createMasterResumeMock,
  createEvidenceBankMock,
  importMasterResumeFileMock,
  importEvidenceSourceFileMock,
  resetLocalDataMock,
  getLlmProviderSettingMock,
  setLlmProviderSettingMock,
  getGmailStatusMock,
  getGmailAuthUrlMock,
  getGmailOAuthSettingsMock,
  setGmailOAuthSettingsMock,
  deleteGmailOAuthSettingsMock,
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
    listMasterResumesMock: vi.fn(),
    listEvidenceSourcesMock: vi.fn(),
    createMasterResumeMock: vi.fn(),
    createEvidenceBankMock: vi.fn(),
    importMasterResumeFileMock: vi.fn(),
    importEvidenceSourceFileMock: vi.fn(),
    resetLocalDataMock: vi.fn(),
    getLlmProviderSettingMock: vi.fn(),
    setLlmProviderSettingMock: vi.fn(),
    getGmailStatusMock: vi.fn(),
    getGmailAuthUrlMock: vi.fn(),
    getGmailOAuthSettingsMock: vi.fn(),
    setGmailOAuthSettingsMock: vi.fn(),
    deleteGmailOAuthSettingsMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listMasterResumes: listMasterResumesMock,
  listEvidenceSources: listEvidenceSourcesMock,
  createMasterResume: createMasterResumeMock,
  createEvidenceBank: createEvidenceBankMock,
  importMasterResumeFile: importMasterResumeFileMock,
  importEvidenceSourceFile: importEvidenceSourceFileMock,
  resetLocalData: resetLocalDataMock,
  getLlmProviderSetting: getLlmProviderSettingMock,
  setLlmProviderSetting: setLlmProviderSettingMock,
  getGmailStatus: getGmailStatusMock,
  getGmailAuthUrl: getGmailAuthUrlMock,
  getGmailOAuthSettings: getGmailOAuthSettingsMock,
  setGmailOAuthSettings: setGmailOAuthSettingsMock,
  deleteGmailOAuthSettings: deleteGmailOAuthSettingsMock,
  getExportSettings: vi.fn(() =>
    Promise.resolve({ path: "candidate_context/exports" }),
  ),
  ApiError: ApiErrorMock,
}));

import { SettingsPage } from "../pages/SettingsPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

function getResumeCard() {
  return screen.getByTestId("master-resumes-card");
}

function getEvidenceCard() {
  return screen.getByTestId("evidence-sources-card");
}

describe("SettingsPage", () => {
  beforeEach(() => {
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceSourcesMock.mockResolvedValue([]);
    getLlmProviderSettingMock.mockResolvedValue({
      default_provider: "claude_code",
      available: [
        {
          id: "claude_code",
          display_name: "Claude Code",
          default_binary: "claude",
          binary_env_var: "JOBAPPLY_CLAUDE_BINARY",
        },
      ],
    });
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });
    getGmailAuthUrlMock.mockResolvedValue({
      auth_url: "https://accounts.google.com/o/oauth2/auth?fake=1",
      scope: "https://www.googleapis.com/auth/gmail.readonly",
    });
    getGmailOAuthSettingsMock.mockResolvedValue({
      configured: true,
      source: "environment",
      google_client_id: "env-id.apps.googleusercontent.com",
      has_google_client_secret: true,
      google_client_secret_preview: "from environment",
      google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
      gmail_token_path: "candidate_context/gmail/token.json",
      updated_at: null,
    });
    setGmailOAuthSettingsMock.mockResolvedValue({
      configured: true,
      source: "settings",
      google_client_id: "saved-id.apps.googleusercontent.com",
      has_google_client_secret: true,
      google_client_secret_preview: "••••••••",
      google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
      gmail_token_path: "candidate_context/gmail/token.json",
      updated_at: "2026-05-26T12:00:00+00:00",
    });
    deleteGmailOAuthSettingsMock.mockResolvedValue({
      configured: false,
      source: "none",
      google_client_id: null,
      has_google_client_secret: false,
      google_client_secret_preview: "",
      google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
      gmail_token_path: "candidate_context/gmail/token.json",
      updated_at: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the redesigned settings hub with grouped panels", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^settings$/i }),
      ).toBeInTheDocument(),
    );

    for (const groupLabel of [
      /gmail integration/i,
      /document tooling/i,
      /claude \/ llm/i,
      /browser extension/i,
      /prompt harnesses/i,
      /danger zone/i,
    ]) {
      expect(
        screen.getByRole("region", { name: groupLabel }),
      ).toBeInTheDocument();
    }
  });

  it("renders both document cards with their headers and empty-state copy", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /master resumes/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByRole("heading", { level: 3, name: /evidence sources/i }),
    ).toBeInTheDocument();

    expect(
      screen.getByText("No master resumes yet — add one to enable tailoring."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "No evidence sources yet — optional, but useful for grounded tailoring.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a file picker for master resume import and no editable Source Path field", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /\+ add master resume/i }),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const card = getResumeCard();
    // File-upload mode is the default: a real file picker is shown.
    const fileInput = within(card).getByTestId("master-resumes-card-file-input");
    expect(fileInput).toHaveAttribute("type", "file");
    // The old free-text "Source path" field is gone entirely.
    expect(
      within(card).queryByLabelText(/source path/i),
    ).not.toBeInTheDocument();
  });

  it("shows a file picker for evidence import", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /\+ add evidence source/i }),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add evidence source/i }),
    );

    const card = getEvidenceCard();
    expect(
      within(card).getByTestId("evidence-sources-card-file-input"),
    ).toHaveAttribute("type", "file");
    expect(
      within(card).queryByLabelText(/source path/i),
    ).not.toBeInTheDocument();
  });

  it("displays the selected filename after choosing a file", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /\+ add master resume/i }),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const card = getResumeCard();
    const file = new File(["resume bytes"], "calvin_resume.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    await user.upload(
      within(card).getByTestId("master-resumes-card-file-input"),
      file,
    );

    expect(
      within(card).getByTestId("master-resumes-card-filename"),
    ).toHaveTextContent("calvin_resume.docx");
  });

  it("imports a master resume file and refreshes the list", async () => {
    const user = userEvent.setup();
    importMasterResumeFileMock.mockResolvedValue({
      id: "fs:abc123",
      name: "calvin_resume.docx",
      source_type: "master_resume",
      source_format: "docx",
      original_filename: "calvin_resume.docx",
      stored_path: "candidate_context/master_resumes/calvin_resume.docx",
      imported_at: "2026-06-10T10:00:00Z",
    });

    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no master resumes yet/i)).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const card = getResumeCard();
    const file = new File(["bytes"], "calvin_resume.docx");
    await user.upload(
      within(card).getByTestId("master-resumes-card-file-input"),
      file,
    );
    await user.click(
      within(card).getByRole("button", { name: /^import master resume$/i }),
    );

    await waitFor(() =>
      expect(importMasterResumeFileMock).toHaveBeenCalledWith(file),
    );
    // The list is refetched after a successful import.
    await waitFor(() =>
      expect(listMasterResumesMock).toHaveBeenCalledTimes(2),
    );
  });

  it("still supports manual content mode for master resumes", async () => {
    const user = userEvent.setup();
    createMasterResumeMock.mockResolvedValue({
      id: "resume-1",
      name: "Calvin – Generalist",
      source: "database",
      source_format: null,
      content_markdown: "# Calvin",
      created_at: "2026-05-22T10:00:00Z",
      updated_at: "2026-05-22T10:00:00Z",
    });

    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no master resumes yet/i)).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const card = getResumeCard();
    // Switch to manual paste mode.
    await user.click(within(card).getByLabelText(/paste content manually/i));

    await user.type(within(card).getByLabelText(/^name$/i), "Calvin – Generalist");
    await user.type(
      within(card).getByLabelText(/content \(markdown\)/i),
      "# Calvin",
    );
    await user.click(
      within(card).getByRole("button", { name: /^add master resume$/i }),
    );

    await waitFor(() =>
      expect(createMasterResumeMock).toHaveBeenCalledWith({
        name: "Calvin – Generalist",
        content_markdown: "# Calvin",
      }),
    );
  });

  it("opens a confirmation dialog when Reset local data is clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    const resetButton = await screen.findByTestId("reset-local-data-button");
    expect(
      screen.queryByTestId("reset-confirm-dialog"),
    ).not.toBeInTheDocument();

    await user.click(resetButton);

    expect(screen.getByTestId("reset-confirm-dialog")).toBeInTheDocument();
    expect(
      screen.getByRole("dialog", { name: /reset local data/i }),
    ).toBeInTheDocument();
  });

  it("requires typing RESET before the reset is allowed to run", async () => {
    const user = userEvent.setup();
    resetLocalDataMock.mockResolvedValue({
      ok: true,
      backup_path: "backups/database/reset-2026-06-10.db",
      deleted: { jobs: 2, applications: 1, runs: 3, captures: 1 },
    });

    renderPage();
    await user.click(await screen.findByTestId("reset-local-data-button"));

    const confirmButton = screen.getByTestId("reset-confirm-button");
    // Disabled until the exact confirmation text is entered.
    expect(confirmButton).toBeDisabled();

    await user.type(
      screen.getByLabelText(/type reset to confirm/i),
      "nope",
    );
    expect(confirmButton).toBeDisabled();
    expect(resetLocalDataMock).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText(/type reset to confirm/i));
    await user.type(screen.getByLabelText(/type reset to confirm/i), "RESET");
    expect(confirmButton).toBeEnabled();

    await user.click(confirmButton);

    await waitFor(() =>
      expect(resetLocalDataMock).toHaveBeenCalledWith("RESET"),
    );
    expect(
      await screen.findByText(/local data reset/i),
    ).toBeInTheDocument();
  });

  it("renders the Gmail integration card and the privacy note", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /gmail integration/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByText(
        /gmail is used read-only for application tracking\. jobapplicator does not send, delete, archive, or label emails\./i,
      ),
    ).toBeInTheDocument();
  });

  it("shows the Connect Gmail action when configured but disconnected", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-settings-status"),
      ).toHaveTextContent(/not connected/i),
    );
    expect(screen.getByTestId("gmail-connect-button")).toBeInTheDocument();
  });
});
