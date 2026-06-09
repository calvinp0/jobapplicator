import type { SectionSlice } from "../../lib/reviewModel";
import { ResumeExperienceEntryPreview } from "./ResumeExperienceEntryPreview";
import { ResumeBulletList } from "./ResumeBulletList";

interface ResumeSectionSliceProps {
  slice: SectionSlice;
  selected: boolean;
  onSelect: (key: string) => void;
}

const CHANGE_LABEL: Record<string, string> = {
  pending: "Suggested edit",
  accepted: "Accepted",
  rejected: "Reviewed",
  mixed: "In review",
};

/**
 * One page slice of a resume section. With flow pagination a section may span
 * several pages, so each page renders the portion of the section that landed on
 * it. The first slice carries the real heading and the AI change marker; any
 * continuation slice shows a subtle "(continued)" heading so the section reads
 * naturally across the page break without duplicating its content.
 *
 * The whole slice remains a click target that opens the section's suggestions
 * in the right panel, exactly like the previous single-block section preview.
 */
export function ResumeSectionSlice({
  slice,
  selected,
  onSelect,
}: ResumeSectionSliceProps) {
  const { section, continued } = slice;
  const hasChanges = section.changeState !== "none";

  return (
    <section
      className={[
        "doc-section",
        continued ? "doc-section-continued" : "",
        selected ? "doc-section-selected" : "",
        hasChanges ? `doc-section-change doc-section-${section.changeState}` : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid={
        continued ? `doc-section-${slice.key}-cont` : `doc-section-${slice.key}`
      }
      data-section-key={slice.key}
      data-selected={selected ? "true" : "false"}
      onClick={() => onSelect(slice.key)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(slice.key);
        }
      }}
      aria-pressed={selected}
    >
      <div className="doc-section-heading-row">
        <h2 className="doc-section-heading">
          {continued ? `${slice.heading} (continued)` : slice.heading}
        </h2>
        {hasChanges && !continued ? (
          <span
            className={`doc-change-flag doc-change-flag-${section.changeState}`}
            data-testid={`doc-change-${slice.key}`}
          >
            {CHANGE_LABEL[section.changeState] ?? "Edit"}
            {section.suggestions.length > 1
              ? ` · ${section.suggestions.length}`
              : ""}
          </span>
        ) : null}
      </div>

      <SliceBody slice={slice} />
    </section>
  );
}

function SliceBody({ slice }: { slice: SectionSlice }) {
  // Skills: label/items groups laid out as a compact definition list.
  if (slice.groups.length > 0) {
    return (
      <dl className="doc-skills">
        {slice.groups.map((group, idx) => (
          <div className="doc-skill-row" key={idx}>
            {group.label ? <dt>{group.label}</dt> : null}
            <dd>{group.items.join(", ")}</dd>
          </div>
        ))}
      </dl>
    );
  }

  // Experience / education entries.
  if (slice.entries.length > 0) {
    return (
      <div className="doc-entries">
        {slice.entries.map((entry, idx) => (
          <ResumeExperienceEntryPreview key={idx} entry={entry} />
        ))}
      </div>
    );
  }

  // Publications / projects / awards: plain item lists.
  if (slice.items.length > 0) {
    return <ResumeBulletList bullets={slice.items} />;
  }

  // Summary / derived sections: paragraphs reflecting accepted text edits.
  if (slice.paragraphs.length === 0) {
    return <p className="doc-paragraph doc-paragraph-empty">—</p>;
  }
  return (
    <>
      {slice.paragraphs.map((para, idx) => (
        <p className="doc-paragraph" key={idx}>
          {para}
        </p>
      ))}
    </>
  );
}
