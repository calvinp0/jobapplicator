import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../api", () => ({
  listCaptures: vi.fn().mockResolvedValue([]),
}));

import { Layout } from "../layout/Layout";

function renderShell(initialPath: string = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<div>home</div>} />
          <Route path="/applications" element={<div>apps</div>} />
          <Route path="/settings" element={<div>settings</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("App shell", () => {
  it("renders the cockpit brand title", () => {
    renderShell();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /jobapply/i,
    );
  });

  it("renders the primary workspace navigation with all five Track + Create labels", () => {
    renderShell();
    const primaryNav = screen.getByRole("navigation", { name: /primary/i });
    for (const label of [
      "Dashboard",
      "Jobs",
      "Applications",
      "Captures",
      "Runs",
    ]) {
      expect(primaryNav).toHaveTextContent(label);
    }
  });

  it("groups primary nav into Track and Create sub-sections", () => {
    renderShell();
    const primaryNav = screen.getByRole("navigation", { name: /primary/i });
    // Group labels surface as visible captions in the sidebar.
    expect(within(primaryNav).getByText(/^track$/i)).toBeInTheDocument();
    expect(within(primaryNav).getByText(/^create$/i)).toBeInTheDocument();
  });

  it("renders the configuration navigation group with Settings and Prompt harnesses", () => {
    renderShell();
    const configNav = screen.getByRole("navigation", {
      name: /configuration/i,
    });
    expect(configNav).toHaveTextContent(/settings/i);
    expect(configNav).toHaveTextContent(/prompt harnesses/i);
    expect(within(configNav).getByText(/^configure$/i)).toBeInTheDocument();
  });

  it("marks the active route with the active nav class", () => {
    renderShell("/applications");
    const primaryNav = screen.getByRole("navigation", { name: /primary/i });
    const appsLink = within(primaryNav).getByRole("link", {
      name: /applications/i,
    });
    expect(appsLink.className).toMatch(/nav-link-active/);
    // Sibling links are not marked active.
    const dashLink = within(primaryNav).getByRole("link", {
      name: /dashboard/i,
    });
    expect(dashLink.className).not.toMatch(/nav-link-active/);
  });

  it("renders a backend status indicator in the sidebar footer", () => {
    renderShell();
    // The footer label is rendered as static copy beneath the nav groups.
    expect(screen.getByText(/local backend/i)).toBeInTheDocument();
  });
});
