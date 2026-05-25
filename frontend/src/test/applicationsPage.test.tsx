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

  it("renders one row per timeline stage with the correct badge label and variant", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // Each row carries a detail link to its application.
    expect(
      screen.getByRole("link", { name: /senior engineer — acme corp/i }),
    ).toHaveAttribute("href", "/applications/app-draft");
    expect(
      screen.getByRole("link", { name: /platform lead — beta inc/i }),
    ).toHaveAttribute("href", "/applications/app-sent");
    expect(
      screen.getByRole("link", { name: /backend eng — gamma llc/i }),
    ).toHaveAttribute("href", "/applications/app-confirmation");
    expect(
      screen.getByRole("link", { name: /frontend eng — delta co/i }),
    ).toHaveAttribute("href", "/applications/app-rejected");
    expect(
      screen.getByRole("link", { name: /staff eng — epsilon ltd/i }),
    ).toHaveAttribute("href", "/applications/app-interview");
    expect(
      screen.getByRole("link", { name: /principal eng — zeta group/i }),
    ).toHaveAttribute("href", "/applications/app-offer");

    // Timeline-stage badges: visible label and color-coded variant class.
    expect(screen.getByText("Draft")).toHaveClass("status-badge-draft");
    expect(screen.getByText("Sent")).toHaveClass("status-badge-submitted");
    expect(screen.getByText("Confirmation received")).toHaveClass(
      "status-badge-completed",
    );
    expect(screen.getByText("Rejected")).toHaveClass("status-badge-rejected");
    expect(screen.getByText("Interview")).toHaveClass(
      "status-badge-interview",
    );
    expect(screen.getByText("Offer")).toHaveClass("status-badge-offer");

    // Raw backend status enum strings must not appear in default UI.
    expect(screen.queryByText(/^submitted$/i)).toBeNull();
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
    // No "Email from" / "Other from" lines should appear for draft/sent.
    expect(screen.queryByText(/^Email from /)).toBeNull();
    // The "· N emails" decoration should not appear without a summary.
    const draftLink = screen.getByRole("link", {
      name: /senior engineer — acme corp/i,
    });
    const draftRow = draftLink.closest("li");
    expect(draftRow).not.toBeNull();
    expect(draftRow!.textContent ?? "").not.toMatch(/emails/);
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

  it("renders submission, email, updated, and next-action lines for each row", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // Draft row shows submission, email state, and next action.
    const draftRow = screen
      .getByRole("link", { name: /senior engineer — acme corp/i })
      .closest("li");
    expect(draftRow).not.toBeNull();
    expect(
      within(draftRow!).getByText(/Submission: Not submitted/),
    ).toBeInTheDocument();
    expect(
      within(draftRow!).getByText(/Email: Not watching yet/),
    ).toBeInTheDocument();
    expect(
      within(draftRow!).getByText(/Next: Ready to submit/),
    ).toBeInTheDocument();

    // Submitted row shows submitted date and watching state.
    const sentRow = screen
      .getByRole("link", { name: /platform lead — beta inc/i })
      .closest("li");
    expect(sentRow).not.toBeNull();
    expect(
      within(sentRow!).getByText(/Submission: Submitted/),
    ).toBeInTheDocument();
    expect(
      within(sentRow!).getByText(/Email: Waiting for email/),
    ).toBeInTheDocument();
    expect(
      within(sentRow!).getByText(/Next: Waiting for email/),
    ).toBeInTheDocument();

    // Rejected row shows rejection detected and Next: Rejected.
    const rejRow = screen
      .getByRole("link", { name: /frontend eng — delta co/i })
      .closest("li");
    expect(rejRow).not.toBeNull();
    expect(
      within(rejRow!).getByText(/Email: Rejection detected/),
    ).toBeInTheDocument();
    expect(within(rejRow!).getByText(/Next: Rejected/)).toBeInTheDocument();
  });

  it("renders an updated-time line for each application card", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    // At least one Updated: line is present per card.
    const updatedLines = screen.getAllByText(/^Updated: /);
    expect(updatedLines.length).toBe(applications.length);
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

    // The draft row offers all three mark actions.
    const draftLink = screen.getByRole("link", {
      name: /senior engineer — acme corp/i,
    });
    const draftRow = draftLink.closest("li");
    expect(draftRow).not.toBeNull();

    const rejectButton = within(draftRow!).getByRole("button", {
      name: /mark rejected/i,
    });
    const submitButton = within(draftRow!).getByRole("button", {
      name: /mark submitted/i,
    });
    const interviewButton = within(draftRow!).getByRole("button", {
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
    const rejLink = screen.getByRole("link", {
      name: /frontend eng — delta co/i,
    });
    const rejRow = rejLink.closest("li");
    expect(rejRow).not.toBeNull();
    expect(
      within(rejRow!).queryByRole("button", { name: /mark rejected/i }),
    ).toBeNull();
    expect(
      within(rejRow!).queryByRole("button", { name: /mark interview/i }),
    ).toBeNull();
    expect(
      within(rejRow!).queryByRole("button", { name: /mark submitted/i }),
    ).toBeNull();
  });
});
