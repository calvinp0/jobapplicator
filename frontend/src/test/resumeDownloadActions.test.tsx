import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const {
  downloadRunResumeMock,
  downloadRunArtifactMock,
  exportRunMock,
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
    downloadRunResumeMock: vi.fn(),
    downloadRunArtifactMock: vi.fn(),
    exportRunMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  downloadRunResume: downloadRunResumeMock,
  downloadRunArtifact: downloadRunArtifactMock,
  exportRun: exportRunMock,
  ApiError: ApiErrorMock,
}));

import { ResumeDownloadActions } from "../components/ResumeDownloadActions";

describe("ResumeDownloadActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the DOCX download button", () => {
    render(<ResumeDownloadActions runId="run-1" />);
    expect(
      screen.getByRole("button", { name: /download docx/i }),
    ).toBeInTheDocument();
  });

  it("downloads the resume via the correct endpoint on click", async () => {
    const user = userEvent.setup();
    downloadRunResumeMock.mockResolvedValue(undefined);

    render(<ResumeDownloadActions runId="run-42" />);
    await user.click(screen.getByRole("button", { name: /download docx/i }));

    await waitFor(() =>
      expect(downloadRunResumeMock).toHaveBeenCalledWith("run-42"),
    );
  });

  it("shows an error when the artifact is missing", async () => {
    const user = userEvent.setup();
    downloadRunResumeMock.mockRejectedValue(
      new ApiErrorMock("nope", 404, { detail: "artifact not found" }),
    );

    render(<ResumeDownloadActions runId="run-1" />);
    await user.click(screen.getByRole("button", { name: /download docx/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /artifact not found/i,
    );
  });

  it("renders a Download Markdown action when enabled", async () => {
    const user = userEvent.setup();
    downloadRunArtifactMock.mockResolvedValue(undefined);

    render(<ResumeDownloadActions runId="run-1" showMarkdown />);
    const mdButton = screen.getByRole("button", {
      name: /download markdown/i,
    });
    await user.click(mdButton);

    await waitFor(() =>
      expect(downloadRunArtifactMock).toHaveBeenCalledWith(
        "run-1",
        "tailored_resume.md",
      ),
    );
  });

  it("shows the exported folder path after export", async () => {
    const user = userEvent.setup();
    exportRunMock.mockResolvedValue({
      ok: true,
      export_dir: "candidate_context/exports/2026-05-27__Acme__SDE__run1",
      files: [],
    });

    render(<ResumeDownloadActions runId="run-1" showExport />);
    await user.click(screen.getByRole("button", { name: /export to folder/i }));

    expect(
      await screen.findByText(
        /candidate_context\/exports\/2026-05-27__Acme__SDE__run1/,
      ),
    ).toBeInTheDocument();
    expect(exportRunMock).toHaveBeenCalledWith("run-1");
  });
});
