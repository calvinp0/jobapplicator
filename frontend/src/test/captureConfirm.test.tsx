import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getCaptureMock,
  confirmCaptureMock,
  listCapturesMock,
  ApiErrorMock,
} = vi.hoisted(() => {
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
    getCaptureMock: vi.fn(),
    confirmCaptureMock: vi.fn(),
    listCapturesMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getCapture: getCaptureMock,
  confirmCapture: confirmCaptureMock,
  listCaptures: listCapturesMock,
  ApiError: ApiErrorMock,
}));

import { CaptureDetailPage } from "../pages/CaptureDetailPage";

function renderDetail(captureId: string) {
  return render(
    <MemoryRouter initialEntries={[`/captures/${captureId}`]}>
      <Routes>
        <Route path="/captures/:captureId" element={<CaptureDetailPage />} />
        <Route path="/jobs/:jobId" element={<JobLanding />} />
      </Routes>
    </MemoryRouter>,
  );
}

function JobLanding() {
  return <div data-testid="job-landing">Landed on Job page</div>;
}

const baseCapture = {
  id: "cap-1",
  source_platform: "linkedin",
  capture_method: "browser_extension_current_page",
  external_url: "https://www.linkedin.com/jobs/view/1",
  external_job_id: null,
  company: "Acme Corp",
  title: "Senior Engineer",
  location: "Remote",
  description_text: "Build cool things in a small team.",
  application_method: "easy_apply",
  raw_text: "raw...",
  captured_at: "2026-05-22T12:00:00Z",
  user_confirmed: false,
  created_at: "2026-05-22T12:00:00Z",
  job_id: null,
};

describe("CaptureDetailPage confirm flow", () => {
  beforeEach(() => {
    listCapturesMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("confirms a valid capture and navigates to the new job", async () => {
    const user = userEvent.setup();
    getCaptureMock.mockResolvedValue(baseCapture);
    confirmCaptureMock.mockResolvedValue({
      id: "job-42",
      source_platform: "linkedin",
      external_url: baseCapture.external_url,
      external_job_id: null,
      company: "Acme Corp",
      title: "Senior Engineer",
      location: "Remote",
      description_text: baseCapture.description_text,
      application_method: "easy_apply",
      created_from_capture_id: baseCapture.id,
      created_at: "2026-05-22T12:01:00Z",
      updated_at: "2026-05-22T12:01:00Z",
    });

    renderDetail("cap-1");

    await waitFor(() =>
      expect(screen.getByDisplayValue("Acme Corp")).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /confirm/i }));

    await waitFor(() =>
      expect(confirmCaptureMock).toHaveBeenCalledWith("cap-1"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("job-landing")).toBeInTheDocument(),
    );
  });

  it("blocks confirm and surfaces an error when required fields are missing", async () => {
    const user = userEvent.setup();
    getCaptureMock.mockResolvedValue({
      ...baseCapture,
      company: null,
      title: "Senior Engineer",
    });

    renderDetail("cap-1");

    await waitFor(() =>
      expect(screen.getByDisplayValue("Senior Engineer")).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(
      await screen.findByText(/missing required fields:.*company/i),
    ).toBeInTheDocument();
    expect(confirmCaptureMock).not.toHaveBeenCalled();
  });

  it("shows an Open job link when the capture was auto-confirmed", async () => {
    getCaptureMock.mockResolvedValue({
      ...baseCapture,
      user_confirmed: true,
      job_id: "job-99",
    });

    renderDetail("cap-1");

    const link = await screen.findByRole("link", { name: /open job/i });
    expect(link).toHaveAttribute("href", "/jobs/job-99");
    expect(
      screen.queryByRole("button", { name: /confirm/i }),
    ).not.toBeInTheDocument();
    expect(confirmCaptureMock).not.toHaveBeenCalled();
  });

  it("fills description from page_text fallback when structured description is empty", async () => {
    getCaptureMock.mockResolvedValue({
      ...baseCapture,
      title: null,
      company: null,
      description_text: "",
      raw_text: null,
      page_title: "Senior ML Engineer at Example Co | LinkedIn",
      page_text: "Senior ML Engineer at Example Co — Build large-scale ranking systems.",
      diagnostics: {
        extractor: "linkedin",
        selectors_matched: {
          title: false,
          company: false,
          location: false,
          description: false,
        },
      },
    });

    renderDetail("cap-1");

    const descBox = (await screen.findByRole("textbox", {
      name: /description/i,
    })) as HTMLTextAreaElement;
    expect(descBox.value).toContain("Build large-scale ranking systems");
  });

  it("shows a warning when structured extraction failed", async () => {
    getCaptureMock.mockResolvedValue({
      ...baseCapture,
      title: null,
      company: null,
      description_text: "",
      diagnostics: {
        extractor: "linkedin",
        selectors_matched: {
          title: false,
          company: false,
          location: false,
          description: false,
        },
      },
    });

    renderDetail("cap-1");

    expect(
      await screen.findByTestId("extraction-warning"),
    ).toBeInTheDocument();
  });

  it("renders a raw captured text preview when page_text is present", async () => {
    getCaptureMock.mockResolvedValue({
      ...baseCapture,
      description_text: "",
      page_text: "Bounded body text excerpt from LinkedIn.",
    });

    renderDetail("cap-1");

    const preview = await screen.findByTestId("raw-text-preview");
    expect(preview.textContent).toContain(
      "Bounded body text excerpt from LinkedIn.",
    );
  });

  it("surfaces server-side 422 validation errors from the confirm endpoint", async () => {
    const user = userEvent.setup();
    getCaptureMock.mockResolvedValue(baseCapture);
    confirmCaptureMock.mockRejectedValue(
      new ApiErrorMock("Request failed", 422, {
        detail: {
          message: "Missing required fields for capture confirmation",
          missing_fields: ["description_text"],
        },
      }),
    );

    renderDetail("cap-1");

    await waitFor(() =>
      expect(screen.getByDisplayValue("Acme Corp")).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(
      await screen.findByText(/missing required fields:.*description/i),
    ).toBeInTheDocument();
  });
});
