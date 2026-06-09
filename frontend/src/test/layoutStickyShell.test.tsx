import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { listCapturesMock } = vi.hoisted(() => ({
  listCapturesMock: vi.fn(),
}));

vi.mock("../api", () => ({
  listCaptures: listCapturesMock,
}));

import { Layout } from "../layout/Layout";

function renderLayoutAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route
            path="/resume-versions/:versionId/review"
            element={<div data-testid="review-stub">review</div>}
          />
          <Route path="/applications" element={<div>apps</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("Layout content shell (sticky review panel)", () => {
  it("opts the resume review route into an overflow-visible content shell so the sticky panel can pin", async () => {
    listCapturesMock.mockResolvedValue([]);
    const { container } = renderLayoutAt("/resume-versions/v1/review");

    await screen.findByTestId("review-stub");
    const main = container.querySelector("main.content");
    expect(main).not.toBeNull();
    // The review route adds `.content-review`, which sets `overflow: visible`
    // so `.content` does not capture the sticky AI-review column's scroll
    // context. Without it, sticky silently breaks.
    expect(main?.className).toContain("content-review");
  });

  it("does not apply the overflow-visible shell on non-review routes", async () => {
    listCapturesMock.mockResolvedValue([]);
    const { container } = renderLayoutAt("/applications");

    await waitFor(() =>
      expect(container.querySelector("main.content")).not.toBeNull(),
    );
    const main = container.querySelector("main.content");
    expect(main?.className).not.toContain("content-review");
  });
});
