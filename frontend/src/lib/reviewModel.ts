import type {
  ResumeSuggestion,
  ResumeSuggestions,
  StructuredResume,
  StructuredResumeSection,
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
 * committed state, then overlays each suggestion onto the section it targets.
 * Suggestions that don't map to any structured section (or when no structured
 * resume exists at all) become their own derived sections so they stay
 * reviewable.
 */
export function buildPreviewDocument(data: ResumeSuggestions): PreviewDocument {
  const structured = data.working_resume ?? data.base_resume ?? null;

  const byKey = new Map<string, ResumeSuggestion[]>();
  const order: string[] = [];
  for (const suggestion of data.suggestions) {
    const key = suggestionKey(suggestion);
    if (!byKey.has(key)) {
      byKey.set(key, []);
      order.push(key);
    }
    byKey.get(key)!.push(suggestion);
  }

  const sections: PreviewSection[] = [];
  const consumed = new Set<string>();

  if (structured?.sections?.length) {
    for (const section of structured.sections) {
      const candidates = structuredSectionKeys(section);
      // Find every suggestion group whose key matches this section.
      const matchedKeys = order.filter((k) => candidates.has(k));
      matchedKeys.forEach((k) => consumed.add(k));
      const suggestions = matchedKeys.flatMap((k) => byKey.get(k) ?? []);
      const key = slugifySection(section.heading) || slugifySection(section.type);
      sections.push({
        key,
        heading: section.heading,
        type: section.type,
        structured: section,
        suggestions,
        changeState: changeStateFor(suggestions),
      });
    }
  }

  // Suggestions with no matching structured section (or no structured resume)
  // are appended as derived sections, preserving discovery order.
  for (const key of order) {
    if (consumed.has(key)) continue;
    const suggestions = byKey.get(key) ?? [];
    sections.push({
      key,
      heading: suggestions[0]?.section_heading || key,
      type: suggestions[0]?.section_id || "other",
      structured: null,
      suggestions,
      changeState: changeStateFor(suggestions),
    });
  }

  return { header: structured?.header ?? null, sections };
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
