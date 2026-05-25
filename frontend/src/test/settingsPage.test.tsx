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
  return screen
    .getByRole("heading", { level: 3, name: /master resumes/i })
    .closest("section") as HTMLElement;
}

function getBankCard() {
  return screen
    .getByRole("heading", { level: 3, name: /evidence banks/i })
    .closest("section") as HTMLElement;
}

describe("SettingsPage", () => {
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
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders both cards with their headers and the canonical empty-state copy", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 3, name: /master resumes/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByRole("heading", { level: 3, name: /evidence banks/i }),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "No master resumes yet — add one to enable tailoring.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "No evidence banks yet — optional, but useful for grounded tailoring.",
      ),
    ).toBeInTheDocument();
  });

  it("hides both add forms by default and exposes only the reveal buttons", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /\+ add master resume/i }),
      ).toBeInTheDocument(),
    );

    expect(
      screen.getByRole("button", { name: /\+ add evidence bank/i }),
    ).toBeInTheDocument();

    // No form fields are in the DOM until the user opens the form.
    expect(screen.queryByLabelText(/^name$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/content/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^cancel$/i }),
    ).not.toBeInTheDocument();
  });

  it("reveals the master resume form when + Add master resume is clicked and only that form", async () => {
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

    const resumeCard = getResumeCard();
    expect(within(resumeCard).getByLabelText(/^name$/i)).toBeInTheDocument();
    expect(within(resumeCard).getByLabelText(/content/i)).toBeInTheDocument();
    expect(
      within(resumeCard).getByRole("button", { name: /^cancel$/i }),
    ).toBeInTheDocument();

    // Evidence bank card form remains hidden.
    const bankCard = getBankCard();
    expect(within(bankCard).queryByLabelText(/^name$/i)).not.toBeInTheDocument();
    expect(
      within(bankCard).getByRole("button", { name: /\+ add evidence bank/i }),
    ).toBeInTheDocument();
  });

  it("reveals the evidence bank form when + Add evidence bank is clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /\+ add evidence bank/i }),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add evidence bank/i }),
    );

    const bankCard = getBankCard();
    expect(within(bankCard).getByLabelText(/^name$/i)).toBeInTheDocument();
    expect(within(bankCard).getByLabelText(/content/i)).toBeInTheDocument();
  });

  it("collapses the form when Cancel is clicked", async () => {
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

    const resumeCard = getResumeCard();
    expect(within(resumeCard).getByLabelText(/^name$/i)).toBeInTheDocument();

    await user.click(
      within(resumeCard).getByRole("button", { name: /^cancel$/i }),
    );

    expect(within(resumeCard).queryByLabelText(/^name$/i)).not.toBeInTheDocument();
    expect(
      within(resumeCard).getByRole("button", { name: /\+ add master resume/i }),
    ).toBeInTheDocument();
  });

  it("creates a master resume, collapses the form, and shows the new row", async () => {
    const user = userEvent.setup();
    createMasterResumeMock.mockResolvedValue({
      id: "resume-1",
      name: "Calvin – Generalist",
      source_path: "candidate_context/resume.md",
      content_markdown: "# Calvin",
      created_at: "2026-05-22T10:00:00Z",
      updated_at: "2026-05-22T10:00:00Z",
    });

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText(/no master resumes yet/i),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const resumeCard = getResumeCard();
    const utils = within(resumeCard);

    await user.type(utils.getByLabelText(/^name$/i), "Calvin – Generalist");
    await user.type(
      utils.getByLabelText(/source path/i),
      "candidate_context/resume.md",
    );
    await user.type(utils.getByLabelText(/content/i), "# Calvin");

    await user.click(
      utils.getByRole("button", { name: /^add master resume$/i }),
    );

    await waitFor(() =>
      expect(createMasterResumeMock).toHaveBeenCalledWith({
        name: "Calvin – Generalist",
        source_path: "candidate_context/resume.md",
        content_markdown: "# Calvin",
      }),
    );

    // Form collapsed after success.
    await waitFor(() =>
      expect(
        within(resumeCard).queryByLabelText(/^name$/i),
      ).not.toBeInTheDocument(),
    );

    // New row appears, empty-state gone.
    expect(
      within(resumeCard).getByText("Calvin – Generalist"),
    ).toBeInTheDocument();
    expect(
      within(resumeCard).queryByText(/no master resumes yet/i),
    ).not.toBeInTheDocument();
    expect(
      within(resumeCard).getByRole("button", {
        name: /\+ add master resume/i,
      }),
    ).toBeInTheDocument();
  });

  it("creates an evidence bank, collapses the form, and shows the new row", async () => {
    const user = userEvent.setup();
    createEvidenceBankMock.mockResolvedValue({
      id: "bank-1",
      name: "Backend evidence",
      source_path: null,
      content_markdown: "# Evidence",
      created_at: "2026-05-22T11:00:00Z",
      updated_at: "2026-05-22T11:00:00Z",
    });

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText(/no evidence banks yet/i),
      ).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add evidence bank/i }),
    );

    const bankCard = getBankCard();
    const utils = within(bankCard);

    await user.type(utils.getByLabelText(/^name$/i), "Backend evidence");
    await user.type(utils.getByLabelText(/content/i), "# Evidence");

    await user.click(
      utils.getByRole("button", { name: /^add evidence bank$/i }),
    );

    await waitFor(() =>
      expect(createEvidenceBankMock).toHaveBeenCalledWith({
        name: "Backend evidence",
        source_path: null,
        content_markdown: "# Evidence",
      }),
    );

    await waitFor(() =>
      expect(
        within(bankCard).queryByLabelText(/^name$/i),
      ).not.toBeInTheDocument(),
    );

    expect(
      within(bankCard).getByText("Backend evidence"),
    ).toBeInTheDocument();
    expect(
      within(bankCard).queryByText(/no evidence banks yet/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces server validation errors on create and keeps the form open", async () => {
    const user = userEvent.setup();
    createMasterResumeMock.mockRejectedValue(
      new ApiErrorMock("Request failed", 422, {
        detail: [
          {
            loc: ["body", "name"],
            msg: "value cannot be blank",
            type: "value_error",
          },
        ],
      }),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/no master resumes yet/i)).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const resumeCard = getResumeCard();
    const utils = within(resumeCard);

    await user.type(utils.getByLabelText(/^name$/i), "Bad");
    await user.type(utils.getByLabelText(/content/i), "x");
    await user.click(
      utils.getByRole("button", { name: /^add master resume$/i }),
    );

    expect(
      await within(resumeCard).findByText(/value cannot be blank/i),
    ).toBeInTheDocument();
    // Form stays open so the user can correct the input.
    expect(within(resumeCard).getByLabelText(/^name$/i)).toBeInTheDocument();
  });

  it("shows a friendly fallback (never the raw request string) when an ApiError has no detail", async () => {
    const user = userEvent.setup();
    createMasterResumeMock.mockRejectedValue(
      new ApiErrorMock(
        "Request to /master-resumes failed with status 500",
        500,
        null,
      ),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/no master resumes yet/i)).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /\+ add master resume/i }),
    );

    const resumeCard = getResumeCard();
    const utils = within(resumeCard);

    await user.type(utils.getByLabelText(/^name$/i), "Bad");
    await user.type(utils.getByLabelText(/content/i), "x");
    await user.click(
      utils.getByRole("button", { name: /^add master resume$/i }),
    );

    expect(
      await within(resumeCard).findByText(/something went wrong/i),
    ).toBeInTheDocument();
    expect(
      within(resumeCard).queryByText(/request to/i),
    ).not.toBeInTheDocument();
  });
});
