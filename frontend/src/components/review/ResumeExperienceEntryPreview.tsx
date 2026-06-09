import type { StructuredResumeEntry } from "../../api/types";
import { ResumeBulletList } from "./ResumeBulletList";

interface ResumeExperienceEntryPreviewProps {
  entry: StructuredResumeEntry;
}

/**
 * One experience or education entry. Title/organization sit on the left with
 * the date right-aligned on the same baseline — the alignment a real resume
 * uses, not the stacked web-card look the old UI had.
 */
export function ResumeExperienceEntryPreview({
  entry,
}: ResumeExperienceEntryPreviewProps) {
  const primary = entry.title || entry.degree || "";
  const secondary = entry.organization || entry.institution || "";
  const place = [entry.subtitle, entry.location].filter(Boolean).join(" · ");

  return (
    <div className="doc-entry">
      <div className="doc-entry-row">
        <span className="doc-entry-primary">{primary}</span>
        {entry.dates ? <span className="doc-entry-dates">{entry.dates}</span> : null}
      </div>
      {secondary || place ? (
        <div className="doc-entry-row doc-entry-subrow">
          <span className="doc-entry-secondary">{secondary}</span>
          {place ? <span className="doc-entry-place">{place}</span> : null}
        </div>
      ) : null}
      {entry.bullets?.length ? <ResumeBulletList bullets={entry.bullets} /> : null}
    </div>
  );
}
