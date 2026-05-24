import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { listApplicationsMock, listJobsMock, ApiErrorMock } = vi.hoisted(() => {
  class ApiErrorMock extends Error {
    status: number;
    body: unknown;
    constructor(message: string, status: number, body: unknown) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
    }
  }
  return {
    listApplicationsMock: vi.fn(),
    listJobsMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listApplications: listApplicationsMock,
  listJobs: listJobsMock,
  ApiError: ApiErrorMock,
}));

import { ApplicationsPage } from "../pages/ApplicationsPage";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/applications"]}>
      <Routes>
        <Route path="/applications" element={<ApplicationsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const jobs = [
  {
    id: "job-1",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Acme Corp",
    title: "Senior Engineer",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
  {
    id: "job-2",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Beta Inc",
    title: "Platform Lead",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-21T10:00:00Z",
    updated_at: "2026-05-21T10:00:00Z",
  },
];

const applications = [
  {
    id: "app-1",
    job_id: "job-1",
    resume_version_id: "version-1",
    status: "approved",
    submitted_at: null,
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T11:00:00Z",
  },
  {
    id: "app-2",
    job_id: "job-2",
    resume_version_id: "version-2",
    status: "submitted",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
  },
];

describe("ApplicationsPage", () => {
  beforeEach(() => {
    listApplicationsMock.mockResolvedValue(applications);
    listJobsMock.mockResolvedValue(jobs);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders applications joined with their job context and detail links", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    const link1 = screen.getByRole("link", {
      name: /senior engineer — acme corp/i,
    });
    const link2 = screen.getByRole("link", {
      name: /platform lead — beta inc/i,
    });
    expect(link1).toHaveAttribute("href", "/applications/app-1");
    expect(link2).toHaveAttribute("href", "/applications/app-2");

    expect(screen.getByText(/approved/i)).toBeInTheDocument();
    expect(screen.getByText(/5\/22\/2026|May 22, 2026|2026/)).toBeInTheDocument();

    // Each row carries a status badge: Approved (default variant) and
    // Sent (submitted variant).
    expect(screen.getByText("Approved")).toHaveClass("status-badge");
    expect(screen.getByText("Sent")).toHaveClass(
      "status-badge-submitted",
    );

    // Raw backend status enum strings must not appear in default UI.
    expect(screen.queryByText(/^submitted$/i)).toBeNull();
  });

  it("renders the empty state when there are no applications", async () => {
    listApplicationsMock.mockResolvedValue([]);
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });
});
