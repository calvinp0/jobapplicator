import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { listCaptures } from "../api";

interface NavItem {
  to: string;
  label: string;
}

const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Dashboard" },
  { to: "/jobs", label: "Jobs" },
  { to: "/applications", label: "Applications" },
  { to: "/captures", label: "Captures" },
  { to: "/runs", label: "Runs" },
];

const ADVANCED_NAV: NavItem[] = [
  { to: "/prompts", label: "Prompt harnesses" },
  { to: "/settings", label: "Settings" },
];

// Routes that benefit from the wider content shell (dashboards / data tables).
const WIDE_PATHS = ["/applications", "/runs", "/jobs", "/"];

function isWidePath(pathname: string): boolean {
  if (pathname === "/") return true;
  return WIDE_PATHS.some(
    (prefix) => prefix !== "/" && pathname.startsWith(prefix),
  );
}

export function Layout() {
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    listCaptures()
      .then((rows) => {
        if (cancelled) return;
        setPendingCount(rows.filter((c) => !c.user_confirmed).length);
      })
      .catch(() => {
        if (!cancelled) setPendingCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  function renderItem(item: NavItem) {
    const showBadge =
      item.to === "/captures" &&
      pendingCount !== null &&
      pendingCount > 0;
    return (
      <li key={item.to}>
        <NavLink
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            isActive ? "nav-link nav-link-active" : "nav-link"
          }
        >
          <span>{item.label}</span>
          {showBadge ? (
            <span
              className="nav-badge"
              aria-label={`${pendingCount} pending captures`}
            >
              {pendingCount}
            </span>
          ) : null}
        </NavLink>
      </li>
    );
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-mark" aria-hidden="true">
            jp
          </span>
          <div>
            <h1 className="sidebar-title">jobapply</h1>
            <p className="sidebar-subtitle">Application cockpit</p>
          </div>
        </div>
        <nav aria-label="Primary">
          <p className="nav-group-label">Workspace</p>
          <ul className="nav-list">{PRIMARY_NAV.map(renderItem)}</ul>
        </nav>
        <div className="sidebar-divider" role="presentation" />
        <nav aria-label="Configuration">
          <p className="nav-group-label">Configuration</p>
          <ul className="nav-list nav-list-advanced">
            {ADVANCED_NAV.map(renderItem)}
          </ul>
        </nav>
      </aside>
      <main className="content">
        <div
          className={
            isWidePath(location.pathname)
              ? "content-inner content-inner-wide"
              : "content-inner"
          }
        >
          <Outlet />
        </div>
      </main>
    </div>
  );
}
