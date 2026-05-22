import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { listCaptures } from "../api";

const NAV_ITEMS: { to: string; label: string }[] = [
  { to: "/captures", label: "Captures" },
  { to: "/jobs", label: "Jobs" },
  { to: "/runs", label: "Runs" },
  { to: "/applications", label: "Applications" },
  { to: "/settings", label: "Settings" },
];

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

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="sidebar-title">jobapply</h1>
        <nav>
          <ul className="nav-list">
            {NAV_ITEMS.map((item) => {
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
            })}
          </ul>
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
