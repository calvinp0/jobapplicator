import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { listCaptures } from "../api";
import { SidebarActivityCenter } from "../components/activity/SidebarActivityCenter";

interface NavItem {
  to: string;
  label: string;
  hint?: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

// Track / Create / Configure follow the redesign brief; only routes that
// actually exist in App.tsx are listed (no dead links).
const TRACK_GROUP: NavGroup = {
  label: "Track",
  items: [
    { to: "/", label: "Dashboard", hint: "Overview" },
    { to: "/jobs", label: "Jobs", hint: "Confirmed roles" },
    { to: "/applications", label: "Applications", hint: "Status + email" },
  ],
};

const CREATE_GROUP: NavGroup = {
  label: "Create",
  items: [{ to: "/runs", label: "Runs", hint: "Tailoring runs" }],
};

// Captures are no longer a primary workflow surface (task 117). The browser
// extension still ingests them and the route stays live, but the nav link
// only appears — demoted under its own "Inbox" section — when there is
// something pending to review. Otherwise pending captures surface through
// the bottom-left activity center.
const CAPTURES_ITEM: NavItem = {
  to: "/captures",
  label: "Capture inbox",
  hint: "Needs review",
};

const CONFIGURE_GROUP: NavGroup = {
  label: "Configure",
  items: [
    { to: "/prompts", label: "Prompt harnesses" },
    { to: "/settings", label: "Settings" },
  ],
};

// Routes that benefit from the wider content shell (dashboards / data tables).
const WIDE_PATHS = ["/applications", "/runs", "/jobs", "/"];

function isWidePath(pathname: string): boolean {
  if (pathname === "/") return true;
  // The resume review workspace is a full three-panel surface that needs the
  // wide shell even though its base route is not in WIDE_PATHS.
  if (pathname.endsWith("/review")) return true;
  return WIDE_PATHS.some(
    (prefix) => prefix !== "/" && pathname.startsWith(prefix),
  );
}

/**
 * The content shell width class for a route. The resume review workspace gets
 * an extra-wide shell so its three columns (rail · document · review panel)
 * have room and the document sheet reads at full width instead of floating in
 * empty gutters; other wide routes use the standard wide shell.
 */
/**
 * The content shell class for a route. The resume review workspace needs the
 * content area to NOT establish its own scroll container: its right-hand AI
 * review panel is `position: sticky` and must pin against the window scroll.
 * An `overflow: auto/hidden/scroll` ancestor would capture the sticky context
 * and silently break pinning, so the review route opts into `overflow: visible`
 * via `.content-review`.
 */
function contentClass(pathname: string): string {
  return pathname.endsWith("/review") ? "content content-review" : "content";
}

function contentInnerClass(pathname: string): string {
  if (pathname.endsWith("/review")) {
    return "content-inner content-inner-wide content-inner-review";
  }
  return isWidePath(pathname)
    ? "content-inner content-inner-wide"
    : "content-inner";
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
          <span className="nav-link-body">
            <span className="nav-link-label">{item.label}</span>
            {item.hint ? (
              <span className="nav-link-hint">{item.hint}</span>
            ) : null}
          </span>
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

  function renderGroup(group: NavGroup) {
    return (
      <div className="nav-group" key={group.label}>
        <p className="nav-group-label">{group.label}</p>
        <ul className="nav-list">{group.items.map(renderItem)}</ul>
      </div>
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

        <nav aria-label="Primary" className="sidebar-nav">
          {renderGroup(TRACK_GROUP)}
          {renderGroup(CREATE_GROUP)}
          {pendingCount !== null && pendingCount > 0
            ? renderGroup({ label: "Inbox", items: [CAPTURES_ITEM] })
            : null}
        </nav>

        <div className="sidebar-divider" role="presentation" />

        <nav aria-label="Configuration" className="sidebar-nav">
          {renderGroup(CONFIGURE_GROUP)}
        </nav>

        <SidebarActivityCenter />
      </aside>
      <main className={contentClass(location.pathname)}>
        <div className={contentInnerClass(location.pathname)}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
