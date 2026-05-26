import type { ReactNode } from "react";

interface ToolbarProps {
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
}

/**
 * Horizontal action strip used at the top of dashboard pages. Holds primary
 * actions, filter chips, and inline status hints in a consistent surface.
 */
export function Toolbar({
  children,
  className,
  ...rest
}: ToolbarProps) {
  const classes = ["ui-toolbar"];
  if (className) classes.push(className);
  return (
    <div
      role="toolbar"
      aria-label={rest["aria-label"] ?? "Page toolbar"}
      className={classes.join(" ")}
    >
      {children}
    </div>
  );
}

interface ToolbarGroupProps {
  children: ReactNode;
  align?: "start" | "end";
}

export function ToolbarGroup({
  children,
  align = "start",
}: ToolbarGroupProps) {
  return (
    <div className={`ui-toolbar-group ui-toolbar-group-${align}`}>
      {children}
    </div>
  );
}

interface FilterChipsProps<T extends string> {
  value: T;
  options: ReadonlyArray<{ id: T; label: string; count?: number }>;
  onChange: (next: T) => void;
  ariaLabel?: string;
}

/**
 * Pill-style filter row. Each chip mirrors the look of `applications-filter`
 * but lives in a shared component so other dashboards can reuse it.
 */
export function FilterChips<T extends string>({
  value,
  options,
  onChange,
  ariaLabel = "Filter",
}: FilterChipsProps<T>) {
  return (
    <div className="ui-filter-chips" role="toolbar" aria-label={ariaLabel}>
      {options.map((opt) => {
        const active = opt.id === value;
        return (
          <button
            key={opt.id}
            type="button"
            className={`ui-filter-chip${active ? " ui-filter-chip-active" : ""}`}
            aria-pressed={active}
            aria-label={opt.label}
            onClick={() => onChange(opt.id)}
          >
            <span>{opt.label}</span>
            {typeof opt.count === "number" ? (
              <span className="ui-filter-chip-count" aria-hidden="true">
                {opt.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
