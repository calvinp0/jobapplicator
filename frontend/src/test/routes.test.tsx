import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    listCaptures: vi.fn().mockResolvedValue([]),
    listJobs: vi.fn().mockResolvedValue([]),
  };
});

import { App } from "../App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("route smoke tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders /captures with empty pending list", async () => {
    renderAt("/captures");
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /pending captures/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/no pending captures/i)).toBeInTheDocument();
  });

  it("renders /jobs with empty list", async () => {
    renderAt("/jobs");
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^jobs$/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/no confirmed jobs yet/i)).toBeInTheDocument();
  });

  it.each([
    ["/runs", "Runs"],
    ["/applications", "Applications"],
    ["/settings", "Settings"],
  ])("renders %s as a placeholder", async (path, label) => {
    renderAt(path);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: label }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/not yet implemented/i)).toBeInTheDocument();
  });
});
