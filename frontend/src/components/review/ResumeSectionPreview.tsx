import type { PreviewSection } from "../../lib/reviewModel";
import { sectionDisplayParagraphs } from "../../lib/reviewModel";
import { ResumeExperienceEntryPreview } from "./ResumeExperienceEntryPreview";
import { ResumeBulletList } from "./ResumeBulletList";

interface ResumeSectionPreviewProps {
  section: PreviewSection;
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
 * One resume section rendered as part of the document page. The whole section
 * is a click target that opens its suggestions in the right panel; sections
 * carrying suggestions get a subtle change marker (the track-changes signal).
 */
export function ResumeSectionPreview({
  section,
  selected,
  onSelect,
}: ResumeSectionPreviewProps) {
  const { structured } = section;
  const hasChanges = section.changeState !== "none";

  return (
    <section
      className={[
        "doc-section",
        selected ? "doc-section-selected" : "",
        hasChanges ? `doc-section-change doc-section-${section.changeState}` : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid={`doc-section-${section.key}`}
      data-selected={selected ? "true" : "false"}
      onClick={() => onSelect(section.key)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(section.key);
        }
      }}
      aria-pressed={selected}
    >
      <div className="doc-section-heading-row">
        <h2 className="doc-section-heading">{section.heading}</h2>
        {hasChanges ? (
          <span
            className={`doc-change-flag doc-change-flag-${section.changeState}`}
            data-testid={`doc-change-${section.key}`}
          >
            {CHANGE_LABEL[section.changeState] ?? "Edit"}
            {section.suggestions.length > 1
              ? ` · ${section.suggestions.length}`
              : ""}
          </span>
        ) : null}
      </div>

      <SectionBody section={section} structured={structured} />
    </section>
  );
}

function SectionBody({
  section,
  structured,
}: {
  section: PreviewSection;
  structured: PreviewSection["structured"];
}) {
  // Skills: label/items groups laid out as a compact definition list.
  if (structured?.groups?.length) {
    return (
      <dl className="doc-skills">
        {structured.groups.map((group, idx) => (
          <div className="doc-skill-row" key={idx}>
            {group.label ? <dt>{group.label}</dt> : null}
            <dd>{group.items.join(", ")}</dd>
          </div>
        ))}
      </dl>
    );
  }

  // Experience / education entries.
  if (structured?.entries?.length) {
    return (
      <div className="doc-entries">
        {structured.entries.map((entry, idx) => (
          <ResumeExperienceEntryPreview key={idx} entry={entry} />
        ))}
      </div>
    );
  }

  // Publications / projects / awards: plain item lists.
  if (structured?.items?.length && !structured.paragraphs?.length) {
    return <ResumeBulletList bullets={structured.items} />;
  }

  // Summary / derived sections: paragraphs reflecting accepted text edits.
  const paragraphs = sectionDisplayParagraphs(section);
  if (paragraphs.length === 0) {
    return <p className="doc-paragraph doc-paragraph-empty">—</p>;
  }
  return (
    <>
      {paragraphs.map((para, idx) => (
        <p className="doc-paragraph" key={idx}>
          {para}
        </p>
      ))}
    </>
  );
}
