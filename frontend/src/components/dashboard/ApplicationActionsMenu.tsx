import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ActiveJobAction } from "../../lib/dashboardJobs";

interface ApplicationActionsMenuProps {
  actions: ActiveJobAction[];
  /** Accessible label for the trigger, e.g. the job title. */
  label?: string;
}

/**
 * Overflow ("⋯") menu holding a card's secondary actions so the card row
 * never shows more than the single primary button. Closes on outside click,
 * Escape, or item selection.
 */
export function ApplicationActionsMenu({
  actions,
  label,
}: ApplicationActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (actions.length === 0) return null;

  return (
    <div className="app-actions-menu" ref={ref}>
      <button
        type="button"
        className="app-actions-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label ? `More actions for ${label}` : "More actions"}
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {open ? (
        <ul className="app-actions-list" role="menu">
          {actions.map((action) => (
            <li key={action.href} role="none">
              <Link
                to={action.href}
                role="menuitem"
                className="app-actions-item"
                onClick={() => setOpen(false)}
              >
                {action.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
