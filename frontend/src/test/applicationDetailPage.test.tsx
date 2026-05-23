import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  getApplicationMock,
  getJobMock,
  getResumeVersionMock,
  listApplicationEventsMock,
  submitApplicationMock,
  createApplicationEventMock,
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
    getApplicationMock: vi.fn(),
    getJobMock: vi.fn(),
    getResumeVersionMock: vi.fn(),
    listApplicationEventsMock: vi.fn(),
    submitApplicationMock: vi.fn(),
    createApplicationEventMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getApplication: getApplicationMock,
  getJob: getJobMock,
  getResumeVersion: getResumeVersionMock,
  listApplicationEvents: listApplicationEventsMock,
  submitApplication: submitApplicationMock,
  createApplicationEvent: createApplicationEventMock,
  ApiError: ApiErrorMock,
}));

import { ApplicationDetailPage } from "../pages/ApplicationDetailPage";

function renderApp(applicationId: string) {
  return render(
    <MemoryRouter initialEntries={[`/applications/${applicationId}`]}>
      <Routes>
        <Route
          path="/applications/:applicationId"
          element={<ApplicationDetailPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

const job = {
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
};

const approvedVersion = {
  id: "version-1",
  job_id: "job-1",
  master_resume_id: "resume-1",
  claude_run_id: "run-1",
  version_number: 2,
  content_markdown: null,
  docx_path: null,
  pdf_path: null,
  content_hash: null,
  prompt_hash: null,
  source: "claude_run",
  approved_at: "2026-05-22T13:00:00Z",
  created_at: "2026-05-22T12:00:00Z",
};

const pendingVersion = { ...approvedVersion, approved_at: null };

const applicationWithApprovedVersion = {
  id: "app-1",
  job_id: "job-1",
  resume_version_id: "version-1",
  status: "approved",
  submitted_at: null,
  created_at: "2026-05-22T13:30:00Z",
  updated_at: "2026-05-22T13:30:00Z",
};

const applicationWithoutVersion = {
  ...applicationWithApprovedVersion,
  resume_version_id: null,
};

const submittedApplication = {
  ...applicationWithApprovedVersion,
  status: "submitted",
  submitted_at: "2026-05-22T14:00:00Z",
};

describe("ApplicationDetailPage", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("disables Mark Submitted when no resume version is linked", async () => {
    getApplicationMock.mockResolvedValue(applicationWithoutVersion);
    listApplicationEventsMock.mockResolvedValue([]);

    renderApp("app-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /application/i }),
      ).toBeInTheDocument(),
    );

    const button = await screen.findByRole("button", {
      name: /mark submitted/i,
    });
    expect(button).toBeDisabled();
    expect(
      screen.getByText(/link an approved resume version first/i),
    ).toBeInTheDocument();
  });

  it("disables Mark Submitted when the linked version is not approved", async () => {
    getApplicationMock.mockResolvedValue({
      ...applicationWithApprovedVersion,
    });
    getResumeVersionMock.mockResolvedValue(pendingVersion);
    listApplicationEventsMock.mockResolvedValue([]);

    renderApp("app-1");

    await waitFor(() =>
      expect(getResumeVersionMock).toHaveBeenCalledWith("version-1"),
    );

    const button = await screen.findByRole("button", {
      name: /mark submitted/i,
    });
    await waitFor(() => expect(button).toBeDisabled());
    expect(
      screen.getByText(/not yet approved/i),
    ).toBeInTheDocument();
  });

  it("submits and reflects the submitted status when version is approved", async () => {
    const user = userEvent.setup();
    getApplicationMock.mockResolvedValue({
      ...applicationWithApprovedVersion,
    });
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValueOnce([]);
    submitApplicationMock.mockResolvedValue(submittedApplication);
    listApplicationEventsMock.mockResolvedValueOnce([
      {
        id: "event-1",
        application_id: "app-1",
        event_type: "submitted",
        event_time: "2026-05-22T14:00:00Z",
        notes: null,
        source: "user",
        created_at: "2026-05-22T14:00:00Z",
      },
    ]);

    renderApp("app-1");

    const button = await screen.findByRole("button", {
      name: /mark submitted/i,
    });
    await waitFor(() => expect(button).toBeEnabled());

    await user.click(button);

    await waitFor(() =>
      expect(submitApplicationMock).toHaveBeenCalledWith("app-1"),
    );

    await waitFor(() => {
      const statusTerms = screen.getAllByText(/submitted/i);
      expect(statusTerms.length).toBeGreaterThan(0);
    });

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /mark submitted/i }),
      ).toBeDisabled(),
    );
  });

  it("renders summary fields by default and hides provenance behind Advanced details", async () => {
    const user = userEvent.setup();
    getApplicationMock.mockResolvedValue({
      ...applicationWithApprovedVersion,
    });
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);

    renderApp("app-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /application/i }),
      ).toBeInTheDocument(),
    );
    await waitFor(() => expect(getJobMock).toHaveBeenCalled());

    // Summary fields live outside the disclosure.
    expect(screen.getByText(/^Status$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Submitted$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Job$/).closest("details")).toBeNull();
    expect(screen.getByText(/^Resume version$/).closest("details")).toBeNull();
    expect(
      screen
        .getByRole("heading", { level: 3, name: /timeline/i })
        .closest("details"),
    ).toBeNull();
    expect(
      screen
        .getByRole("heading", { level: 3, name: /record event/i })
        .closest("details"),
    ).toBeNull();

    // The disclosure renders with the heading "Advanced details", closed by default.
    const disclosure = screen.getByText(/^Advanced details$/);
    const detailsEl = disclosure.closest("details");
    expect(detailsEl).not.toBeNull();
    expect(detailsEl).toHaveClass("advanced-details");
    expect(detailsEl).not.toHaveAttribute("open");

    // Provenance fields live inside the disclosure.
    expect(screen.getByText(/^Application id$/).closest("details")).toBe(
      detailsEl,
    );
    expect(screen.getByText("app-1").closest("details")).toBe(detailsEl);
    expect(screen.getByText(/^Created$/).closest("details")).toBe(detailsEl);
    expect(screen.getByText(/^Updated$/).closest("details")).toBe(detailsEl);

    // Expanding the disclosure surfaces the provenance fields to the user.
    await user.click(disclosure);
    expect(detailsEl).toHaveAttribute("open");
  });

  it("records a manual event and refreshes the timeline", async () => {
    const user = userEvent.setup();
    getApplicationMock.mockResolvedValue({
      ...applicationWithApprovedVersion,
    });
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValueOnce([]);
    createApplicationEventMock.mockResolvedValue({
      id: "event-1",
      application_id: "app-1",
      event_type: "response_received",
      event_time: "2026-05-23T08:00:00Z",
      notes: "Recruiter replied",
      source: null,
      created_at: "2026-05-23T08:00:00Z",
    });
    listApplicationEventsMock.mockResolvedValueOnce([
      {
        id: "event-1",
        application_id: "app-1",
        event_type: "response_received",
        event_time: "2026-05-23T08:00:00Z",
        notes: "Recruiter replied",
        source: null,
        created_at: "2026-05-23T08:00:00Z",
      },
    ]);

    renderApp("app-1");

    await screen.findByRole("heading", { level: 3, name: /record event/i });

    const eventTypeInput = screen.getByLabelText(/event type/i);
    const notesInput = screen.getByLabelText(/notes/i);

    await user.type(eventTypeInput, "response_received");
    await user.type(notesInput, "Recruiter replied");

    await user.click(screen.getByRole("button", { name: /add event/i }));

    await waitFor(() =>
      expect(createApplicationEventMock).toHaveBeenCalledWith("app-1", {
        event_type: "response_received",
        notes: "Recruiter replied",
      }),
    );

    await waitFor(() =>
      expect(screen.getByText("response_received")).toBeInTheDocument(),
    );
    expect(screen.getByText("Recruiter replied")).toBeInTheDocument();
  });
});
