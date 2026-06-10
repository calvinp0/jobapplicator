import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  getLocalLlmSettingsMock,
  setLocalLlmSettingsMock,
  testLocalLlmConnectionMock,
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
    getLocalLlmSettingsMock: vi.fn(),
    setLocalLlmSettingsMock: vi.fn(),
    testLocalLlmConnectionMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listMasterResumes: vi.fn(() => Promise.resolve([])),
  listEvidenceSources: vi.fn(() => Promise.resolve([])),
  createMasterResume: vi.fn(),
  createEvidenceBank: vi.fn(),
  importMasterResumeFile: vi.fn(),
  importEvidenceSourceFile: vi.fn(),
  resetLocalData: vi.fn(),
  getLlmProviderSetting: vi.fn(() =>
    Promise.resolve({
      default_provider: "claude_code",
      available: [
        {
          id: "claude_code",
          display_name: "Claude Code",
          default_binary: "claude",
          binary_env_var: "JOBAPPLY_CLAUDE_BINARY",
        },
      ],
    }),
  ),
  setLlmProviderSetting: vi.fn(),
  getGmailStatus: vi.fn(() =>
    Promise.resolve({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    }),
  ),
  getGmailAuthUrl: vi.fn(),
  getGmailOAuthSettings: vi.fn(() =>
    Promise.resolve({
      configured: false,
      source: "none",
      google_client_id: null,
      has_google_client_secret: false,
      google_client_secret_preview: "",
      google_redirect_uri: "http://localhost:8000/gmail/oauth/callback",
      gmail_token_path: "candidate_context/gmail/token.json",
      updated_at: null,
    }),
  ),
  setGmailOAuthSettings: vi.fn(),
  deleteGmailOAuthSettings: vi.fn(),
  getExportSettings: vi.fn(() =>
    Promise.resolve({ path: "candidate_context/exports" }),
  ),
  getLocalLlmSettings: getLocalLlmSettingsMock,
  setLocalLlmSettings: setLocalLlmSettingsMock,
  testLocalLlmConnection: testLocalLlmConnectionMock,
  ApiError: ApiErrorMock,
}));

import { SettingsPage } from "../pages/SettingsPage";

const TASK_POLICY = [
  { task: "job_summary", risk: "low", configurable: true, default_local: true },
  { task: "ats_keywords", risk: "low", configurable: true, default_local: true },
  {
    task: "email_classification",
    risk: "low",
    configurable: true,
    default_local: true,
  },
  {
    task: "resume_suggestions",
    risk: "experimental",
    configurable: true,
    default_local: false,
  },
  {
    task: "resume_tailoring",
    risk: "high",
    configurable: true,
    default_local: false,
  },
  { task: "claim_audit", risk: "high", configurable: true, default_local: false },
  {
    task: "recruiter_review",
    risk: "claude_only",
    configurable: false,
    default_local: false,
  },
];

function defaultSettings(overrides = {}) {
  return {
    enabled: false,
    provider: "openai_compatible",
    base_url: "http://localhost:11434/v1",
    model: "llama3.1:8b",
    timeout_seconds: 60,
    allowed_tasks: {
      job_summary: true,
      ats_keywords: true,
      email_classification: true,
      resume_suggestions: false,
      resume_tailoring: false,
      claim_audit: false,
    },
    has_api_key: false,
    api_key_preview: "",
    updated_at: null,
    task_policy: TASK_POLICY,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

function getCard() {
  return screen.getByTestId("local-llm-card");
}

describe("SettingsPage – Local LLM card", () => {
  beforeEach(() => {
    getLocalLlmSettingsMock.mockResolvedValue(defaultSettings());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the LLM Providers section", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", {
        level: 3,
        name: /local llm \(experimental\)/i,
      }),
    ).toBeInTheDocument();
  });

  it("shows the experimental warning copy", async () => {
    renderPage();
    const card = await waitFor(() => getCard());
    expect(
      within(card).getByText(/local llm support is experimental/i),
    ).toBeInTheDocument();
    expect(
      within(card).getByText(
        /final resume tailoring and claim audits should use claude code/i,
      ),
    ).toBeInTheDocument();
  });

  it("lets the user edit the endpoint and model fields", async () => {
    const user = userEvent.setup();
    renderPage();
    const card = await waitFor(() => getCard());

    const endpoint = within(card).getByLabelText(
      /local llm endpoint/i,
    ) as HTMLInputElement;
    const model = within(card).getByLabelText(/model name/i) as HTMLInputElement;

    await user.clear(endpoint);
    await user.type(endpoint, "http://localhost:1234/v1");
    await user.clear(model);
    await user.type(model, "qwen2.5-coder:14b");

    expect(endpoint.value).toBe("http://localhost:1234/v1");
    expect(model.value).toBe("qwen2.5-coder:14b");
  });

  it("marks full resume tailoring as high-risk and off by default", async () => {
    renderPage();
    const card = await waitFor(() => getCard());

    const tailoringCheckbox = within(card).getByRole("checkbox", {
      name: /full resume tailoring/i,
    }) as HTMLInputElement;
    expect(tailoringCheckbox.checked).toBe(false);

    // Risk labels are visible next to each high-risk task (tailoring + audit).
    expect(
      within(card).getAllByText(/high risk — off by default/i).length,
    ).toBeGreaterThan(0);
  });

  it("calls the backend when Test connection is clicked", async () => {
    const user = userEvent.setup();
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: true,
      message: "Connected — model responded.",
      model: "llama3.1:8b",
      provider: "local_openai_compatible",
      latency_ms: 12,
      error: null,
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    expect(testLocalLlmConnectionMock).toHaveBeenCalledTimes(1);
    expect(
      await within(card).findByText(/connected — model responded/i),
    ).toBeInTheDocument();
  });

  it("surfaces a test-connection failure", async () => {
    const user = userEvent.setup();
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: false,
      message: "Connection failed.",
      model: "llama3.1:8b",
      provider: "local_openai_compatible",
      latency_ms: null,
      error: "timeout after 60s",
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    expect(
      await within(card).findByText(/timeout after 60s/i),
    ).toBeInTheDocument();
  });

  it("displays saved settings (enabled endpoint/model) correctly", async () => {
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({
        enabled: true,
        base_url: "http://localhost:1234/v1",
        model: "mistral-small",
        has_api_key: true,
        api_key_preview: "••••••••",
      }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    const enabled = within(card).getByRole("checkbox", {
      name: /enable local llm/i,
    }) as HTMLInputElement;
    expect(enabled.checked).toBe(true);

    expect(
      (within(card).getByLabelText(/local llm endpoint/i) as HTMLInputElement)
        .value,
    ).toBe("http://localhost:1234/v1");
    expect(
      (within(card).getByLabelText(/model name/i) as HTMLInputElement).value,
    ).toBe("mistral-small");
  });

  it("saves edited settings through the API", async () => {
    const user = userEvent.setup();
    setLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ enabled: true, model: "mistral-small" }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("checkbox", { name: /enable local llm/i }),
    );
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(setLocalLlmSettingsMock).toHaveBeenCalledTimes(1));
    const payload = setLocalLlmSettingsMock.mock.calls[0][0];
    expect(payload.enabled).toBe(true);
    expect(
      await within(card).findByText(/saved\./i),
    ).toBeInTheDocument();
  });
});
