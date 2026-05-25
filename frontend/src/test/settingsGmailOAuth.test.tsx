import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  listMasterResumesMock,
  listEvidenceBanksMock,
  createMasterResumeMock,
  createEvidenceBankMock,
  listCapturesMock,
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
    listEvidenceBanksMock: vi.fn(),
    createMasterResumeMock: vi.fn(),
    createEvidenceBankMock: vi.fn(),
    listCapturesMock: vi.fn(),
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
  listEvidenceBanks: listEvidenceBanksMock,
  createMasterResume: createMasterResumeMock,
  createEvidenceBank: createEvidenceBankMock,
  listCaptures: listCapturesMock,
  getLlmProviderSetting: getLlmProviderSettingMock,
  setLlmProviderSetting: setLlmProviderSettingMock,
  getGmailStatus: getGmailStatusMock,
  getGmailAuthUrl: getGmailAuthUrlMock,
  getGmailOAuthSettings: getGmailOAuthSettingsMock,
  setGmailOAuthSettings: setGmailOAuthSettingsMock,
  deleteGmailOAuthSettings: deleteGmailOAuthSettingsMock,
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

function notConfiguredStatus() {
  return {
    connected: false,
    configured: false,
    missing_config: [
      "GOOGLE_CLIENT_ID",
      "GOOGLE_CLIENT_SECRET",
      "GOOGLE_REDIRECT_URI",
    ],
    email: null,
    scopes: [],
    token_path_configured: true,
    last_checked_at: null,
  };
}

function notConfiguredSettings() {
  return {
    configured: false,
    source: "none" as const,
    google_client_id: null,
    has_google_client_secret: false,
    google_client_secret_preview: "",
    google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
    gmail_token_path: "candidate_context/gmail/token.json",
    updated_at: null,
  };
}

function configuredViaSettings() {
  return {
    connected: false,
    configured: true,
    missing_config: [],
    email: null,
    scopes: [],
    token_path_configured: true,
    last_checked_at: null,
  };
}

function settingsLoadedConfig() {
  return {
    configured: true,
    source: "settings" as const,
    google_client_id: "saved-id.apps.googleusercontent.com",
    has_google_client_secret: true,
    google_client_secret_preview: "••••••••",
    google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
    gmail_token_path: "candidate_context/gmail/token.json",
    updated_at: "2026-05-26T12:00:00+00:00",
  };
}

describe("Gmail OAuth settings card", () => {
  beforeEach(() => {
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listCapturesMock.mockResolvedValue([]);
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
    getGmailAuthUrlMock.mockResolvedValue({
      auth_url: "https://accounts.google.com/o/oauth2/auth?fake=1",
      scope: "https://www.googleapis.com/auth/gmail.readonly",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the OAuth form when nothing is configured", async () => {
    getGmailStatusMock.mockResolvedValue(notConfiguredStatus());
    getGmailOAuthSettingsMock.mockResolvedValue(notConfiguredSettings());

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-oauth-form"),
      ).toBeInTheDocument(),
    );

    const form = screen.getByTestId("gmail-oauth-form");
    expect(within(form).getByLabelText(/google client id/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/google client secret/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/redirect uri/i)).toBeInTheDocument();
    expect(within(form).getByLabelText(/token path/i)).toBeInTheDocument();
  });

  it("save Gmail config posts to the settings endpoint", async () => {
    getGmailStatusMock
      .mockResolvedValueOnce(notConfiguredStatus())
      .mockResolvedValueOnce(configuredViaSettings());
    getGmailOAuthSettingsMock
      .mockResolvedValueOnce(notConfiguredSettings())
      .mockResolvedValueOnce(settingsLoadedConfig());
    setGmailOAuthSettingsMock.mockResolvedValue(settingsLoadedConfig());

    const user = userEvent.setup();
    renderPage();

    const form = await screen.findByTestId("gmail-oauth-form");
    await user.type(
      within(form).getByLabelText(/google client id/i),
      "new-id.apps.googleusercontent.com",
    );
    await user.type(
      within(form).getByLabelText(/google client secret/i),
      "shh-very-secret",
    );

    await user.click(screen.getByTestId("gmail-save-config-button"));

    await waitFor(() => expect(setGmailOAuthSettingsMock).toHaveBeenCalledTimes(1));
    expect(setGmailOAuthSettingsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        google_client_id: "new-id.apps.googleusercontent.com",
        google_client_secret: "shh-very-secret",
        google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
        gmail_token_path: "candidate_context/gmail/token.json",
        preserve_existing_secret: false,
      }),
    );
  });

  it("renders Connect Gmail after saving and never shows the plaintext secret", async () => {
    getGmailStatusMock
      .mockResolvedValueOnce(notConfiguredStatus())
      .mockResolvedValueOnce(configuredViaSettings());
    getGmailOAuthSettingsMock
      .mockResolvedValueOnce(notConfiguredSettings())
      .mockResolvedValueOnce(settingsLoadedConfig());
    setGmailOAuthSettingsMock.mockResolvedValue(settingsLoadedConfig());

    const user = userEvent.setup();
    const { container } = renderPage();

    const form = await screen.findByTestId("gmail-oauth-form");
    const secret = "leak-me-please-12345";
    await user.type(
      within(form).getByLabelText(/google client id/i),
      "new-id.apps.googleusercontent.com",
    );
    await user.type(
      within(form).getByLabelText(/google client secret/i),
      secret,
    );

    await user.click(screen.getByTestId("gmail-save-config-button"));

    await waitFor(() =>
      expect(screen.getByTestId("gmail-connect-button")).toBeInTheDocument(),
    );

    // The plaintext secret must not appear anywhere in the rendered page.
    expect(container.innerHTML).not.toContain(secret);
  });

  it("labels env-loaded config and offers an override path", async () => {
    getGmailStatusMock.mockResolvedValue(configuredViaSettings());
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

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("gmail-config-source")).toHaveTextContent(
        /environment/i,
      ),
    );
    expect(
      screen.getByTestId("gmail-env-source-note"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("gmail-edit-config-button"),
    ).toHaveTextContent(/override with local settings/i);
  });

  it("deletes local Gmail config via the settings endpoint", async () => {
    getGmailStatusMock
      .mockResolvedValueOnce(configuredViaSettings())
      .mockResolvedValueOnce(notConfiguredStatus());
    getGmailOAuthSettingsMock
      .mockResolvedValueOnce(settingsLoadedConfig())
      .mockResolvedValueOnce(notConfiguredSettings());

    const user = userEvent.setup();
    renderPage();

    const deleteButton = await screen.findByTestId(
      "gmail-delete-config-button",
    );
    await user.click(deleteButton);

    await waitFor(() =>
      expect(deleteGmailOAuthSettingsMock).toHaveBeenCalledTimes(1),
    );
  });

  it("missing-config text mentions Settings", async () => {
    getGmailStatusMock.mockResolvedValue(notConfiguredStatus());
    getGmailOAuthSettingsMock.mockResolvedValue(notConfiguredSettings());

    renderPage();

    const notConfigured = await screen.findByTestId("gmail-not-configured");
    expect(notConfigured).toHaveTextContent(/save your google oauth client id/i);
  });
});
