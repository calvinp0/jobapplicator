import type {
  ResumeSuggestion,
  ResumeSuggestions,
  StructuredResume,
  StructuredResumeEntry,
  StructuredResumeSection,
  StructuredResumeSkillGroup,
} from "../api/types";

/**
 * Section-level change state, used to render the track-changes indicator in
 * the document preview. ``mixed`` means a section carries suggestions in more
 * than one state (e.g. one accepted, one still pending).
 */
export type ChangeState =
  | "none"
  | "pending"
  | "accepted"
  | "rejected"
  | "mixed";

/**
 * One section of the resume document as the workspace renders it. Combines the
 * structured content (when the backend exposed a ``base_resume``) with the AI
 * suggestions mapped onto that section. When no structured resume is available
 * the section is derived purely from its suggestions and ``structured`` is null.
 */
export interface PreviewSection {
  /** Stable selection key — the suggestion section_id or a slug of the heading. */
  key: string;
  heading: string;
  type: string;
  structured: StructuredResumeSection | null;
  suggestions: ResumeSuggestion[];
  changeState: ChangeState;
}

export interface PreviewDocument {
  header: StructuredResume["header"] | null;
  sections: PreviewSection[];
}

/** Normalize a heading/section id into a comparable, URL-safe key. */
export function slugifySection(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function suggestionKey(suggestion: ResumeSuggestion): string {
  return (
    suggestion.section_id ||
    slugifySection(suggestion.section_heading) ||
    "section"
  );
}

/**
 * The keys a suggestion can be matched to a structured section by — its
 * ``section_id`` and its ``section_heading``, both slugified. Matching on the
 * heading as well as the id is what stops work-experience suggestions (whose
 * ``section_id`` is often per-entry, e.g. ``experience_0``) from failing to
 * match the canonical ``WORK EXPERIENCE`` section and being re-rendered as a
 * duplicate appended section.
 */
function suggestionMatchKeys(suggestion: ResumeSuggestion): string[] {
  return [
    slugifySection(suggestion.section_id),
    slugifySection(suggestion.section_heading),
  ].filter(Boolean);
}

function changeStateFor(suggestions: ResumeSuggestion[]): ChangeState {
  if (suggestions.length === 0) return "none";
  const statuses = new Set(suggestions.map((s) => s.status));
  // A section with only rejected suggestions reads as untouched-but-reviewed;
  // anything still pending or accepted is the more meaningful signal.
  if (statuses.has("accepted") && (statuses.has("pending") || statuses.has("revised")))
    return "mixed";
  if (statuses.has("pending") || statuses.has("revised")) return "pending";
  if (statuses.has("accepted")) return "accepted";
  return "rejected";
}

/** Candidate keys a structured section can be matched against. */
function structuredSectionKeys(section: StructuredResumeSection): Set<string> {
  return new Set(
    [slugifySection(section.heading), slugifySection(section.type)].filter(
      Boolean,
    ),
  );
}

/**
 * Build the document model the preview renders. Prefers the applied
 * ``working_resume`` over the ``base_resume`` so the page reflects the latest
 * committed state, then overlays each suggestion onto the canonical section it
 * targets, matched by ``section_id`` or ``section_heading``.
 *
 * The resume is rendered exactly once: when a structured resume exists, every
 * suggestion attaches to one of its sections and is shown as a badge/highlight
 * there — suggestions never become extra document sections. A derived section
 * is minted only for a suggestion that targets a heading the structured resume
 * does not contain (a genuinely new section), or when there is no structured
 * resume at all. This is what prevents the previously-seen duplicate
 * ``WORK EXPERIENCE`` blocks at the bottom of the page.
 */
export function buildPreviewDocument(data: ResumeSuggestions): PreviewDocument {
  const structured = data.working_resume ?? data.base_resume ?? null;

  // Orphan suggestions (no matching structured section) grouped by a stable
  // key, preserving discovery order, so they remain reviewable on their own.
  const orphanGroups = new Map<string, ResumeSuggestion[]>();
  const orphanOrder: string[] = [];
  function addOrphan(suggestion: ResumeSuggestion) {
    const key = suggestionKey(suggestion);
    if (!orphanGroups.has(key)) {
      orphanGroups.set(key, []);
      orphanOrder.push(key);
    }
    orphanGroups.get(key)!.push(suggestion);
  }

  function derivedSection(key: string): PreviewSection {
    const suggestions = orphanGroups.get(key) ?? [];
    return {
      key,
      heading: suggestions[0]?.section_heading || key,
      type: suggestions[0]?.section_id || "other",
      structured: null,
      suggestions,
      changeState: changeStateFor(suggestions),
    };
  }

  if (structured?.sections?.length) {
    // Map every candidate key of every structured section to its index, so a
    // suggestion can be attached by either id or heading.
    const keyToIndex = new Map<string, number>();
    structured.sections.forEach((section, idx) => {
      for (const key of structuredSectionKeys(section)) {
        if (!keyToIndex.has(key)) keyToIndex.set(key, idx);
      }
    });

    const perSection: ResumeSuggestion[][] = structured.sections.map(() => []);
    for (const suggestion of data.suggestions) {
      let matched = -1;
      for (const key of suggestionMatchKeys(suggestion)) {
        const idx = keyToIndex.get(key);
        if (idx !== undefined) {
          matched = idx;
          break;
        }
      }
      if (matched >= 0) perSection[matched].push(suggestion);
      else addOrphan(suggestion);
    }

    const sections: PreviewSection[] = structured.sections.map(
      (section, idx) => {
        const suggestions = perSection[idx];
        return {
          key:
            slugifySection(section.heading) || slugifySection(section.type),
          heading: section.heading,
          type: section.type,
          structured: section,
          suggestions,
          changeState: changeStateFor(suggestions),
        };
      },
    );

    // Append derived sections only for suggestions targeting a section the
    // resume does not already contain — never duplicating an existing heading.
    for (const key of orphanOrder) sections.push(derivedSection(key));

    return { header: structured.header ?? null, sections };
  }

  // No structured resume: derive every section purely from its suggestions.
  for (const suggestion of data.suggestions) addOrphan(suggestion);
  const sections = orphanOrder.map((key) => derivedSection(key));
  return { header: null, sections };
}

/**
 * The paragraphs to render for a summary/other section, reflecting any
 * accepted ``replace_section_text`` suggestion so the preview updates live on
 * accept. Falls back to the structured paragraphs, then to the suggestions'
 * current text. Used for sections without richer structured content.
 */
export function sectionDisplayParagraphs(section: PreviewSection): string[] {
  const accepted = section.suggestions.find(
    (s) => s.operation === "replace_section_text" && s.status === "accepted",
  );
  if (accepted && accepted.suggested_text) {
    return splitParagraphs(accepted.suggested_text);
  }
  if (section.structured?.paragraphs?.length) {
    return section.structured.paragraphs;
  }
  if (section.structured?.items?.length) {
    return section.structured.items;
  }
  // Derived (no structured content): show the current text of each suggestion,
  // or its suggested text when there is no "before".
  const lines = section.suggestions
    .map((s) => s.current_text || s.suggested_text)
    .filter(Boolean);
  return lines.length > 0 ? lines : [];
}

function splitParagraphs(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

// ---- Estimated pagination ---------------------------------------------------
// We don't run real Word layout; instead we estimate how many text lines each
// section occupies and break to a new page once a page's budget is exceeded.
// This gives visible Page 1 / Page 2 boundaries without measuring the DOM. The
// constants are tuned to the document type size in the preview (see styles.css).

/** Roughly how many resume lines fit on one rendered page. */
const LINES_PER_PAGE = 46;
/** Lines the centered header consumes on page 1. */
const HEADER_LINES = 6;
/** Characters of body text that wrap onto one rendered line. The page is now
 *  wider (see the document column / .doc-page in styles.css), so more text
 *  fits per line and pages pack more densely. */
const CHARS_PER_LINE = 120;

function paragraphLines(paragraphs: string[]): number {
  return paragraphs.reduce(
    (sum, p) => sum + Math.max(1, Math.ceil(p.length / CHARS_PER_LINE)),
    0,
  );
}

/** Estimate how many rendered lines a section occupies, heading included. */
export function estimateSectionLines(section: PreviewSection): number {
  // Heading row + its rule + trailing gap.
  let lines = 3;
  const s = section.structured;

  if (s?.groups?.length) {
    lines += s.groups.reduce(
      (sum, g) =>
        sum + Math.max(1, Math.ceil((g.items.join(", ").length || 1) / CHARS_PER_LINE)),
      0,
    );
  } else if (s?.entries?.length) {
    for (const entry of s.entries) {
      // Title row, optional org/place subrow, then bullets.
      lines += 2;
      lines += paragraphLines(entry.bullets ?? []);
    }
  } else if (s?.items?.length) {
    lines += paragraphLines(s.items);
  } else {
    lines += paragraphLines(sectionDisplayParagraphs(section));
  }

  return lines;
}

/**
 * Split the document's sections into estimated pages. A section is never
 * broken across a page — it moves whole to the next page when it would
 * overflow the current one — so the result is always at least one page (an
 * empty document yields a single empty page so the preview still renders a
 * sheet). The first page reserves room for the document header.
 */
export function paginateSections(document: PreviewDocument): PreviewSection[][] {
  const pages: PreviewSection[][] = [];
  let current: PreviewSection[] = [];
  let used = document.header ? HEADER_LINES : 0;

  for (const section of document.sections) {
    const cost = estimateSectionLines(section);
    if (current.length > 0 && used + cost > LINES_PER_PAGE) {
      pages.push(current);
      current = [];
      used = 0;
    }
    current.push(section);
    used += cost;
  }

  if (current.length > 0 || pages.length === 0) pages.push(current);
  return pages;
}

// ---- Flow (block-level) pagination -----------------------------------------
// The section-level paginator above keeps a whole section on one page, which
// leaves large blank areas (e.g. WORK EXPERIENCE bumped entirely to page 2).
// The flow paginator instead breaks each section into granular render blocks —
// heading, paragraph, skill row, experience/education entry, list item — and
// fills each page block-by-block, letting a section start near the bottom of a
// page and continue onto the next, the way a real Word/Docs resume flows.

/** A single renderable unit of the document, tagged with its source section. */
export interface FlowBlock {
  sectionIndex: number;
  kind: "heading" | "paragraph" | "skill-group" | "entry" | "item";
  lines: number;
  paragraph?: string;
  group?: StructuredResumeSkillGroup;
  entry?: StructuredResumeEntry;
  item?: string;
}

/** A run of one section's content placed on a single page. A section that
 *  spans pages yields one slice per page; ``continued`` marks the slices whose
 *  heading already appeared on an earlier page so the renderer can show a
 *  subtle continuation label instead of repeating the section unnaturally. */
export interface SectionSlice {
  key: string;
  heading: string;
  section: PreviewSection;
  continued: boolean;
  paragraphs: string[];
  groups: StructuredResumeSkillGroup[];
  entries: StructuredResumeEntry[];
  items: string[];
}

/** One rendered page: an optional document header followed by section slices. */
export interface DocumentPage {
  hasHeader: boolean;
  slices: SectionSlice[];
}

function lineCost(length: number): number {
  return Math.max(1, Math.ceil((length || 1) / CHARS_PER_LINE));
}

function entryLines(entry: StructuredResumeEntry): number {
  // Title row + optional org/place subrow, then one block of bullets.
  return 2 + paragraphLines(entry.bullets ?? []);
}

/**
 * Flatten a section into ordered render blocks, mirroring the body-type
 * precedence the section renderer uses (skills → entries → items → paragraphs)
 * so the paginated output matches what is drawn on the page.
 */
function flattenSection(
  section: PreviewSection,
  sectionIndex: number,
): FlowBlock[] {
  const blocks: FlowBlock[] = [
    { sectionIndex, kind: "heading", lines: 3 },
  ];
  const s = section.structured;

  if (s?.groups?.length) {
    for (const group of s.groups) {
      blocks.push({
        sectionIndex,
        kind: "skill-group",
        lines: lineCost(group.items.join(", ").length),
        group,
      });
    }
  } else if (s?.entries?.length) {
    for (const entry of s.entries) {
      blocks.push({
        sectionIndex,
        kind: "entry",
        lines: entryLines(entry),
        entry,
      });
    }
  } else if (s?.items?.length && !s.paragraphs?.length) {
    for (const item of s.items) {
      blocks.push({
        sectionIndex,
        kind: "item",
        lines: lineCost(item.length),
        item,
      });
    }
  } else {
    for (const paragraph of sectionDisplayParagraphs(section)) {
      blocks.push({
        sectionIndex,
        kind: "paragraph",
        lines: lineCost(paragraph.length),
        paragraph,
      });
    }
  }

  return blocks;
}

/** Flatten every section of the document into a single ordered block stream. */
export function flattenDocumentBlocks(document: PreviewDocument): FlowBlock[] {
  return document.sections.flatMap((section, idx) =>
    flattenSection(section, idx),
  );
}

/**
 * Pack the block stream into pages by accumulating line cost until the page
 * budget is exceeded, then starting a new page. A section heading is kept with
 * the first content block of its section so a heading never strands alone at
 * the foot of a page. ``headerLines`` reserves room for the document header on
 * the first page.
 */
export function paginateBlocks(
  blocks: FlowBlock[],
  headerLines = 0,
): FlowBlock[][] {
  const pages: FlowBlock[][] = [];
  let current: FlowBlock[] = [];
  let used = headerLines;

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    // Couple a heading with the first content block of the same section so the
    // pair moves together rather than orphaning the heading.
    let need = block.lines;
    if (
      block.kind === "heading" &&
      blocks[i + 1]?.sectionIndex === block.sectionIndex
    ) {
      need += blocks[i + 1].lines;
    }

    if (current.length > 0 && used + need > LINES_PER_PAGE) {
      pages.push(current);
      current = [];
      used = 0;
    }

    current.push(block);
    used += block.lines;
  }

  if (current.length > 0 || pages.length === 0) pages.push(current);
  return pages;
}

/**
 * The document as a list of rendered pages, each carrying section slices. A
 * section whose blocks span a page boundary appears as a slice on each page it
 * touches; only the first slice owns the real heading, the rest are flagged
 * ``continued``. No block is ever duplicated — the slices partition the blocks.
 */
export function paginateDocument(document: PreviewDocument): DocumentPage[] {
  const blocks = flattenDocumentBlocks(document);
  const headerLines = document.header ? HEADER_LINES : 0;
  const blockPages = paginateBlocks(blocks, headerLines);
  const headingSeen = new Set<number>();

  return blockPages.map((pageBlocks, pageIndex) => {
    const slices: SectionSlice[] = [];
    let currentIndex = -1;
    let slice: SectionSlice | null = null;

    for (const block of pageBlocks) {
      if (block.sectionIndex !== currentIndex || slice === null) {
        currentIndex = block.sectionIndex;
        const section = document.sections[currentIndex];
        slice = {
          key: section.key,
          heading: section.heading,
          section,
          // Continued when this section's heading already rendered earlier and
          // this run starts with content rather than the heading itself.
          continued:
            headingSeen.has(currentIndex) && block.kind !== "heading",
          paragraphs: [],
          groups: [],
          entries: [],
          items: [],
        };
        slices.push(slice);
      }

      switch (block.kind) {
        case "heading":
          headingSeen.add(currentIndex);
          break;
        case "paragraph":
          if (block.paragraph !== undefined)
            slice.paragraphs.push(block.paragraph);
          break;
        case "skill-group":
          if (block.group) slice.groups.push(block.group);
          break;
        case "entry":
          if (block.entry) slice.entries.push(block.entry);
          break;
        case "item":
          if (block.item) slice.items.push(block.item);
          break;
      }
    }

    return {
      hasHeader: pageIndex === 0 && Boolean(document.header),
      slices,
    };
  });
}
