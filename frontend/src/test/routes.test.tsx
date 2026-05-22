import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("route smoke tests", () => {
  it.each([
    ["/captures", "Captures"],
    ["/jobs", "Jobs"],
    ["/runs", "Runs"],
    ["/applications", "Applications"],
    ["/settings", "Settings"],
  ])("renders %s as a placeholder", (path, label) => {
    renderAt(path);
    expect(
      screen.getByRole("heading", { level: 2, name: label }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not yet implemented/i),
    ).toBeInTheDocument();
  });
});
