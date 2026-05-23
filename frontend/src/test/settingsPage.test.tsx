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
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listMasterResumes: listMasterResumesMock,
  listEvidenceBanks: listEvidenceBanksMock,
  createMasterResume: createMasterResumeMock,
  createEvidenceBank: createEvidenceBankMock,
  listCaptures: listCapturesMock,
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

describe("SettingsPage", () => {
  beforeEach(() => {
    listMasterResumesMock.mockResolvedValue([]);
    listEvidenceBanksMock.mockResolvedValue([]);
    listCapturesMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("creates a master resume and shows it in the list", async () => {
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
      expect(screen.getByText(/no master resumes yet/i)).toBeInTheDocument(),
    );

    const resumeSection = screen
      .getByRole("heading", { level: 3, name: /master resumes/i })
      .closest("section") as HTMLElement;
    const utils = within(resumeSection);

    await user.type(utils.getByLabelText(/^name$/i), "Calvin – Generalist");
    await user.type(
      utils.getByLabelText(/source path/i),
      "candidate_context/resume.md",
    );
    await user.type(utils.getByLabelText(/content/i), "# Calvin");

    await user.click(
      utils.getByRole("button", { name: /add master resume/i }),
    );

    await waitFor(() =>
      expect(createMasterResumeMock).toHaveBeenCalledWith({
        name: "Calvin – Generalist",
        source_path: "candidate_context/resume.md",
        content_markdown: "# Calvin",
      }),
    );

    expect(
      await within(resumeSection).findByText("Calvin – Generalist"),
    ).toBeInTheDocument();
    expect(
      within(resumeSection).queryByText(/no master resumes yet/i),
    ).not.toBeInTheDocument();
    expect(
      (utils.getByLabelText(/^name$/i) as HTMLInputElement).value,
    ).toBe("");
  });

  it("creates an evidence bank and shows it in the list", async () => {
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
      expect(screen.getByText(/no evidence banks yet/i)).toBeInTheDocument(),
    );

    const bankSection = screen
      .getByRole("heading", { level: 3, name: /evidence banks/i })
      .closest("section") as HTMLElement;
    const utils = within(bankSection);

    await user.type(utils.getByLabelText(/^name$/i), "Backend evidence");
    await user.type(utils.getByLabelText(/content/i), "# Evidence");

    await user.click(
      utils.getByRole("button", { name: /add evidence bank/i }),
    );

    await waitFor(() =>
      expect(createEvidenceBankMock).toHaveBeenCalledWith({
        name: "Backend evidence",
        source_path: null,
        content_markdown: "# Evidence",
      }),
    );

    expect(
      await within(bankSection).findByText("Backend evidence"),
    ).toBeInTheDocument();
    expect(
      within(bankSection).queryByText(/no evidence banks yet/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces server validation errors on create", async () => {
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

    const resumeSection = screen
      .getByRole("heading", { level: 3, name: /master resumes/i })
      .closest("section") as HTMLElement;
    const utils = within(resumeSection);

    await user.type(utils.getByLabelText(/^name$/i), "Bad");
    await user.type(utils.getByLabelText(/content/i), "x");
    await user.click(
      utils.getByRole("button", { name: /add master resume/i }),
    );

    expect(
      await within(resumeSection).findByText(/value cannot be blank/i),
    ).toBeInTheDocument();
  });
});
