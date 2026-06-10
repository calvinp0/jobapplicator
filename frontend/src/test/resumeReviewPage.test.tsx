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
  getRunMock,
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
    getRunMock: vi.fn(
      (): Promise<any> =>
        Promise.resolve({ id: "run-1", provider_summary: null }),
    ),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getResumeSuggestions: getResumeSuggestionsMock,
  getResumeVersion: vi.fn(() =>
    Promise.resolve({ claude_run_id: "run-1", docx_path: "x" }),
  ),
  getRun: getRunMock,
  acceptSuggestion: acceptSuggestionMock,
  rejectSuggestion: rejectSuggestionMock,
  reviseSuggestion: reviseSuggestionMock,
  applyResumeSuggestions: applyResumeSuggestionsMock,
  downloadRunResume: vi.fn(() => Promise.resolve()),
  downloadRunArtifact: vi.fn(() => Promise.resolve()),
  exportRun: vi.fn(() =>
    Promise.resolve({ ok: true, export_dir: "", files: [] }),
  ),
  ApiError: ApiErrorMock,
}));

import { ResumeReviewPage } from "../pages/ResumeReviewPage";
import type {
  ResumeSuggestion,
  ResumeSuggestions,
  StructuredResume,
} from "../api/types";

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

const BASE_RESUME: StructuredResume = {
  header: { name: "Jane Candidate", contact_items: ["jane@example.com"] },
  sections: [
    {
      type: "summary",
      heading: "PROFESSIONAL SUMMARY",
      paragraphs: ["Old summary."],
    },
    {
      type: "skills",
      heading: "SKILLS",
      groups: [{ label: "Languages", items: ["Python"] }],
    },
    {
      type: "education",
      heading: "EDUCATION",
      entries: [{ institution: "State University", degree: "BSc", dates: "2018" }],
    },
  ],
};

function payload(overrides: Partial<ResumeSuggestions> = {}): ResumeSuggestions {
  return {
    resume_version_id: "v1",
    target_company: "Acme",
    target_job_title: "ML Engineer",
    base_resume: BASE_RESUME,
    working_resume: null,
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

describe("ResumeReviewPage workspace (task 114)", () => {
  it("renders the three-panel workspace: rail, document preview and review panel", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    expect(await screen.findByTestId("review-workspace")).toBeInTheDocument();
    // Center document preview with the resume page + header.
    expect(screen.getByTestId("resume-document-preview")).toBeInTheDocument();
    expect(screen.getByTestId("resume-page")).toBeInTheDocument();
    expect(screen.getByText("Jane Candidate")).toBeInTheDocument();
    // Left workflow rail with all five steps.
    expect(screen.getByTestId("workflow-step-1")).toHaveTextContent("Job");
    expect(screen.getByTestId("workflow-step-4")).toHaveTextContent("Review");
    expect(screen.getByTestId("workflow-step-5")).toHaveTextContent("Export");
    // Right AI review panel.
    expect(screen.getByTestId("review-panel")).toBeInTheDocument();
  });

  it("shows a compact provider provenance strip from the originating run (task 129)", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    getRunMock.mockResolvedValue({
      id: "run-1",
      provider_summary: {
        label: "Preflight: Ollama · Tailoring: Claude Code · DOCX: Backend",
        providers_used: ["ollama", "claude_code", "backend"],
        has_warnings: false,
      },
    });
    renderReview();

    const strip = await screen.findByTestId("review-provenance");
    expect(strip).toHaveTextContent("Generated with:");
    expect(strip).toHaveTextContent(
      "Preflight: Ollama · Tailoring: Claude Code · DOCX: Backend",
    );
  });

  it("omits the provenance strip when the run has no provider summary", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    getRunMock.mockResolvedValue({ id: "run-1", provider_summary: null });
    renderReview();

    await screen.findByTestId("review-workspace");
    expect(screen.queryByTestId("review-provenance")).not.toBeInTheDocument();
  });

  it("renders the resume sections in the document preview", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    await screen.findByTestId("resume-document-preview");
    expect(screen.getByTestId("doc-section-professional_summary")).toBeInTheDocument();
    expect(screen.getByTestId("doc-section-skills")).toBeInTheDocument();
    expect(screen.getByTestId("doc-section-education")).toBeInTheDocument();
  });

  it("shows the selected section's previous and suggested text in the review panel", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    // The summary section is selected by default (first with suggestions).
    // The default selection is applied by an effect that commits one render
    // after the panel first appears, so wait for the card rather than querying
    // synchronously (which races the selection effect under full-suite load).
    const panel = await screen.findByTestId("review-panel");
    const card = await within(panel).findByTestId("suggestion-card-sug_001");
    expect(within(card).getByText("Old summary.")).toBeInTheDocument(); // previous
    expect(within(card).getByText("Sharper summary.")).toBeInTheDocument(); // suggested
    expect(within(card).getByText("Aligns with the role.")).toBeInTheDocument();
    expect(within(card).getByText("distributed systems")).toBeInTheDocument();
  });

  it("clicking a section opens its suggestions in the review panel", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("doc-section-skills");
    await user.click(screen.getByTestId("doc-section-skills"));

    const panel = screen.getByTestId("review-panel");
    expect(await within(panel).findByTestId("suggestion-card-sug_002")).toBeInTheDocument();
    // The panel title names the selected section.
    expect(within(panel).getByText("Listed as preferred.")).toBeInTheDocument();
  });

  it("accept calls the API and marks the suggestion accepted", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    acceptSuggestionMock.mockResolvedValue(suggestion({ status: "accepted" }));
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
    expect(screen.getByTestId("accepted-count")).toHaveTextContent("1 accepted");
  });

  it("reject calls the API and marks the suggestion rejected", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    rejectSuggestionMock.mockResolvedValue(
      suggestion({
        id: "sug_002",
        section_id: "skills",
        section_heading: "SKILLS",
        operation: "add_skill",
        current_text: "",
        suggested_text: "Rust",
        status: "rejected",
      }),
    );
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("doc-section-skills");
    await user.click(screen.getByTestId("doc-section-skills"));
    await user.click(await screen.findByTestId("reject-sug_002"));

    await waitFor(() =>
      expect(rejectSuggestionMock).toHaveBeenCalledWith("v1", "sug_002"),
    );
    expect(
      await screen.findByTestId("suggestion-status-sug_002"),
    ).toHaveTextContent("rejected");
  });

  it("shows a useful empty state for a section without suggestions", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    const user = userEvent.setup();
    renderReview();

    await screen.findByTestId("doc-section-education");
    await user.click(screen.getByTestId("doc-section-education"));

    const panel = screen.getByTestId("review-panel");
    expect(
      await within(panel).findByText(/No AI suggestions available/i),
    ).toBeInTheDocument();
  });

  it("shows a page-level empty state when the draft has no suggestions at all", async () => {
    getResumeSuggestionsMock.mockRejectedValue(
      new ApiErrorMock("not found", 404, null),
    );
    renderReview();

    expect(await screen.findByText(/no AI suggestions/i)).toBeInTheDocument();
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

  it("renders the document as labeled pages (Page 1)", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    await screen.findByTestId("resume-document-preview");
    expect(screen.getByTestId("page-label-1")).toHaveTextContent("Page 1");
    expect(screen.getByTestId("doc-page-block-1")).toBeInTheDocument();
  });

  it("paginates a long resume into a second page", async () => {
    const longResume: StructuredResume = {
      header: { name: "Jane Candidate", contact_items: ["jane@example.com"] },
      sections: Array.from({ length: 6 }, (_, i) => ({
        type: "experience",
        heading: `ROLE ${i + 1}`,
        entries: [
          {
            title: `Engineer ${i}`,
            organization: "Acme",
            dates: "2020",
            bullets: ["alpha", "beta", "gamma", "delta", "epsilon"],
          },
        ],
      })),
    };
    getResumeSuggestionsMock.mockResolvedValue(
      payload({ base_resume: longResume, suggestions: [] }),
    );
    renderReview();

    await screen.findByTestId("resume-document-preview");
    expect(screen.getByTestId("doc-page-block-2")).toBeInTheDocument();
    expect(screen.getByTestId("page-label-2")).toHaveTextContent("Page 2");
  });

  it("renders one WORK EXPERIENCE heading even when many suggestions target it", async () => {
    const resume: StructuredResume = {
      header: { name: "Jane Candidate" },
      sections: [
        {
          type: "experience",
          heading: "WORK EXPERIENCE",
          entries: [
            { title: "Engineer", organization: "Acme", dates: "2020", bullets: ["Did things."] },
          ],
        },
        { type: "publications", heading: "PUBLICATIONS", items: ["A paper."] },
      ],
    };
    getResumeSuggestionsMock.mockResolvedValue(
      payload({
        base_resume: resume,
        suggestions: [
          suggestion({
            id: "w1",
            section_id: "experience_0",
            section_heading: "WORK EXPERIENCE",
            operation: "rewrite_bullet",
          }),
          suggestion({
            id: "w2",
            section_id: "experience_0_bullet_1",
            section_heading: "WORK EXPERIENCE",
            operation: "rewrite_bullet",
          }),
        ],
      }),
    );
    renderReview();

    const preview = await screen.findByTestId("resume-document-preview");
    // The canonical heading appears exactly once in the document — suggestions
    // did not leak out as appended duplicate sections after Publications.
    // (Scoped to the document; the heading also names the selected section in
    // the right-hand review panel, which is expected.)
    const headings = within(preview).getAllByText("WORK EXPERIENCE");
    expect(headings).toHaveLength(1);
    // Exactly one work-experience section element exists in the document.
    expect(screen.getByTestId("doc-section-work_experience")).toBeInTheDocument();
    // Its suggestion badge reflects both edits.
    const badge = screen.getByTestId("doc-change-work_experience");
    expect(badge).toHaveTextContent("Suggested edit");
    expect(badge).toHaveTextContent("2");
  });

  it("renders three columns: rail, document and the sticky review column", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    const workspace = await screen.findByTestId("review-workspace");
    // Left rail, center document, and the right review column wrapper.
    expect(within(workspace).getByLabelText("Tailoring workflow")).toBeInTheDocument();
    expect(within(workspace).getByTestId("resume-document-preview")).toBeInTheDocument();
    const column = within(workspace).getByTestId("review-panel-column");
    expect(column).toBeInTheDocument();
    // The sticky wrapper holds the panel (sticky lives on the column in CSS).
    expect(within(column).getByTestId("review-panel")).toBeInTheDocument();
  });

  it("keeps the AI review panel sticky (on the column) and internally scrollable", async () => {
    getResumeSuggestionsMock.mockResolvedValue(payload());
    renderReview();

    // Sticky is applied to the column wrapper; the panel body scrolls internally.
    const column = await screen.findByTestId("review-panel-column");
    expect(column.className).toContain("review-panel-column");
    const panel = within(column).getByTestId("review-panel");
    expect(panel.className).toContain("review-panel");
    expect(panel.querySelector(".review-panel-body")).not.toBeNull();
  });

  it("flows a long section across pages with a single continuation heading", async () => {
    const flowResume: StructuredResume = {
      header: { name: "Jane Candidate", contact_items: ["jane@example.com"] },
      sections: [
        {
          type: "skills",
          heading: "SKILLS",
          groups: [{ label: "Languages", items: ["Python", "Go"] }],
        },
        {
          type: "experience",
          heading: "WORK EXPERIENCE",
          entries: Array.from({ length: 8 }, (_, i) => ({
            title: `Engineer ${i + 1}`,
            organization: "Acme",
            dates: "2020",
            bullets: ["alpha", "beta", "gamma", "delta"],
          })),
        },
      ],
    };
    getResumeSuggestionsMock.mockResolvedValue(
      payload({ base_resume: flowResume, suggestions: [] }),
    );
    renderReview();

    const preview = await screen.findByTestId("resume-document-preview");
    // The section spilled onto a second page.
    expect(screen.getByTestId("doc-page-block-2")).toBeInTheDocument();
    // The real WORK EXPERIENCE heading renders exactly once; the continuation
    // is a "(continued)" label, not a duplicated section.
    const headings = within(preview).getAllByText("WORK EXPERIENCE", {
      exact: true,
    });
    expect(headings).toHaveLength(1);
    expect(within(preview).getByText(/\(continued\)/)).toBeInTheDocument();
    // The continuation slice is a distinct element, not a duplicate testid.
    expect(
      screen.getByTestId("doc-section-work_experience"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("doc-section-work_experience-cont"),
    ).toBeInTheDocument();
    // No work entry is duplicated: 8 distinct engineer titles total.
    const titles = within(preview)
      .getAllByText(/^Engineer \d+$/)
      .map((el) => el.textContent);
    expect(new Set(titles).size).toBe(8);
    expect(titles).toHaveLength(8);
  });

  it("keeps long status/risk text inside overflow-guarded badge containers", async () => {
    getResumeSuggestionsMock.mockResolvedValue(
      payload({
        suggestions: [
          suggestion({
            risk: "extremely-high-risk-with-a-very-long-descriptor-string",
            ats_keywords: [
              "a-very-long-ats-keyword-phrase-that-could-overflow-a-narrow-chip",
            ],
          }),
        ],
      }),
    );
    renderReview();

    const panel = await screen.findByTestId("review-panel");
    // Status badge: constrained by the .status-badge overflow guard in CSS.
    const status = within(panel).getByTestId("suggestion-status-sug_001");
    expect(status.className).toContain("status-badge");
    // Risk pill renders the long descriptor but stays within its container.
    const risk = within(panel).getByText(/extremely-high-risk-with-a-very-long/);
    expect(risk.className).toContain("suggestion-risk");
    // Long keyword chip is present and carries the clamped chip class.
    const chip = within(panel).getByText(/a-very-long-ats-keyword-phrase/);
    expect(chip.className).toContain("suggestion-keyword-chip");
  });
});
