import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { listRunsMock, ApiErrorMock } = vi.hoisted(() => {
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
    listRunsMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listRuns: listRunsMock,
  ApiError: ApiErrorMock,
}));

import { RunsPage } from "../pages/RunsPage";

function renderRuns() {
  return render(
    <MemoryRouter initialEntries={["/runs"]}>
      <Routes>
        <Route path="/runs" element={<RunsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RunsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the empty state when no runs exist", async () => {
    listRunsMock.mockResolvedValue([]);
    renderRuns();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /^runs$/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
  });

  it("renders runs sorted by created_at desc with a link to each detail page", async () => {
    listRunsMock.mockResolvedValue([
      {
        id: "run-old",
        job_id: "job-1",
        master_resume_id: "resume-1",
        evidence_bank_id: null,
        run_dir: "runs/run-old",
        status: "completed",
        prompt_hash: null,
        input_hash: null,
        output_hash: null,
        created_at: "2026-05-20T10:00:00Z",
        started_at: null,
        completed_at: null,
        error_message: null,
      },
      {
        id: "run-new",
        job_id: "job-1",
        master_resume_id: "resume-1",
        evidence_bank_id: null,
        run_dir: "runs/run-new",
        status: "created",
        prompt_hash: null,
        input_hash: null,
        output_hash: null,
        created_at: "2026-05-22T10:00:00Z",
        started_at: null,
        completed_at: null,
        error_message: null,
      },
    ]);
    renderRuns();

    await waitFor(() =>
      expect(screen.getByText("run-new")).toBeInTheDocument(),
    );

    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/runs/run-new");
    expect(links[1]).toHaveAttribute("href", "/runs/run-old");
  });
});
