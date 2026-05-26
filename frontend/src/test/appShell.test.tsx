import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../api", () => ({
  listCaptures: vi.fn().mockResolvedValue([]),
}));

import { Layout } from "../layout/Layout";

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<div>home</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("App shell", () => {
  it("renders the primary workspace navigation", () => {
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

  it("renders the configuration navigation group with Settings and Prompt harnesses", () => {
    renderShell();
    const configNav = screen.getByRole("navigation", {
      name: /configuration/i,
    });
    expect(configNav).toHaveTextContent(/settings/i);
    expect(configNav).toHaveTextContent(/prompt harnesses/i);
  });

  it("renders the cockpit brand title", () => {
    renderShell();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /jobapply/i,
    );
  });
});
