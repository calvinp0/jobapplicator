import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  getLocalLlmSettingsMock,
  setLocalLlmSettingsMock,
  testLocalLlmConnectionMock,
  listLocalLlmModelsMock,
  pullLocalLlmModelMock,
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
    listLocalLlmModelsMock: vi.fn(),
    pullLocalLlmModelMock: vi.fn(),
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
  listLocalLlmModels: listLocalLlmModelsMock,
  pullLocalLlmModel: pullLocalLlmModelMock,
  ApiError: ApiErrorMock,
}));

import { SettingsPage } from "../pages/SettingsPage";

const TASK_POLICY = [
  { task: "job_summary", risk: "low", configurable: true, default_local: true },
  { task: "ats_keywords", risk: "low", configurable: true, default_local: true },
  {
    task: "role_requirements",
    risk: "low",
    configurable: true,
    default_local: true,
  },
  {
    task: "evidence_gap_plan",
    risk: "low",
    configurable: true,
    default_local: true,
  },
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
    context_window_tokens: 8192,
    reserved_output_tokens: 1200,
    max_input_tokens: 6500,
    num_ctx: null,
    max_output_tokens: null,
    allow_compression: true,
    allow_fallback: true,
    abort_on_over_budget: false,
    allowed_tasks: {
      job_summary: true,
      ats_keywords: true,
      role_requirements: true,
      evidence_gap_plan: true,
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

  it("shows the local LLM preflight task toggles", async () => {
    renderPage();
    const card = await waitFor(() => getCard());

    // The four low-risk preflight tasks each render a checkbox, on by default.
    for (const name of [
      /job summary/i,
      /ats keyword extraction/i,
      /role requirement extraction/i,
      /evidence gap planning/i,
    ]) {
      const checkbox = within(card).getByRole("checkbox", {
        name,
      }) as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    }
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
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: null,
      context_verified: false,
      context_warning: null,
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
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: null,
      context_verified: false,
      context_warning: null,
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
    expect(payload.context_window_tokens).toBe(8192);
    expect(payload.reserved_output_tokens).toBe(1200);
    expect(payload.max_input_tokens).toBe(6500);
    expect(
      await within(card).findByText(/saved\./i),
    ).toBeInTheDocument();
  });

  it("renders context budget and reserved output token fields", async () => {
    renderPage();
    const card = await waitFor(() => getCard());

    expect(
      within(card).getByLabelText(/jobapplicator context budget/i),
    ).toBeInTheDocument();
    expect(
      within(card).getByLabelText(/reserved output tokens/i),
    ).toBeInTheDocument();
  });

  it("labels the budget control honestly and explains the distinction", async () => {
    renderPage();
    const card = await waitFor(() => getCard());

    // Renamed away from "Context window tokens" (task 128): the field only
    // drives JobApplicator's budgeting, not the server's context.
    expect(
      within(card).queryByLabelText(/context window tokens/i),
    ).toBeNull();
    expect(
      within(card).getByText(
        /does not change the running model server/i,
      ),
    ).toBeInTheDocument();
    // The summary uses the same renamed wording.
    expect(
      within(card).getAllByText(/jobapplicator context budget/i).length,
    ).toBeGreaterThan(1);
  });

  it("displays the usable input budget", async () => {
    renderPage();
    const card = await waitFor(() => getCard());

    expect(within(card).getByText(/usable input budget/i)).toBeInTheDocument();
    expect(within(card).getByText(/6500 tokens/i)).toBeInTheDocument();
  });

  it("shows a local context warning for small context windows", async () => {
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({
        context_window_tokens: 2048,
        reserved_output_tokens: 512,
        max_input_tokens: 1536,
      }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    expect(
      within(card).getByText(/this context window is small/i),
    ).toBeInTheDocument();
  });

  it("shows a validation error for impossible budget input", async () => {
    const user = userEvent.setup();
    renderPage();
    const card = await waitFor(() => getCard());

    await user.clear(within(card).getByLabelText(/reserved output tokens/i));
    await user.type(within(card).getByLabelText(/reserved output tokens/i), "9000");
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    expect(
      await within(card).findByText(
        /reserved output tokens must be smaller than context window tokens/i,
      ),
    ).toBeInTheDocument();
    expect(setLocalLlmSettingsMock).not.toHaveBeenCalled();
  });

  it("shows the num_ctx control only for the Ollama provider", async () => {
    const user = userEvent.setup();
    renderPage();
    const card = await waitFor(() => getCard());

    // Default provider is openai_compatible: no num_ctx control.
    expect(
      within(card).queryByLabelText(/ollama context length/i),
    ).toBeNull();

    await user.selectOptions(
      within(card).getByLabelText(/provider/i),
      "ollama",
    );
    expect(
      within(card).getByLabelText(/ollama context length/i),
    ).toBeInTheDocument();

    await user.selectOptions(
      within(card).getByLabelText(/provider/i),
      "openai_compatible",
    );
    expect(
      within(card).queryByLabelText(/ollama context length/i),
    ).toBeNull();
  });

  it("loads a saved num_ctx and sends edits through the API", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", num_ctx: 16384 }),
    );
    setLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", num_ctx: 8192 }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    const numCtxInput = within(card).getByLabelText(
      /ollama context length/i,
    ) as HTMLInputElement;
    expect(numCtxInput.value).toBe("16384");

    await user.clear(numCtxInput);
    await user.type(numCtxInput, "8192");
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(setLocalLlmSettingsMock).toHaveBeenCalledTimes(1),
    );
    expect(setLocalLlmSettingsMock.mock.calls[0][0].num_ctx).toBe(8192);
  });

  it("treats an empty num_ctx as unset when saving", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", num_ctx: 16384 }),
    );
    setLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", num_ctx: null }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    await user.clear(within(card).getByLabelText(/ollama context length/i));
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(setLocalLlmSettingsMock).toHaveBeenCalledTimes(1),
    );
    expect(setLocalLlmSettingsMock.mock.calls[0][0].num_ctx).toBeNull();
  });

  it("loads a saved max output tokens value and sends edits through the API", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ max_output_tokens: 512 }),
    );
    setLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ max_output_tokens: 1024 }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    const maxOutputInput = within(card).getByLabelText(
      /max output tokens/i,
    ) as HTMLInputElement;
    expect(maxOutputInput.value).toBe("512");

    await user.clear(maxOutputInput);
    await user.type(maxOutputInput, "1024");
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(setLocalLlmSettingsMock).toHaveBeenCalledTimes(1),
    );
    expect(setLocalLlmSettingsMock.mock.calls[0][0].max_output_tokens).toBe(
      1024,
    );
  });

  it("treats an empty max output tokens field as unset when saving", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ max_output_tokens: 512 }),
    );
    setLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ max_output_tokens: null }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    await user.clear(within(card).getByLabelText(/max output tokens/i));
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(setLocalLlmSettingsMock).toHaveBeenCalledTimes(1),
    );
    expect(
      setLocalLlmSettingsMock.mock.calls[0][0].max_output_tokens,
    ).toBeNull();
  });

  it("explains the max output tokens field maps to the provider-native cap", async () => {
    renderPage();
    const card = await waitFor(() => getCard());

    expect(
      within(card).getByLabelText(/max output tokens/i),
    ).toBeInTheDocument();
    expect(
      within(card).getByText(/num_predict/i),
    ).toBeInTheDocument();
    expect(within(card).getByText(/max_tokens/i)).toBeInTheDocument();
  });

  it("shows the server-reported context after a verified connection test", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", num_ctx: 16384 }),
    );
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: true,
      message: "Connected — model responded.",
      model: "llama3.1:8b",
      provider: "local_ollama",
      latency_ms: 12,
      error: null,
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: 131072,
      context_verified: true,
      context_warning: null,
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    expect(
      await within(card).findByTestId("server-context-verified"),
    ).toHaveTextContent(/server-reported context: 131072 tokens/i);
    expect(
      within(card).queryByTestId("server-context-warning"),
    ).toBeNull();
    // The current num_ctx edit is passed as a test override.
    expect(testLocalLlmConnectionMock.mock.calls[0][0].num_ctx).toBe(16384);
  });

  it("shows the context warning when the test cannot verify the context", async () => {
    const user = userEvent.setup();
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: true,
      message: "Connected — model responded.",
      model: "llama3.1:8b",
      provider: "local_openai_compatible",
      latency_ms: 12,
      error: null,
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: null,
      context_verified: false,
      context_warning:
        "An OpenAI-compatible endpoint does not expose its context window.",
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    expect(
      await within(card).findByTestId("server-context-warning"),
    ).toHaveTextContent(/does not expose its context window/i);
    expect(
      within(card).queryByTestId("server-context-verified"),
    ).toBeNull();
  });

  it("shows a static cannot-verify note for OpenAI-compatible endpoints", async () => {
    const user = userEvent.setup();
    renderPage();
    const card = await waitFor(() => getCard());

    // Default provider is openai_compatible: the note is visible pre-test.
    expect(
      within(card).getByTestId("openai-context-note"),
    ).toHaveTextContent(/cannot verify the server.s real context/i);

    await user.selectOptions(
      within(card).getByLabelText(/provider/i),
      "ollama",
    );
    expect(within(card).queryByTestId("openai-context-note")).toBeNull();
  });

  it("lists installed models and the picker updates the model field", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "llama3.1:8b" }),
    );
    listLocalLlmModelsMock.mockResolvedValue({
      provider: "local_ollama",
      ok: true,
      models: ["llama3.1:8b", "qwen2.5-coder:14b"],
      error: null,
      error_kind: null,
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /list installed models/i }),
    );

    const select = (await within(card).findByTestId(
      "installed-models-select",
    )) as HTMLSelectElement;
    expect(within(select).getByRole("option", { name: "qwen2.5-coder:14b" }))
      .toBeInTheDocument();

    // The override is passed so listing works on unsaved edits.
    expect(listLocalLlmModelsMock.mock.calls[0][0]).toMatchObject({
      provider: "ollama",
    });

    // Selecting a listed model updates the free-text model field.
    await user.selectOptions(select, "qwen2.5-coder:14b");
    expect(
      (within(card).getByLabelText(/model name/i) as HTMLInputElement).value,
    ).toBe("qwen2.5-coder:14b");
  });

  it("shows the unsupported model-listing state for OpenAI-compatible", async () => {
    const user = userEvent.setup();
    // Default provider is openai_compatible: a static unsupported note shows.
    renderPage();
    const card = await waitFor(() => getCard());
    expect(
      within(card).getByTestId("models-unsupported"),
    ).toHaveTextContent(/model listing is ollama-only/i);

    listLocalLlmModelsMock.mockResolvedValue({
      provider: "local_openai_compatible",
      ok: false,
      models: [],
      error: "Model listing is not supported for the OpenAI-compatible provider.",
      error_kind: "unsupported",
    });

    await user.click(
      within(card).getByRole("button", { name: /list installed models/i }),
    );

    expect(
      await within(card).findByTestId("models-error"),
    ).toHaveTextContent(/only available for the ollama provider/i);
    expect(within(card).queryByTestId("installed-models-select")).toBeNull();
  });

  it("renders a distinct model_not_installed connection failure", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "llama3.1:70b" }),
    );
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: false,
      message: "Connection failed.",
      model: "llama3.1:70b",
      provider: "local_ollama",
      latency_ms: null,
      error: 'Model "llama3.1:70b" is not installed on this Ollama server.',
      error_kind: "model_not_installed",
      installed_models: ["llama3.1:8b", "qwen2.5-coder:14b"],
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: null,
      context_verified: false,
      context_warning: null,
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    const result = await within(card).findByTestId("test-connection-result");
    expect(result).toHaveAttribute("data-error-kind", "model_not_installed");
    expect(result).toHaveTextContent(/is not installed on this ollama server/i);
    expect(result).toHaveTextContent(/llama3\.1:8b, qwen2\.5-coder:14b/i);

    // The installed models surface in the picker so the user can fix it.
    expect(
      within(card).getByTestId("installed-models-select"),
    ).toBeInTheDocument();
  });

  it("renders a distinct endpoint_unavailable connection failure", async () => {
    const user = userEvent.setup();
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: false,
      message: "Connection failed.",
      model: "llama3.1:8b",
      provider: "local_ollama",
      latency_ms: null,
      error: "Connection refused",
      error_kind: "endpoint_unavailable",
      installed_models: [],
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: null,
      context_verified: false,
      context_warning: null,
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    const result = await within(card).findByTestId("test-connection-result");
    expect(result).toHaveAttribute("data-error-kind", "endpoint_unavailable");
    expect(result).toHaveTextContent(/could not reach the server/i);
  });

  // ---- Explicit, confirmation-gated model pull (task 139) ----

  it("offers the Pull model control only for the Ollama provider", async () => {
    const user = userEvent.setup();
    // Default provider is openai_compatible: no pull control (Ollama-only).
    renderPage();
    const card = await waitFor(() => getCard());
    expect(within(card).queryByTestId("local-llm-pull")).toBeNull();
    expect(
      within(card).queryByRole("button", { name: /^pull model$/i }),
    ).toBeNull();

    await user.selectOptions(
      within(card).getByLabelText(/provider/i),
      "ollama",
    );
    expect(within(card).getByTestId("local-llm-pull")).toBeInTheDocument();
    expect(
      within(card).getByRole("button", { name: /^pull model$/i }),
    ).toBeInTheDocument();
  });

  it("does not pull without confirmation, and pulls after confirming", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "qwen2.5-coder:14b" }),
    );
    pullLocalLlmModelMock.mockResolvedValue(undefined);

    renderPage();
    const card = await waitFor(() => getCard());

    // First click only reveals the confirmation step — no request is sent.
    await user.click(
      within(card).getByRole("button", { name: /^pull model$/i }),
    );
    expect(within(card).getByTestId("pull-confirm")).toBeInTheDocument();
    expect(pullLocalLlmModelMock).not.toHaveBeenCalled();

    // Confirming sends exactly one request for the named model.
    await user.click(
      within(card).getByRole("button", { name: /confirm pull/i }),
    );
    await waitFor(() =>
      expect(pullLocalLlmModelMock).toHaveBeenCalledTimes(1),
    );
    expect(pullLocalLlmModelMock.mock.calls[0][0]).toMatchObject({
      model: "qwen2.5-coder:14b",
      provider: "ollama",
    });
  });

  it("cancelling the confirmation never sends a pull request", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "qwen2.5-coder:14b" }),
    );

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /^pull model$/i }),
    );
    await user.click(within(card).getByRole("button", { name: /cancel/i }));

    expect(within(card).queryByTestId("pull-confirm")).toBeNull();
    expect(pullLocalLlmModelMock).not.toHaveBeenCalled();
  });

  it("shows the disk/VRAM warning, progress, and a success terminal state", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "qwen2.5-coder:14b" }),
    );
    // After a successful pull the panel re-lists installed models.
    listLocalLlmModelsMock.mockResolvedValue({
      provider: "local_ollama",
      ok: true,
      models: ["qwen2.5-coder:14b"],
      error: null,
      error_kind: null,
    });
    pullLocalLlmModelMock.mockImplementation(
      async (
        _payload: unknown,
        onEvent: (event: {
          type: string;
          [key: string]: unknown;
        }) => void,
      ) => {
        onEvent({
          type: "advisory",
          model: "qwen2.5-coder:14b",
          provider: "local_ollama",
          message: "advisory",
        });
        onEvent({
          type: "progress",
          status: "downloading",
          completed: 50,
          total: 100,
          digest: "sha256:abc",
        });
        onEvent({ type: "result", ok: true, error: null, error_kind: null });
      },
    );

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /^pull model$/i }),
    );
    // The disk/VRAM-unknown warning is shown at the confirmation step.
    expect(
      within(card).getByTestId("pull-advisory-warning"),
    ).toHaveTextContent(/cannot verify whether this model will fit/i);

    await user.click(
      within(card).getByRole("button", { name: /confirm pull/i }),
    );

    // A progress/terminal state is rendered from the streamed events.
    expect(
      await within(card).findByTestId("pull-progress"),
    ).toHaveTextContent(/downloading/i);
    const result = await within(card).findByTestId("pull-result");
    expect(result).toHaveAttribute("data-pull-ok", "true");
    expect(result).toHaveTextContent(/now installed/i);
  });

  it("renders a pull failure terminal state", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "does-not-exist" }),
    );
    pullLocalLlmModelMock.mockImplementation(
      async (
        _payload: unknown,
        onEvent: (event: {
          type: string;
          [key: string]: unknown;
        }) => void,
      ) => {
        onEvent({
          type: "advisory",
          model: "does-not-exist",
          provider: "local_ollama",
          message: "advisory",
        });
        onEvent({
          type: "result",
          ok: false,
          error: "pull model manifest: file does not exist",
          error_kind: "unexpected",
        });
      },
    );

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /^pull model$/i }),
    );
    await user.click(
      within(card).getByRole("button", { name: /confirm pull/i }),
    );

    const result = await within(card).findByTestId("pull-result");
    expect(result).toHaveAttribute("data-pull-ok", "false");
    expect(result).toHaveTextContent(/file does not exist/i);
  });

  it("offers to pull the missing model after a model_not_installed diagnostic", async () => {
    const user = userEvent.setup();
    getLocalLlmSettingsMock.mockResolvedValue(
      defaultSettings({ provider: "ollama", model: "llama3.1:70b" }),
    );
    testLocalLlmConnectionMock.mockResolvedValue({
      ok: false,
      message: "Connection failed.",
      model: "llama3.1:70b",
      provider: "local_ollama",
      latency_ms: null,
      error: 'Model "llama3.1:70b" is not installed on this Ollama server.',
      error_kind: "model_not_installed",
      installed_models: ["llama3.1:8b"],
      context_window_tokens: 8192,
      max_input_tokens: 6500,
      server_reported_context_tokens: null,
      context_verified: false,
      context_warning: null,
    });

    renderPage();
    const card = await waitFor(() => getCard());

    await user.click(
      within(card).getByRole("button", { name: /test connection/i }),
    );

    // The diagnostic surfaces a direct "Pull <model>" affordance.
    const pullMissing = await within(card).findByTestId("pull-missing-model");
    expect(pullMissing).toHaveTextContent(/llama3\.1:70b/i);

    // It opens the same confirmation-gated flow — still no request yet.
    await user.click(pullMissing);
    expect(within(card).getByTestId("pull-confirm")).toBeInTheDocument();
    expect(pullLocalLlmModelMock).not.toHaveBeenCalled();
  });
});
