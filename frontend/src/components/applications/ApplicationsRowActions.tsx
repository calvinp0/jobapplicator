import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type {
  ApplicationMutationKey,
  ApplicationRowActions,
} from "../../lib/applicationActions";

interface ApplicationsRowActionsProps {
  actions: ApplicationRowActions;
  /** Accessible label for the triggers, e.g. the application title. */
  label: string;
  /** Disables the mutation menu items while a request is in flight. */
  pending?: boolean;
  onMutate: (key: ApplicationMutationKey) => void;
}

/**
 * Row action cluster for the applications table: exactly one primary action
 * button followed by an overflow ("⋯") menu holding every secondary action.
 * The menu mixes navigation links and status-mutation buttons, and closes on
 * outside click, Escape, or item selection — mirroring the dashboard's
 * ApplicationActionsMenu but with mutation support.
 */
export function ApplicationsRowActions({
  actions,
  label,
  pending = false,
  onMutate,
}: ApplicationsRowActionsProps) {
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

  const { primary, secondary } = actions;

  return (
    <div className="applications-row-actions">
      <Link
        to={primary.href}
        className="ui-button ui-button-primary ui-button-sm applications-primary-action"
        aria-label={`${primary.label} — ${label}`}
      >
        {primary.label}
      </Link>
      {secondary.length > 0 ? (
        <div className="app-actions-menu" ref={ref}>
          <button
            type="button"
            className="app-actions-trigger"
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={`More actions for ${label}`}
            onClick={() => setOpen((value) => !value)}
          >
            <span aria-hidden="true">⋯</span>
          </button>
          {open ? (
            <ul className="app-actions-list" role="menu">
              {secondary.map((action) => (
                <li key={`${action.kind}:${action.key}`} role="none">
                  {action.kind === "link" ? (
                    <Link
                      to={action.href}
                      role="menuitem"
                      className="app-actions-item"
                      onClick={() => setOpen(false)}
                    >
                      {action.label}
                    </Link>
                  ) : (
                    <button
                      type="button"
                      role="menuitem"
                      className="app-actions-item app-actions-item-button"
                      disabled={pending}
                      onClick={() => {
                        setOpen(false);
                        onMutate(action.key);
                      }}
                    >
                      {action.label}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
