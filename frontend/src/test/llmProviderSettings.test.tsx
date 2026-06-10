import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  listMasterResumesMock,
  listEvidenceSourcesMock,
  createMasterResumeMock,
  createEvidenceBankMock,
  getLlmProviderSettingMock,
  setLlmProviderSettingMock,
  getGmailStatusMock,
  getGmailAuthUrlMock,
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
    getLlmProviderSettingMock: vi.fn(),
    setLlmProviderSettingMock: vi.fn(),
    getGmailStatusMock: vi.fn(),
    getGmailAuthUrlMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listMasterResumes: listMasterResumesMock,
  listEvidenceSources: listEvidenceSourcesMock,
  createMasterResume: createMasterResumeMock,
  createEvidenceBank: createEvidenceBankMock,
  importMasterResumeFile: vi.fn(),
  importEvidenceSourceFile: vi.fn(),
  resetLocalData: vi.fn(),
  getLlmProviderSetting: getLlmProviderSettingMock,
  setLlmProviderSetting: setLlmProviderSettingMock,
  getGmailStatus: getGmailStatusMock,
  getGmailAuthUrl: getGmailAuthUrlMock,
  getExportSettings: vi.fn(() =>
    Promise.resolve({ path: "candidate_context/exports" }),
  ),
  getLocalLlmSettings: vi.fn(() =>
    Promise.resolve({
      enabled: false,
      provider: "openai_compatible",
      base_url: "http://localhost:11434/v1",
      model: "llama3.1:8b",
      timeout_seconds: 60,
      allowed_tasks: {},
      has_api_key: false,
      api_key_preview: "",
      updated_at: null,
      task_policy: [],
    }),
  ),
  setLocalLlmSettings: vi.fn(),
  testLocalLlmConnection: vi.fn(),
  ApiError: ApiErrorMock,
}));

import { SettingsPage } from "../pages/SettingsPage";

const THREE_PROVIDERS = [
  {
    id: "claude_code",
    display_name: "Claude Code",
    default_binary: "claude",
    binary_env_var: "JOBAPPLY_CLAUDE_BINARY",
  },
  {
    id: "codex",
    display_name: "Codex CLI",
    default_binary: "codex",
    binary_env_var: "JOBAPPLY_CODEX_BINARY",
  },
  {
    id: "gemini",
    display_name: "Gemini CLI",
    default_binary: "gemini",
    binary_env_var: "JOBAPPLY_GEMINI_BINARY",
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

function getProviderCard() {
  return screen
    .getByRole("heading", { level: 3, name: /tailoring llm/i })
    .closest("section") as HTMLElement;
}

describe("SettingsPage – Tailoring LLM card", () => {
  beforeEach(() => {
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceSourcesMock.mockResolvedValue([]);
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the providers returned by the API and marks the persisted default as selected", async () => {
    getLlmProviderSettingMock.mockResolvedValue({
      default_provider: "codex",
      available: THREE_PROVIDERS,
    });

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /tailoring llm/i }),
      ).toBeInTheDocument(),
    );

    const card = getProviderCard();
    const select = await within(card).findByLabelText(/default provider/i);

    // All three options rendered with display name and id.
    const options = within(select as HTMLElement).getAllByRole("option");
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveTextContent("Claude Code (claude_code)");
    expect(options[1]).toHaveTextContent("Codex CLI (codex)");
    expect(options[2]).toHaveTextContent("Gemini CLI (gemini)");

    // The persisted default is the selected value.
    expect((select as HTMLSelectElement).value).toBe("codex");
  });

  it("PUTs the chosen provider id when Save is clicked", async () => {
    const user = userEvent.setup();
    getLlmProviderSettingMock.mockResolvedValue({
      default_provider: "claude_code",
      available: THREE_PROVIDERS,
    });
    setLlmProviderSettingMock.mockResolvedValue({
      default_provider: "gemini",
      available: THREE_PROVIDERS,
    });

    renderPage();

    const card = getProviderCard();
    const select = (await within(card).findByLabelText(
      /default provider/i,
    )) as HTMLSelectElement;

    await user.selectOptions(select, "gemini");
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(setLlmProviderSettingMock).toHaveBeenCalledWith("gemini"),
    );

    expect(
      await within(card).findByText(/saved\./i),
    ).toBeInTheDocument();
    // After save, the dropdown reflects the new persisted value.
    expect(select.value).toBe("gemini");
  });

  it("disables Save until the selection differs from the persisted value", async () => {
    const user = userEvent.setup();
    getLlmProviderSettingMock.mockResolvedValue({
      default_provider: "claude_code",
      available: THREE_PROVIDERS,
    });

    renderPage();

    const card = getProviderCard();
    const select = (await within(card).findByLabelText(
      /default provider/i,
    )) as HTMLSelectElement;
    const saveButton = within(card).getByRole("button", { name: /^save$/i });

    expect(saveButton).toBeDisabled();

    await user.selectOptions(select, "codex");
    expect(saveButton).toBeEnabled();
  });

  it("surfaces a server error when the PUT fails and does not show success", async () => {
    const user = userEvent.setup();
    getLlmProviderSettingMock.mockResolvedValue({
      default_provider: "claude_code",
      available: THREE_PROVIDERS,
    });
    setLlmProviderSettingMock.mockRejectedValue(
      new ApiErrorMock("Request failed", 400, {
        detail: "unknown llm provider: gemini",
      }),
    );

    renderPage();

    const card = getProviderCard();
    const select = (await within(card).findByLabelText(
      /default provider/i,
    )) as HTMLSelectElement;

    await user.selectOptions(select, "gemini");
    await user.click(within(card).getByRole("button", { name: /^save$/i }));

    expect(
      await within(card).findByText(/unknown llm provider: gemini/i),
    ).toBeInTheDocument();
    expect(within(card).queryByText(/saved\./i)).not.toBeInTheDocument();
  });

  it("shows a load error when the GET endpoint fails", async () => {
    getLlmProviderSettingMock.mockRejectedValue(
      new ApiErrorMock("Request failed", 500, null),
    );

    renderPage();

    const card = await waitFor(() => getProviderCard());
    expect(
      await within(card).findByText(/something went wrong/i),
    ).toBeInTheDocument();
    // The form is not rendered when load fails.
    expect(
      within(card).queryByLabelText(/default provider/i),
    ).not.toBeInTheDocument();
  });
});
