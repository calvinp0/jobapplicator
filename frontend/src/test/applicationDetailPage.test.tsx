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
  listApplicationEmailLinksMock,
  createApplicationEmailLinkMock,
  getGmailStatusMock,
  getGmailAuthUrlMock,
  searchApplicationGmailMock,
  classifyApplicationGmailMock,
  listGmailCandidatesMock,
  linkGmailEmailMock,
  listLinkedGmailEmailsMock,
  unlinkGmailEmailMock,
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
    listApplicationEmailLinksMock: vi.fn(),
    createApplicationEmailLinkMock: vi.fn(),
    getGmailStatusMock: vi.fn(),
    getGmailAuthUrlMock: vi.fn(),
    searchApplicationGmailMock: vi.fn(),
    classifyApplicationGmailMock: vi.fn(),
    listGmailCandidatesMock: vi.fn(),
    linkGmailEmailMock: vi.fn(),
    listLinkedGmailEmailsMock: vi.fn(),
    unlinkGmailEmailMock: vi.fn(),
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
  listApplicationEmailLinks: listApplicationEmailLinksMock,
  createApplicationEmailLink: createApplicationEmailLinkMock,
  getGmailStatus: getGmailStatusMock,
  getGmailAuthUrl: getGmailAuthUrlMock,
  searchApplicationGmail: searchApplicationGmailMock,
  classifyApplicationGmail: classifyApplicationGmailMock,
  listGmailCandidates: listGmailCandidatesMock,
  linkGmailEmail: linkGmailEmailMock,
  listLinkedGmailEmails: listLinkedGmailEmailsMock,
  unlinkGmailEmail: unlinkGmailEmailMock,
  downloadRunResume: vi.fn(() => Promise.resolve()),
  downloadRunArtifact: vi.fn(() => Promise.resolve()),
  exportRun: vi.fn(() =>
    Promise.resolve({ ok: true, export_dir: "", files: [] }),
  ),
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
  timeline_stage: "draft",
  last_email_link: null,
  email_link_count: 0,
};

const applicationWithoutVersion = {
  ...applicationWithApprovedVersion,
  resume_version_id: null,
};

const submittedApplication = {
  ...applicationWithApprovedVersion,
  status: "submitted",
  submitted_at: "2026-05-22T14:00:00Z",
  timeline_stage: "sent",
};

const applicationConfirmationReceived = {
  ...submittedApplication,
  timeline_stage: "confirmation_received",
  email_link_count: 1,
};

const confirmationEmail = {
  id: "email-1",
  application_id: "app-1",
  gmail_message_id: "manual:abc-123",
  gmail_thread_id: null,
  subject: "We've received your application",
  sender: "noreply@acme.com",
  received_at: "2026-05-22T14:30:00Z",
  classified_status: "confirmation",
  confidence: null,
  created_at: "2026-05-22T14:30:00Z",
};

describe("ApplicationDetailPage", () => {
  beforeEach(() => {
    getJobMock.mockResolvedValue(job);
    listApplicationEmailLinksMock.mockResolvedValue([]);
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });
    getGmailAuthUrlMock.mockResolvedValue({
      auth_url: "https://accounts.google.com/o/oauth2/auth?fake=1",
      scope: "https://www.googleapis.com/auth/gmail.readonly",
    });
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: "(\"Acme Corp\") newer_than:180d",
      count: 0,
      candidates: [],
    });
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: null,
      count: 0,
      strong_count: 0,
      possible_count: 0,
      candidates: [],
    });
    linkGmailEmailMock.mockResolvedValue({
      application_id: "app-1",
      email_link: {
        id: "el-new",
        application_id: "app-1",
        gmail_message_id: "msg-1",
        gmail_thread_id: null,
        subject: null,
        sender: null,
        received_at: null,
        classified_status: "confirmation",
        confidence: null,
        match_method: "manual",
        linked_by_user: true,
        evidence: null,
        created_at: "2026-05-25T12:00:00Z",
      },
      classification: "submission_confirmation",
      email_status: "confirmation_found",
      application_status: "submitted",
      application_status_changed: false,
    });
    listLinkedGmailEmailsMock.mockResolvedValue({
      application_id: "app-1",
      linked_emails: [],
    });
    unlinkGmailEmailMock.mockResolvedValue({
      application_id: "app-1",
      removed_email_link_id: "el-1",
      remaining_linked_count: 0,
    });
    classifyApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      message_id: "msg-1",
      classification: "rejection",
      confidence: 0.86,
      email_status: "classified_rejection",
      application_status: "rejected",
      evidence: [
        {
          field: "snippet",
          text: "we will not be moving forward with your application",
          reason: "contains rejection phrase",
        },
      ],
      reason: "Matched rejection phrase in email snippet",
      application_status_changed: true,
      email_link_id: "el-new",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("disables 'I've sent it' when no resume version is linked", async () => {
    getApplicationMock.mockResolvedValue(applicationWithoutVersion);
    listApplicationEventsMock.mockResolvedValue([]);

    renderApp("app-1");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /application/i }),
      ).toBeInTheDocument(),
    );

    const button = await screen.findByRole("button", {
      name: /i've sent it/i,
    });
    expect(button).toBeDisabled();
    expect(
      screen.getByText(
        /pick an approved draft on the job page first\./i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mark submitted/i })).toBeNull();
  });

  it("disables 'I've sent it' when the linked version is not approved", async () => {
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
      name: /i've sent it/i,
    });
    await waitFor(() => expect(button).toBeDisabled());
    expect(
      screen.getByText(
        /this draft has not been approved yet\. approve it on the job page first\./i,
      ),
    ).toBeInTheDocument();
  });

  it("records send and reflects the Sent status when version is approved", async () => {
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
      name: /i've sent it/i,
    });
    await waitFor(() => expect(button).toBeEnabled());

    await user.click(button);

    await waitFor(() =>
      expect(submitApplicationMock).toHaveBeenCalledWith("app-1"),
    );

    // Badge updates to Sent with the submitted variant once the
    // status transitions.
    await waitFor(() => {
      const badge = screen
        .getAllByText("Sent")
        .find((el) => el.classList.contains("status-badge"));
      expect(badge).toBeDefined();
      expect(badge).toHaveClass("status-badge-submitted");
    });

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /i've sent it/i }),
      ).toBeDisabled(),
    );

    // Raw backend status enum string must not appear in the default UI.
    // (The event_type field is allowed to render its raw value.)
    expect(
      screen
        .queryAllByText(/^submitted$/i)
        .filter((el) => el.tagName !== "STRONG"),
    ).toHaveLength(0);

    // Heading now includes the job context.
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /application — senior engineer — acme corp/i,
      }),
    ).toBeInTheDocument();

    // Resume version link uses draft language, never "Version N".
    const versionLink = screen.getByRole("link", {
      name: /draft 2 \(approved\)/i,
    });
    expect(versionLink).toHaveAttribute(
      "href",
      "/resume-versions/version-1",
    );
    expect(screen.queryByText(/Version 2/i)).toBeNull();
  });

  it("renders the linked resume draft as 'Draft N (Awaiting review)' when pending", async () => {
    getApplicationMock.mockResolvedValue({
      ...applicationWithApprovedVersion,
    });
    getResumeVersionMock.mockResolvedValue(pendingVersion);
    listApplicationEventsMock.mockResolvedValue([]);

    renderApp("app-1");

    const link = await screen.findByRole("link", {
      name: /draft 2 \(awaiting review\)/i,
    });
    expect(link).toHaveAttribute("href", "/resume-versions/version-1");
    expect(screen.queryByText(/Version 2/i)).toBeNull();
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
    expect(screen.getByText(/^Sent at$/).closest("details")).toBeNull();
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

  it("renders the timeline-stage badge for the 'sent' stage", async () => {
    getApplicationMock.mockResolvedValue(submittedApplication);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([]);

    renderApp("app-1");

    await waitFor(() => {
      const badge = screen
        .getAllByText("Sent")
        .find((el) => el.classList.contains("status-badge"));
      expect(badge).toBeDefined();
      expect(badge).toHaveClass("status-badge-submitted");
    });
  });

  it("renders the timeline-stage badge for the 'confirmation_received' stage", async () => {
    getApplicationMock.mockResolvedValue(applicationConfirmationReceived);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([confirmationEmail]);

    renderApp("app-1");

    await waitFor(() => {
      const badge = screen
        .getAllByText("Confirmation received")
        .find((el) => el.classList.contains("status-badge"));
      expect(badge).toBeDefined();
      expect(badge).toHaveClass("status-badge-completed");
    });
  });

  it("renders the attached email-link list", async () => {
    getApplicationMock.mockResolvedValue(applicationConfirmationReceived);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([
      confirmationEmail,
      {
        ...confirmationEmail,
        id: "email-2",
        gmail_message_id: "manual:def-456",
        subject: "Interview invitation",
        sender: "recruiter@acme.com",
        classified_status: "next_step",
        received_at: "2026-05-23T10:00:00Z",
      },
    ]);

    renderApp("app-1");

    await screen.findByRole("heading", { level: 3, name: /email evidence/i });

    expect(
      screen.getByText("We've received your application"),
    ).toBeInTheDocument();
    expect(screen.getByText("noreply@acme.com")).toBeInTheDocument();
    expect(screen.getByText("Interview invitation")).toBeInTheDocument();
    expect(screen.getByText("recruiter@acme.com")).toBeInTheDocument();

    const confirmationBadge = screen
      .getAllByText("Confirmation")
      .find((el) => el.classList.contains("status-badge"));
    expect(confirmationBadge).toBeDefined();
    const nextStepBadge = screen
      .getAllByText("Next step")
      .find((el) => el.classList.contains("status-badge"));
    expect(nextStepBadge).toBeDefined();
  });

  it("renders the empty-state copy when no email links are attached", async () => {
    getApplicationMock.mockResolvedValue(submittedApplication);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([]);

    renderApp("app-1");

    await waitFor(() =>
      expect(
        screen.getByText(
          /no emails recorded yet\. the gmail integration is not enabled — you can record an email by hand\./i,
        ),
      ).toBeInTheDocument(),
    );
  });

  it("records a manual email, refreshes the application, and refetches the email list", async () => {
    const user = userEvent.setup();
    getApplicationMock.mockResolvedValueOnce(submittedApplication);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValueOnce([]);
    createApplicationEmailLinkMock.mockResolvedValue(confirmationEmail);
    getApplicationMock.mockResolvedValueOnce(applicationConfirmationReceived);
    listApplicationEmailLinksMock.mockResolvedValueOnce([confirmationEmail]);

    renderApp("app-1");

    await screen.findByText("Record email manually", { selector: "summary" });

    await user.clear(screen.getByLabelText(/gmail message id/i));
    await user.type(
      screen.getByLabelText(/gmail message id/i),
      "manual:abc-123",
    );
    await user.type(
      screen.getByLabelText(/sender/i),
      "noreply@acme.com",
    );
    await user.type(
      screen.getByLabelText(/subject/i),
      "We've received your application",
    );

    await user.click(
      screen.getByRole("button", { name: /record email manually/i }),
    );

    await waitFor(() =>
      expect(createApplicationEmailLinkMock).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          gmail_message_id: "manual:abc-123",
          classified_status: "confirmation",
          sender: "noreply@acme.com",
          subject: "We've received your application",
        }),
      ),
    );

    // After create: parent application is re-fetched and the timeline-stage
    // badge reflects the new stage.
    await waitFor(() => {
      const badge = screen
        .getAllByText("Confirmation received")
        .find((el) => el.classList.contains("status-badge"));
      expect(badge).toBeDefined();
    });

    // The refreshed email-link list is rendered.
    await waitFor(() =>
      expect(
        screen.getByText("We've received your application"),
      ).toBeInTheDocument(),
    );

    // Both follow-up fetches fired.
    expect(getApplicationMock).toHaveBeenCalledTimes(2);
    expect(listApplicationEmailLinksMock).toHaveBeenCalledTimes(2);
  });

  it("collapses the manual Record Email form behind a 'Record email manually' summary with helper text", async () => {
    getApplicationMock.mockResolvedValue(submittedApplication);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([]);

    renderApp("app-1");

    const summary = await screen.findByText("Record email manually", {
      selector: "summary",
    });
    const detailsEl = summary.closest("details");
    expect(detailsEl).not.toBeNull();
    // Collapsed by default so the form is reserved for emails Gmail could
    // not find.
    expect(detailsEl).not.toHaveAttribute("open");
    expect(
      screen.getByText(
        /use this only if the email was not found through gmail search/i,
      ),
    ).toBeInTheDocument();
    // The form's submit button is renamed to make it clear this records a
    // manual entry, not a Gmail-candidate link.
    expect(
      screen.getByRole("button", { name: /record email manually/i }),
    ).toBeInTheDocument();
  });

  it("prefills a manual:<uuid> gmail message id for manual entries", async () => {
    getApplicationMock.mockResolvedValue(submittedApplication);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([]);

    renderApp("app-1");

    await screen.findByText("Record email manually", { selector: "summary" });
    const input = screen.getByLabelText(/gmail message id/i) as HTMLInputElement;
    // Manual:<uuid> is only used for the typed-by-hand path — Gmail
    // candidate links pass the real Gmail message id through instead.
    expect(input.value).toMatch(/^manual:/);
  });

  it("surfaces an inline error when the create-email call fails", async () => {
    const user = userEvent.setup();
    getApplicationMock.mockResolvedValue(submittedApplication);
    getResumeVersionMock.mockResolvedValue(approvedVersion);
    listApplicationEventsMock.mockResolvedValue([]);
    listApplicationEmailLinksMock.mockResolvedValue([]);
    createApplicationEmailLinkMock.mockRejectedValue(
      new ApiErrorMock(
        "Request to /applications/app-1/email-links failed with status 422",
        422,
        null,
      ),
    );

    renderApp("app-1");

    await screen.findByText("Record email manually", { selector: "summary" });

    await user.click(
      screen.getByRole("button", { name: /record email manually/i }),
    );

    await waitFor(() => {
      const alerts = screen.getAllByRole("alert");
      const message = alerts.find((el) =>
        /failed with status 422/i.test(el.textContent ?? ""),
      );
      expect(message).toBeDefined();
    });
  });
});
