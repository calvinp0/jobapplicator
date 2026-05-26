import type { ReactNode } from "react";

interface SettingsGroupProps {
  label: string;
  description?: ReactNode;
  children: ReactNode;
}

/**
 * Visually-labelled grouping wrapper used on the Settings page to cluster
 * related SectionCards (e.g. "Gmail integration", "Claude / LLM providers").
 * Provides a small section heading and helper text above the cards.
 */
export function SettingsGroup({
  label,
  description,
  children,
}: SettingsGroupProps) {
  return (
    <section className="settings-group" aria-label={label}>
      <header className="settings-group-header">
        <div className="settings-group-label">{label}</div>
        {description ? (
          <p className="settings-group-description">{description}</p>
        ) : null}
      </header>
      <div className="settings-group-body">{children}</div>
    </section>
  );
}
