import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS: { to: string; label: string }[] = [
  { to: "/captures", label: "Captures" },
  { to: "/jobs", label: "Jobs" },
  { to: "/runs", label: "Runs" },
  { to: "/applications", label: "Applications" },
  { to: "/settings", label: "Settings" },
];

export function Layout() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="sidebar-title">jobapply</h1>
        <nav>
          <ul className="nav-list">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    isActive ? "nav-link nav-link-active" : "nav-link"
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
