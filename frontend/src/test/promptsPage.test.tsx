import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  listPromptHarnessesMock,
  getPromptHarnessMock,
  savePromptOverrideMock,
  deletePromptOverrideMock,
  validatePromptHarnessMock,
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
    listPromptHarnessesMock: vi.fn(),
    getPromptHarnessMock: vi.fn(),
    savePromptOverrideMock: vi.fn(),
    deletePromptOverrideMock: vi.fn(),
    validatePromptHarnessMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listPromptHarnesses: listPromptHarnessesMock,
  getPromptHarness: getPromptHarnessMock,
  savePromptOverride: savePromptOverrideMock,
  deletePromptOverride: deletePromptOverrideMock,
  validatePromptHarness: validatePromptHarnessMock,
  ApiError: ApiErrorMock,
}));

import { PromptsPage } from "../pages/PromptsPage";
import type { PromptHarnessDetail, PromptHarnessSummary } from "../api";

const TAILORING_SUMMARY: PromptHarnessSummary = {
  id: "resume_tailoring",
  label: "Resume Tailoring",
  description: "First-draft tailoring prompt.",
  default_path: "runtime_prompts/resume_tailoring.md",
  has_override: false,
  effective_source: "default",
  updated_at: null,
};

const REVISION_SUMMARY: PromptHarnessSummary = {
  id: "resume_revision",
  label: "Resume Revision",
  description: "Follow-up revision prompt.",
  default_path: "runtime_prompts/resume_revision.md",
  has_override: false,
  effective_source: "default",
  updated_at: null,
};

const DEFAULT_DETAIL: PromptHarnessDetail = {
  id: "resume_tailoring",
  label: "Resume Tailoring",
  description: "First-draft tailoring prompt.",
  default_path: "runtime_prompts/resume_tailoring.md",
  has_override: false,
  effective_source: "default",
  default_content: "# default body for tests",
  override_content: null,
  effective_content: "# default body for tests",
  effective_hash: "a".repeat(64),
  updated_at: null,
};

function defaultDetail(
  overrides: Partial<PromptHarnessDetail> = {},
): PromptHarnessDetail {
  return { ...DEFAULT_DETAIL, ...overrides };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PromptsPage />
    </MemoryRouter>,
  );
}

describe("PromptsPage", () => {
  beforeEach(() => {
    listPromptHarnessesMock.mockResolvedValue([TAILORING_SUMMARY, REVISION_SUMMARY]);
    getPromptHarnessMock.mockResolvedValue(defaultDetail());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lists prompt harnesses and shows the effective body for the first one", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Resume Tailoring")).toBeInTheDocument(),
    );
    expect(screen.getByText("Resume Revision")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("prompt-effective-source")).toHaveTextContent(
        /default/i,
      ),
    );
    expect(screen.getByTestId("prompt-effective-textarea")).toHaveValue(
      "# default body for tests",
    );
  });

  it("warns the operator that prompt changes can break output validation", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/break run output validation/i)).toBeInTheDocument(),
    );
  });

  it("creates an override from the default and switches the source", async () => {
    savePromptOverrideMock.mockResolvedValue(
      defaultDetail({
        has_override: true,
        effective_source: "override",
        override_content: "# default body for tests",
        effective_content: "# default body for tests",
      }),
    );

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("prompt-create-override")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByTestId("prompt-create-override"));

    await waitFor(() =>
      expect(savePromptOverrideMock).toHaveBeenCalledWith(
        "resume_tailoring",
        "# default body for tests",
      ),
    );
    expect(screen.getByTestId("prompt-effective-source")).toHaveTextContent(
      /override/i,
    );
    expect(screen.getByTestId("prompt-save-override")).toBeInTheDocument();
    expect(screen.getByTestId("prompt-restore-default")).toBeInTheDocument();
  });

  it("saves edited override content via the API", async () => {
    getPromptHarnessMock.mockResolvedValueOnce(
      defaultDetail({
        has_override: true,
        effective_source: "override",
        override_content: "# existing override",
        effective_content: "# existing override",
      }),
    );
    savePromptOverrideMock.mockResolvedValue(
      defaultDetail({
        has_override: true,
        effective_source: "override",
        override_content: "# existing override\nedited line",
        effective_content: "# existing override\nedited line",
      }),
    );

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("prompt-override-textarea")).toBeInTheDocument(),
    );

    const textarea = screen.getByTestId("prompt-override-textarea");
    await userEvent.click(textarea);
    await userEvent.keyboard("{End}\nedited line");

    await userEvent.click(screen.getByTestId("prompt-save-override"));

    await waitFor(() => expect(savePromptOverrideMock).toHaveBeenCalled());
    expect(savePromptOverrideMock.mock.calls[0][0]).toBe("resume_tailoring");
    expect(savePromptOverrideMock.mock.calls[0][1]).toContain("edited line");
  });

  it("restores the default by deleting the override", async () => {
    getPromptHarnessMock.mockResolvedValueOnce(
      defaultDetail({
        has_override: true,
        effective_source: "override",
        override_content: "# existing override",
        effective_content: "# existing override",
      }),
    );
    deletePromptOverrideMock.mockResolvedValue(defaultDetail());

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("prompt-restore-default")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByTestId("prompt-restore-default"));

    await waitFor(() =>
      expect(deletePromptOverrideMock).toHaveBeenCalledWith("resume_tailoring"),
    );
    expect(screen.getByTestId("prompt-effective-source")).toHaveTextContent(
      /default/i,
    );
  });

  it("renders validation warnings returned from the API", async () => {
    validatePromptHarnessMock.mockResolvedValue({
      valid: false,
      warnings: ["Prompt does not mention required element: 'claim_audit.md'"],
    });

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("prompt-validate")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("prompt-validate"));

    await waitFor(() =>
      expect(
        screen.getByTestId("prompt-validation-result"),
      ).toHaveTextContent(/claim_audit.md/),
    );
  });
});
