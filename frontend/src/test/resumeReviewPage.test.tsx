import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getResumeSuggestionsMock,
  acceptSuggestionMock,
  rejectSuggestionMock,
  reviseSuggestionMock,
  applyResumeSuggestionsMock,
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
    getResumeSuggestionsMock: vi.fn(),
    acceptSuggestionMock: vi.fn(),
    rejectSuggestionMock: vi.fn(),
    reviseSuggestionMock: vi.fn(),
    applyResumeSuggestionsMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getResumeSuggestions: getResumeSuggestionsMock,
  acceptSuggestion: acceptSuggestionMock,
  rejectSuggestion: rejectSuggestionMock,
  reviseSuggestion: reviseSuggestionMock,
  applyResumeSuggestions: applyResumeSuggestionsMock,
  ApiError: ApiErrorMock,
}));

import { ResumeReviewPage } from "../pages/ResumeReviewPage";
import type { ResumeSuggestion, ResumeSuggestions } from "../api/types";

function suggestion(overrides: Partial<ResumeSuggestion> = {}): ResumeSuggestion {
  return {
    id: "sug_001",
    section_id: "professional_summary",
    section_heading: "PROFESSIONAL SUMMARY",
    operation: "replace_section_text",
    current_text: "Old summary.",
    suggested_text: "Sharper summary.",
    reason: "Aligns with the role.",
    evidence_refs: [{ source: "master resume", quote: "Built systems." }],
    ats_keywords: ["distributed systems"],
    confidence: 0.86,
    risk: "low",
    status: "pending",
    revision_instruction: "",
    ...overrides,
  };
}

function payload(overrides: Partial<ResumeSuggestions> = {}): ResumeSuggestions {
  return {
    resume_version_id: "v1",
    target_company: "Acme",
    target_job_title: "ML Engineer",
    suggestions: [
      suggestion(),
      suggestion({
        id: "sug_002",
        section_id: "skills",
        section_heading: "SKILLS",
        operation: "add_skill",
        current_text: "",
        suggested_text: "Rust",
        reason: "Listed as preferred.",
        evidence_refs: [],
        ats_keywords: ["Rust"],
        risk: "medium",
      }),
    ],
    applied_at: null,
    has_working_resume: false,
    ...overrides,
  };
}

function renderReview() {
  return render(
    <MemoryRouter initialEntries={["/resume-versions/v1/review"]}>
      <Routes>
        <Route
          path="/resume-versions/:versionId/review"
          element={<ResumeReviewPage />}
        />
        <Route
          path="/resume-versions/:versionId"
          element={<div>draft stub</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ResumeReviewPage", () => {
  it("renders sections and suggestion cards with reason, evidence and ATS keywords", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    await screen.findByTestId("review-section-professional_summary");
    expect(
      screen.getByTestId("review-section-skills"),
    ).toBeInTheDocument();

    const card = screen.getByTestId("suggestion-card-sug_001");
    expect(within(card).getByText("Aligns with the role.")).toBeInTheDocument();
    expect(within(card).getByText(/Built systems\./)).toBeInTheDocument();
    expect(within(card).getByText("distributed systems")).toBeInTheDocument();
    expect(within(card).getByText("Sharper summary.")).toBeInTheDocument();
  });

  it("accept calls the API and marks the suggestion accepted", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    acceptSuggestionMock.mockResolvedValue(
      suggestion({ status: "accepted" }),
    );
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("accept-sug_001");
    await user.click(screen.getByTestId("accept-sug_001"));

    await waitFor(() =>
      expect(acceptSuggestionMock).toHaveBeenCalledWith("v1", "sug_001"),
    );
    expect(
      await screen.findByTestId("suggestion-status-sug_001"),
    ).toHaveTextContent("accepted");
    // Accepted card is visually marked.
    expect(screen.getByTestId("suggestion-card-sug_001").className).toContain(
      "suggestion-card-accepted",
    );
    expect(screen.getByTestId("accepted-count")).toHaveTextContent("1 accepted");
  });

  it("reject calls the API and marks the suggestion rejected", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    rejectSuggestionMock.mockResolvedValue(
      suggestion({ id: "sug_002", status: "rejected" }),
    );
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("reject-sug_002");
    await user.click(screen.getByTestId("reject-sug_002"));

    await waitFor(() =>
      expect(rejectSuggestionMock).toHaveBeenCalledWith("v1", "sug_002"),
    );
    expect(
      await screen.findByTestId("suggestion-status-sug_002"),
    ).toHaveTextContent("rejected");
  });

  it("shows a revise textarea and submits the instruction", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    reviseSuggestionMock.mockResolvedValue(
      suggestion({ status: "revised", revision_instruction: "More backend." }),
    );
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("revise-toggle-sug_001");
    await user.click(screen.getByTestId("revise-toggle-sug_001"));

    const textarea = await screen.findByTestId("revise-textarea-sug_001");
    await user.type(textarea, "More backend.");
    await user.click(screen.getByTestId("revise-submit-sug_001"));

    await waitFor(() =>
      expect(reviseSuggestionMock).toHaveBeenCalledWith(
        "v1",
        "sug_001",
        "More backend.",
      ),
    );
  });

  it("applies accepted suggestions and reports the result", async () => {
    getResumeSuggestionsMock
      .mockResolvedValueOnce(payload())
      .mockResolvedValueOnce(
        payload({ applied_at: "2026-06-09T10:00:00Z", has_working_resume: true }),
      );
    applyResumeSuggestionsMock.mockResolvedValue({
      resume_version_id: "v1",
      applied_at: "2026-06-09T10:00:00Z",
      accepted_count: 2,
      working_resume: { header: { name: "x" }, sections: [] },
    });
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("apply-suggestions");
    await user.click(screen.getByTestId("apply-suggestions"));

    await waitFor(() =>
      expect(applyResumeSuggestionsMock).toHaveBeenCalledWith("v1"),
    );
    expect(await screen.findByTestId("apply-message")).toHaveTextContent(
      "Applied 2 accepted suggestions",
    );
  });

  it("shows an empty state when the draft has no suggestions", async () => {
    getResumeSuggestionsMock.mockRejectedValue(
      new ApiErrorMock("not found", 404, null),
    );
    renderReview();

    expect(await screen.findByText(/no AI suggestions/i)).toBeInTheDocument();
  });
});
