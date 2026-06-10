import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { listCapturesMock } = vi.hoisted(() => ({
  listCapturesMock: vi.fn(),
}));

vi.mock("../api", () => ({
  listCaptures: listCapturesMock,
  // CapturesPage imports ApiError for its error branch.
  ApiError: class ApiError extends Error {},
}));

import { CapturesPage } from "../pages/CapturesPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <CapturesPage />
    </MemoryRouter>,
  );
}

describe("CapturesPage", () => {
  it("renders the empty state when there are no pending captures", async () => {
    // Task 121: the capture inbox is demoted out of primary nav, but the
    // route still renders a clear empty state when visited directly.
    listCapturesMock.mockResolvedValue([]);
    renderPage();

    expect(
      await screen.findByText(/no pending captures/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/capture a job from the browser extension/i),
    ).toBeInTheDocument();
  });

  it("lists pending captures when some are awaiting review", async () => {
    listCapturesMock.mockResolvedValue([
      {
        id: "cap-1",
        source_platform: "linkedin",
        capture_method: "browser_extension_current_page",
        external_url: "https://www.linkedin.com/jobs/view/1/",
        external_job_id: null,
        company: "Acme",
        title: "ML Engineer",
        location: null,
        description_text: "build",
        application_method: null,
        raw_text: null,
        captured_at: "2026-06-10T10:00:00Z",
        user_confirmed: false,
        created_at: "2026-06-10T10:00:00Z",
        job_id: null,
      },
    ]);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/ML Engineer/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Acme/)).toBeInTheDocument();
  });
});
