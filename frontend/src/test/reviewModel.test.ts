import { describe, expect, it } from "vitest";
import {
  buildPreviewDocument,
  estimateSectionLines,
  flattenDocumentBlocks,
  paginateBlocks,
  paginateDocument,
  paginateSections,
} from "../lib/reviewModel";
import type {
  ResumeSuggestion,
  ResumeSuggestions,
  StructuredResume,
} from "../api/types";

function suggestion(overrides: Partial<ResumeSuggestion> = {}): ResumeSuggestion {
  return {
    id: "sug",
    section_id: "professional_summary",
    section_heading: "PROFESSIONAL SUMMARY",
    operation: "replace_section_text",
    current_text: "Old.",
    suggested_text: "New.",
    reason: "Because.",
    evidence_refs: [],
    ats_keywords: [],
    confidence: 0.8,
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
    target_job_title: "Engineer",
    base_resume: null,
    working_resume: null,
    suggestions: [],
    applied_at: null,
    has_working_resume: false,
    ...overrides,
  };
}

const RESUME: StructuredResume = {
  header: { name: "Jane Candidate", contact_items: ["jane@example.com"] },
  sections: [
    { type: "summary", heading: "PROFESSIONAL SUMMARY", paragraphs: ["Summary."] },
    {
      type: "experience",
      heading: "WORK EXPERIENCE",
      entries: [
        {
          title: "Engineer",
          organization: "Acme",
          dates: "2020",
          bullets: ["Did a thing.", "Did another thing."],
        },
      ],
    },
    { type: "publications", heading: "PUBLICATIONS", items: ["A paper."] },
  ],
};

describe("buildPreviewDocument — suggestions never duplicate resume sections", () => {
  it("attaches work-experience suggestions to the canonical section even when their section_id is per-entry", () => {
    const data = payload({
      base_resume: RESUME,
      suggestions: [
        // Granular per-entry ids that do NOT match the section heading slug;
        // these previously leaked out as duplicate WORK EXPERIENCE sections.
        suggestion({
          id: "s1",
          section_id: "experience_0",
          section_heading: "WORK EXPERIENCE",
          operation: "rewrite_bullet",
        }),
        suggestion({
          id: "s2",
          section_id: "experience_0_bullet_1",
          section_heading: "WORK EXPERIENCE",
          operation: "rewrite_bullet",
        }),
      ],
    });

    const doc = buildPreviewDocument(data);

    const workSections = doc.sections.filter(
      (s) => s.heading === "WORK EXPERIENCE",
    );
    expect(workSections).toHaveLength(1);
    // Both suggestions land on the single canonical section as badges.
    expect(workSections[0].suggestions.map((s) => s.id)).toEqual(["s1", "s2"]);
    // No extra sections appear beyond the three canonical ones.
    expect(doc.sections).toHaveLength(3);
  });

  it("renders each canonical section exactly once", () => {
    const data = payload({
      base_resume: RESUME,
      suggestions: [suggestion({ id: "s1", section_heading: "PUBLICATIONS", section_id: "publications" })],
    });
    const doc = buildPreviewDocument(data);
    const headings = doc.sections.map((s) => s.heading);
    expect(headings).toEqual([
      "PROFESSIONAL SUMMARY",
      "WORK EXPERIENCE",
      "PUBLICATIONS",
    ]);
  });

  it("only mints a derived section for a suggestion targeting a heading the resume lacks", () => {
    const data = payload({
      base_resume: RESUME,
      suggestions: [
        suggestion({
          id: "new1",
          section_id: "certifications",
          section_heading: "CERTIFICATIONS",
          operation: "add_section",
        }),
      ],
    });
    const doc = buildPreviewDocument(data);
    expect(doc.sections.map((s) => s.heading)).toEqual([
      "PROFESSIONAL SUMMARY",
      "WORK EXPERIENCE",
      "PUBLICATIONS",
      "CERTIFICATIONS",
    ]);
  });

  it("derives sections purely from suggestions when there is no structured resume", () => {
    const data = payload({
      suggestions: [
        suggestion({ id: "s1", section_id: "summary", section_heading: "SUMMARY" }),
        suggestion({ id: "s2", section_id: "skills", section_heading: "SKILLS" }),
      ],
    });
    const doc = buildPreviewDocument(data);
    expect(doc.header).toBeNull();
    expect(doc.sections.map((s) => s.heading)).toEqual(["SUMMARY", "SKILLS"]);
  });
});

describe("paginateSections", () => {
  it("returns a single page for a short resume", () => {
    const doc = buildPreviewDocument(payload({ base_resume: RESUME }));
    expect(paginateSections(doc)).toHaveLength(1);
  });

  it("always returns at least one (empty) page", () => {
    const doc = buildPreviewDocument(payload());
    expect(paginateSections(doc)).toHaveLength(1);
    expect(paginateSections(doc)[0]).toEqual([]);
  });

  it("breaks a long resume into multiple pages without splitting a section", () => {
    const longResume: StructuredResume = {
      header: { name: "Jane Candidate" },
      sections: Array.from({ length: 6 }, (_, i) => ({
        type: "experience",
        heading: `ROLE ${i + 1}`,
        entries: [
          {
            title: `Engineer ${i}`,
            organization: "Acme",
            dates: "2020",
            bullets: ["a", "b", "c", "d", "e"],
          },
        ],
      })),
    };
    const doc = buildPreviewDocument(payload({ base_resume: longResume }));
    const pages = paginateSections(doc);
    expect(pages.length).toBeGreaterThanOrEqual(2);
    // Every section appears on exactly one page (no section split / dropped).
    const flat = pages.flat();
    expect(flat).toHaveLength(doc.sections.length);
  });

  it("estimates more lines for richer sections", () => {
    const doc = buildPreviewDocument(payload({ base_resume: RESUME }));
    const summary = doc.sections.find((s) => s.heading === "PROFESSIONAL SUMMARY")!;
    const work = doc.sections.find((s) => s.heading === "WORK EXPERIENCE")!;
    expect(estimateSectionLines(work)).toBeGreaterThan(
      estimateSectionLines(summary),
    );
  });
});

// A skills section then a long work-experience section: enough work content
// that it cannot all fit on page 1 alongside skills, forcing the work section
// to begin on page 1 and continue onto page 2 (true flow pagination).
const FLOW_RESUME: StructuredResume = {
  header: { name: "Jane Candidate", contact_items: ["jane@example.com"] },
  sections: [
    {
      type: "skills",
      heading: "SKILLS",
      groups: [
        { label: "Languages", items: ["Python", "Go"] },
        { label: "Cloud", items: ["AWS", "GCP"] },
      ],
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

describe("paginateDocument — block-level flow pagination", () => {
  it("lets a long section begin on page 1 and continue onto page 2", () => {
    const doc = buildPreviewDocument(payload({ base_resume: FLOW_RESUME }));
    const pages = paginateDocument(doc);
    expect(pages.length).toBeGreaterThanOrEqual(2);

    // WORK EXPERIENCE appears on page 1 (does NOT have to start on page 2)...
    const page1Headings = pages[0].slices.map((s) => s.heading);
    expect(page1Headings).toContain("WORK EXPERIENCE");
    // ...and continues onto page 2 as a continuation slice.
    const page2Work = pages[1].slices.find((s) => s.heading === "WORK EXPERIENCE");
    expect(page2Work).toBeDefined();
    expect(page2Work!.continued).toBe(true);
  });

  it("keeps content after SKILLS on page 1 when there is room", () => {
    const doc = buildPreviewDocument(payload({ base_resume: FLOW_RESUME }));
    const pages = paginateDocument(doc);
    const page1Headings = pages[0].slices.map((s) => s.heading);
    // SKILLS is fully on page 1 and is followed by more content on the page.
    expect(page1Headings[0]).toBe("SKILLS");
    expect(page1Headings.length).toBeGreaterThan(1);
  });

  it("owns the heading on the first slice only; continuations are flagged", () => {
    const doc = buildPreviewDocument(payload({ base_resume: FLOW_RESUME }));
    const pages = paginateDocument(doc);
    const workSlices = pages
      .flatMap((p) => p.slices)
      .filter((s) => s.heading === "WORK EXPERIENCE");
    expect(workSlices.length).toBeGreaterThanOrEqual(2);
    expect(workSlices[0].continued).toBe(false);
    expect(workSlices.slice(1).every((s) => s.continued)).toBe(true);
  });

  it("partitions content across pages without duplicating it", () => {
    const doc = buildPreviewDocument(payload({ base_resume: FLOW_RESUME }));
    const pages = paginateDocument(doc);
    // Every work entry appears exactly once across all pages/slices.
    const titles = pages
      .flatMap((p) => p.slices)
      .flatMap((s) => s.entries.map((e) => e.title));
    expect(titles).toHaveLength(8);
    expect(new Set(titles).size).toBe(8);
  });

  it("always yields at least one page, even for an empty document", () => {
    const doc = buildPreviewDocument(payload());
    const pages = paginateDocument(doc);
    expect(pages).toHaveLength(1);
    expect(pages[0].slices).toEqual([]);
  });

  it("flattens a section into ordered heading + content blocks", () => {
    const doc = buildPreviewDocument(payload({ base_resume: RESUME }));
    const blocks = flattenDocumentBlocks(doc);
    // Heading-first per section; the stream covers every section.
    expect(blocks[0]).toMatchObject({ sectionIndex: 0, kind: "heading" });
    const headings = blocks.filter((b) => b.kind === "heading");
    expect(headings).toHaveLength(doc.sections.length);
  });

  it("keeps a section heading with its first content block (no orphan heading)", () => {
    const doc = buildPreviewDocument(payload({ base_resume: FLOW_RESUME }));
    const blocks = flattenDocumentBlocks(doc);
    const pages = paginateBlocks(blocks, 6);
    for (const page of pages) {
      const last = page[page.length - 1];
      // A heading is never stranded as the final block of a page.
      expect(last.kind).not.toBe("heading");
    }
  });
});
