import type { StructuredResumeHeader } from "../../api/types";

interface ResumeHeaderPreviewProps {
  header: StructuredResumeHeader;
}

/** Centered document header: name, optional subtitle, and a contact line. */
export function ResumeHeaderPreview({ header }: ResumeHeaderPreviewProps) {
  const contact = (header.contact_items ?? []).filter(Boolean);
  return (
    <header className="doc-header">
      <h1 className="doc-name">{header.name}</h1>
      {header.subtitle ? (
        <p className="doc-subtitle">{header.subtitle}</p>
      ) : null}
      {contact.length > 0 ? (
        <p className="doc-contact">{contact.join("  •  ")}</p>
      ) : null}
    </header>
  );
}
