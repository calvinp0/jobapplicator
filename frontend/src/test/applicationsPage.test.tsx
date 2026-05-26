import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const {
  listApplicationsMock,
  listJobsMock,
  markApplicationRejectedMock,
  markApplicationInterviewMock,
  submitApplicationMock,
  syncApplicationsGmailMock,
  getGmailStatusMock,
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
    listApplicationsMock: vi.fn(),
    listJobsMock: vi.fn(),
    markApplicationRejectedMock: vi.fn(),
    markApplicationInterviewMock: vi.fn(),
    submitApplicationMock: vi.fn(),
    syncApplicationsGmailMock: vi.fn(),
    getGmailStatusMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  listApplications: listApplicationsMock,
  listJobs: listJobsMock,
  markApplicationRejected: markApplicationRejectedMock,
  markApplicationInterview: markApplicationInterviewMock,
  submitApplication: submitApplicationMock,
  syncApplicationsGmail: syncApplicationsGmailMock,
  getGmailStatus: getGmailStatusMock,
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

function rowFor(title: string | RegExp): HTMLElement {
  const link = screen.getByRole("link", { name: title });
  const row = link.closest("tr");
  if (!row) throw new Error(`No table row found for ${title}`);
  return row as HTMLElement;
}

function emailLink(
  overrides: {
    classified_status?: string | null;
    sender?: string | null;
    received_at?: string | null;
  } = {},
) {
  return {
    id: "el-1",
    application_id: "app-x",
    gmail_message_id: "manual:abc",
    gmail_thread_id: null,
    subject: "Hi",
    sender: overrides.sender ?? "acme@example.com",
    received_at: overrides.received_at ?? "2026-05-22T12:00:00Z",
    classified_status: overrides.classified_status ?? "confirmation",
    confidence: null,
    created_at: "2026-05-22T12:00:01Z",
  };
}

const jobs = [
  {
    id: "job-draft",
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
    id: "job-sent",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Beta Inc",
    title: "Platform Lead",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
  {
    id: "job-confirmation",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Gamma LLC",
    title: "Backend Eng",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
  {
    id: "job-rejected",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Delta Co",
    title: "Frontend Eng",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
  {
    id: "job-interview",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Epsilon Ltd",
    title: "Staff Eng",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
  {
    id: "job-offer",
    source_platform: "linkedin",
    external_url: null,
    external_job_id: null,
    company: "Zeta Group",
    title: "Principal Eng",
    location: null,
    description_text: "",
    application_method: null,
    created_from_capture_id: null,
    created_at: "2026-05-22T10:00:00Z",
    updated_at: "2026-05-22T10:00:00Z",
  },
];

const applications = [
  {
    id: "app-draft",
    job_id: "job-draft",
    resume_version_id: "version-1",
    status: "approved",
    submitted_at: null,
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T11:00:00Z",
    timeline_stage: "draft",
    last_email_link: null,
    email_link_count: 0,
    submission_status: "not_submitted",
    email_status: "not_watching",
    next_action: "Ready to submit",
    latest_run_id: "run-1",
    latest_run_status: "imported",
    last_email_at: null,
  },
  {
    id: "app-sent",
    job_id: "job-sent",
    resume_version_id: "version-2",
    status: "submitted",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    timeline_stage: "sent",
    last_email_link: null,
    email_link_count: 0,
    submission_status: "submitted",
    email_status: "watching",
    next_action: "Waiting for email",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: null,
  },
  {
    id: "app-confirmation",
    job_id: "job-confirmation",
    resume_version_id: "version-3",
    status: "submitted",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    timeline_stage: "confirmation_received",
    last_email_link: emailLink({
      classified_status: "confirmation",
      sender: "ats@gamma.example",
    }),
    email_link_count: 1,
    submission_status: "submitted",
    email_status: "classified_neutral",
    next_action: "Waiting for response",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: "2026-05-22T12:00:00Z",
  },
  {
    id: "app-rejected",
    job_id: "job-rejected",
    resume_version_id: "version-4",
    status: "rejected",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    timeline_stage: "rejected",
    last_email_link: emailLink({
      classified_status: "rejection",
      sender: "hiring@delta.example",
    }),
    email_link_count: 3,
    submission_status: "submitted",
    email_status: "classified_rejection",
    next_action: "Rejected",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: "2026-05-22T12:00:00Z",
  },
  {
    id: "app-interview",
    job_id: "job-interview",
    resume_version_id: "version-5",
    status: "interview",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    timeline_stage: "interview",
    last_email_link: emailLink({
      classified_status: "next_step",
      sender: "recruiter@epsilon.example",
    }),
    email_link_count: 1,
    submission_status: "submitted",
    email_status: "classified_positive",
    next_action: "Interview response needed",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: "2026-05-22T12:00:00Z",
  },
  {
    id: "app-offer",
    job_id: "job-offer",
    resume_version_id: "version-6",
    status: "offer",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T11:00:00Z",
    updated_at: "2026-05-22T12:00:00Z",
    timeline_stage: "offer",
    last_email_link: emailLink({
      classified_status: "offer",
      sender: "hiring@zeta.example",
    }),
    email_link_count: 2,
    submission_status: "submitted",
    email_status: "classified_positive",
    next_action: "Respond to offer",
    latest_run_id: null,
    latest_run_status: null,
    last_email_at: "2026-05-22T12:00:00Z",
  },
];

describe("ApplicationsPage", () => {
  beforeEach(() => {
    listApplicationsMock.mockResolvedValue(applications);
    listJobsMock.mockResolvedValue(jobs);
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the table header row with the expected columns", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );
    const headerColumns = [
      "Job",
      "Status",
      "Submission",
      "Email",
      "Latest run",
      "Updated",
      "Next action",
      "Actions",
    ];
    for (const col of headerColumns) {
      expect(
        screen.getByRole("columnheader", { name: col }),
      ).toBeInTheDocument();
    }
  });

  it("renders applications as table rows with badge labels and variant classes", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // Each row carries a detail link to its application.
    expect(
      screen.getByRole("link", { name: "Senior Engineer" }),
    ).toHaveAttribute("href", "/applications/app-draft");
    expect(
      screen.getByRole("link", { name: "Platform Lead" }),
    ).toHaveAttribute("href", "/applications/app-sent");
    expect(
      screen.getByRole("link", { name: "Backend Eng" }),
    ).toHaveAttribute("href", "/applications/app-confirmation");
    expect(
      screen.getByRole("link", { name: "Frontend Eng" }),
    ).toHaveAttribute("href", "/applications/app-rejected");
    expect(
      screen.getByRole("link", { name: "Staff Eng" }),
    ).toHaveAttribute("href", "/applications/app-interview");
    expect(
      screen.getByRole("link", { name: "Principal Eng" }),
    ).toHaveAttribute("href", "/applications/app-offer");

    // Company is rendered as a separate visual element under the title.
    const draftRow = rowFor("Senior Engineer");
    expect(within(draftRow).getByText("Acme Corp")).toBeInTheDocument();

    // Timeline-stage badges: visible label and color-coded variant class.
    expect(screen.getByTestId("status-badge-app-draft")).toHaveTextContent(
      /^Draft$/,
    );
    expect(screen.getByTestId("status-badge-app-draft")).toHaveClass(
      "status-badge-draft",
    );
    expect(screen.getByTestId("status-badge-app-sent")).toHaveTextContent(
      /^Sent$/,
    );
    expect(screen.getByTestId("status-badge-app-sent")).toHaveClass(
      "status-badge-submitted",
    );
    expect(
      screen.getByTestId("status-badge-app-confirmation"),
    ).toHaveTextContent(/^Confirmation received$/);
    expect(
      screen.getByTestId("status-badge-app-confirmation"),
    ).toHaveClass("status-badge-completed");
    expect(screen.getByTestId("status-badge-app-rejected")).toHaveTextContent(
      /^Rejected$/,
    );
    expect(screen.getByTestId("status-badge-app-rejected")).toHaveClass(
      "status-badge-rejected",
    );
    expect(screen.getByTestId("status-badge-app-interview")).toHaveTextContent(
      /^Interview$/,
    );
    expect(screen.getByTestId("status-badge-app-interview")).toHaveClass(
      "status-badge-interview",
    );
    expect(screen.getByTestId("status-badge-app-offer")).toHaveTextContent(
      /^Offer$/,
    );
    expect(screen.getByTestId("status-badge-app-offer")).toHaveClass(
      "status-badge-offer",
    );

    // Raw backend status enum strings must not appear inside the table body.
    const table = screen.getByTestId("applications-table");
    expect(within(table).queryByText(/^submitted$/)).toBeNull();
  });

  it("renders the last-email summary when an email link is attached", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // confirmation_received row carries a single-email summary; no email
    // count decoration because email_link_count === 1.
    expect(
      screen.getByText(/Confirmation from ats@gamma\.example/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Confirmation from ats@gamma\.example.*emails/),
    ).toBeNull();
  });

  it("appends ` · N emails` decoration when email_link_count > 1", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // rejected row has 3 email links.
    expect(
      screen.getByText(/Rejection from hiring@delta\.example.*· 3 emails/),
    ).toBeInTheDocument();

    // offer row has 2 email links.
    expect(
      screen.getByText(/Offer from hiring@zeta\.example.*· 2 emails/),
    ).toBeInTheDocument();
  });

  it("does not render an email summary when last_email_link is null", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // draft and sent rows have no attached emails — no summary line.
    expect(screen.queryByText(/Confirmation from/)).toBeInTheDocument(); // gamma row only
    expect(screen.queryByText(/^Email from /)).toBeNull();
    const draftRow = rowFor("Senior Engineer");
    // The "· N emails" decoration should not appear without a summary.
    expect(draftRow.textContent ?? "").not.toMatch(/emails/);
  });

  it("renders the polished empty state when there are no applications", async () => {
    listApplicationsMock.mockResolvedValue([]);
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /create or generate a draft from a job to start tracking applications/i,
      ),
    ).toBeInTheDocument();
    // No table should be rendered in the empty state.
    expect(screen.queryByTestId("applications-table")).toBeNull();
  });

  it("renders submission, email, updated, and next-action cells for each row", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    const draftRow = rowFor("Senior Engineer");
    expect(
      within(draftRow).getByTestId("submission-app-draft"),
    ).toHaveTextContent(/^Not submitted$/);
    expect(
      within(draftRow).getByTestId("email-status-app-draft"),
    ).toHaveTextContent(/^Not watching yet$/);
    expect(
      within(draftRow).getByTestId("next-action-app-draft"),
    ).toHaveTextContent(/^Ready to submit$/);

    const sentRow = rowFor("Platform Lead");
    expect(
      within(sentRow).getByTestId("submission-app-sent"),
    ).toHaveTextContent(/^Submitted/);
    expect(
      within(sentRow).getByTestId("email-status-app-sent"),
    ).toHaveTextContent(/^Waiting for email$/);
    expect(
      within(sentRow).getByTestId("next-action-app-sent"),
    ).toHaveTextContent(/^Waiting for email$/);

    const rejRow = rowFor("Frontend Eng");
    expect(
      within(rejRow).getByTestId("email-status-app-rejected"),
    ).toHaveTextContent(/^Rejection detected$/);
    expect(
      within(rejRow).getByTestId("next-action-app-rejected"),
    ).toHaveTextContent(/^Rejected$/);
  });

  it("renders an updated-time cell for each application row", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    for (const app of applications) {
      expect(screen.getByTestId(`updated-${app.id}`)).toBeInTheDocument();
    }
  });

  it("invokes markApplicationRejected when 'Mark rejected' is clicked", async () => {
    submitApplicationMock.mockResolvedValue({
      ...applications[0],
      status: "submitted",
      submission_status: "submitted",
      submitted_at: "2026-05-22T13:00:00Z",
      timeline_stage: "sent",
    });
    markApplicationRejectedMock.mockResolvedValue({
      ...applications[0],
      status: "rejected",
      submission_status: "submitted",
      timeline_stage: "rejected",
      next_action: "Rejected",
    });
    markApplicationInterviewMock.mockResolvedValue({
      ...applications[0],
      status: "interview",
      timeline_stage: "interview",
      next_action: "Interview response needed",
    });

    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    const draftRow = rowFor("Senior Engineer");
    const rejectButton = within(draftRow).getByRole("button", {
      name: /mark rejected/i,
    });
    const submitButton = within(draftRow).getByRole("button", {
      name: /mark submitted/i,
    });
    const interviewButton = within(draftRow).getByRole("button", {
      name: /mark interview/i,
    });
    expect(submitButton).toBeInTheDocument();
    expect(interviewButton).toBeInTheDocument();

    await userEvent.click(rejectButton);
    expect(markApplicationRejectedMock).toHaveBeenCalledWith("app-draft");
  });

  it("hides Mark rejected/interview on already-rejected rows", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    const rejRow = rowFor("Frontend Eng");
    expect(
      within(rejRow).queryByRole("button", { name: /mark rejected/i }),
    ).toBeNull();
    expect(
      within(rejRow).queryByRole("button", { name: /mark interview/i }),
    ).toBeNull();
    expect(
      within(rejRow).queryByRole("button", { name: /mark submitted/i }),
    ).toBeNull();
  });

  it("filters rows when a filter pill is selected", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /^rejected$/i, pressed: false }),
    );
    expect(
      screen.queryByRole("link", { name: "Senior Engineer" }),
    ).toBeNull();
    expect(
      screen.getByRole("link", { name: "Frontend Eng" }),
    ).toBeInTheDocument();
  });
});
