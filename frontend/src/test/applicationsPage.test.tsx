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
      "Application",
      "Pipeline",
      "Email",
      "Activity",
      "Next action",
    ];
    for (const col of headerColumns) {
      expect(
        screen.getByRole("columnheader", { name: col }),
      ).toBeInTheDocument();
    }
    // Columns removed in the redesign must no longer appear.
    for (const removed of [
      "Job",
      "Status",
      "Submission",
      "Latest run",
      "Updated",
      "Actions",
    ]) {
      expect(
        screen.queryByRole("columnheader", { name: removed }),
      ).toBeNull();
    }
  });

  it("renders applications as table rows with compact pipeline status indicators", async () => {
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

    // Compact pipeline status: a short single-line label + colour-coded
    // variant class. The label is deliberately shorter than the full
    // timeline-stage wording so it never wraps in the narrow column.
    const draftStatus = screen.getByTestId("pipeline-status-app-draft");
    expect(draftStatus).toHaveTextContent(/^Draft$/);
    expect(draftStatus).toHaveClass("applications-status-draft");
    expect(screen.getByTestId("pipeline-status-app-sent")).toHaveTextContent(
      /^Submitted$/,
    );
    expect(screen.getByTestId("pipeline-status-app-sent")).toHaveClass(
      "applications-status-submitted",
    );
    expect(
      screen.getByTestId("pipeline-status-app-confirmation"),
    ).toHaveTextContent(/^Confirmation$/);
    expect(
      screen.getByTestId("pipeline-status-app-confirmation"),
    ).toHaveClass("applications-status-confirmation");
    expect(
      screen.getByTestId("pipeline-status-app-rejected"),
    ).toHaveTextContent(/^Rejected$/);
    expect(screen.getByTestId("pipeline-status-app-rejected")).toHaveClass(
      "applications-status-rejected",
    );
    expect(
      screen.getByTestId("pipeline-status-app-interview"),
    ).toHaveTextContent(/^Interview$/);
    expect(screen.getByTestId("pipeline-status-app-interview")).toHaveClass(
      "applications-status-interview",
    );
    expect(screen.getByTestId("pipeline-status-app-offer")).toHaveTextContent(
      /^Offer$/,
    );
    expect(screen.getByTestId("pipeline-status-app-offer")).toHaveClass(
      "applications-status-offer",
    );

    // The redesign drops the large rounded pill: no pipeline status carries
    // the old `status-badge` pill classes.
    for (const id of [
      "app-draft",
      "app-sent",
      "app-confirmation",
      "app-rejected",
      "app-interview",
      "app-offer",
    ]) {
      const status = screen.getByTestId(`pipeline-status-${id}`);
      expect(status.className).not.toMatch(/(^|\s)status-badge(\s|-|$)/);
    }

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

  it("renders status, email, and next-action cells for each row", async () => {
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    const draftRow = rowFor("Senior Engineer");
    expect(
      within(draftRow).getByTestId("email-status-app-draft"),
    ).toHaveTextContent(/^Not watching yet$/);
    expect(
      within(draftRow).getByTestId("next-action-app-draft"),
    ).toHaveTextContent(/^Ready to submit$/);

    const sentRow = rowFor("Platform Lead");
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

  it("renders submission text inside the Status cell, beneath the stage status", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    // A not_submitted draft row shows the inline "Not submitted yet" line
    // inside the Status cell — same <td> as the stage badge.
    const draftRow = rowFor("Senior Engineer");
    const draftSubmission = within(draftRow).getByTestId(
      "submission-app-draft",
    );
    expect(draftSubmission).toHaveTextContent(/^Not submitted yet$/);
    const draftStatus = within(draftRow).getByTestId("pipeline-status-app-draft");
    expect(draftStatus.closest("td")).toBe(draftSubmission.closest("td"));

    // A submitted row shows "Submitted <date>" in the same Status cell.
    const sentRow = rowFor("Platform Lead");
    expect(
      within(sentRow).getByTestId("submission-app-sent"),
    ).toHaveTextContent(/^Submitted /);
  });

  it("renders an Updated line inside the Activity cell", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    for (const app of applications) {
      const updated = screen.getByTestId(`updated-${app.id}`);
      expect(updated).toHaveTextContent(/^Updated /);
      // The redesigned table puts "Updated" in its own Activity column,
      // separate from the Email column.
      const cell = updated.closest("td");
      expect(cell).not.toBeNull();
      expect(cell?.getAttribute("data-label")).toBe("Activity");
      const emailStatus = screen.getByTestId(`email-status-${app.id}`);
      expect(updated.closest("td")).not.toBe(emailStatus.closest("td"));
    }
  });

  it("renders the redesigned toolbar with filter chips and Sync Gmail", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );
    const toolbar = screen.getByRole("toolbar", {
      name: /applications toolbar/i,
    });
    // Sync Gmail lives inside the toolbar in the redesign.
    const syncButton = screen.getByTestId("sync-gmail-button");
    expect(toolbar.contains(syncButton)).toBe(true);
    // Filter chips render inside the toolbar with a toolbar role of
    // their own.
    const chipsToolbar = within(toolbar).getByRole("toolbar", {
      name: /filter applications/i,
    });
    expect(
      within(chipsToolbar).getByRole("button", { name: /^all/i }),
    ).toBeInTheDocument();
    expect(
      within(chipsToolbar).getByRole("button", { name: /^submitted/i }),
    ).toBeInTheDocument();
  });

  it("renders exactly one primary action button per row", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );

    for (const app of applications) {
      const row = screen.getByTestId(`next-action-${app.id}`).closest("tr");
      expect(row).not.toBeNull();
      // The action cluster renders one primary <a> button plus a single
      // "More actions" overflow trigger — never a stack of competing buttons.
      const actionLinks = within(row as HTMLElement)
        .getAllByRole("link")
        .filter((el) => el.className.includes("applications-primary-action"));
      expect(actionLinks).toHaveLength(1);
    }
  });

  it("maps each pipeline state to the expected single primary action", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );

    const primaryFor = (title: string) => {
      const row = rowFor(title);
      const [link] = within(row)
        .getAllByRole("link")
        .filter((el) => el.className.includes("applications-primary-action"));
      return link;
    };

    // approved + not submitted (next_action "Ready to submit") → Continue.
    expect(primaryFor("Senior Engineer")).toHaveTextContent(/^Continue$/);
    expect(primaryFor("Senior Engineer")).toHaveAttribute(
      "href",
      "/applications/app-draft",
    );
    // submitted, waiting → Open.
    expect(primaryFor("Platform Lead")).toHaveTextContent(/^Open$/);
    // confirmation received → Open.
    expect(primaryFor("Backend Eng")).toHaveTextContent(/^Open$/);
  });

  it("shows Review draft as the primary action for an un-approved draft", async () => {
    listApplicationsMock.mockResolvedValue([
      {
        ...applications[0],
        id: "app-review",
        job_id: "job-draft",
        status: "generated",
        resume_version_id: "version-review",
        latest_run_status: "imported",
        next_action: "Review draft",
      },
    ]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("applications-table")).toBeInTheDocument(),
    );
    const row = rowFor("Senior Engineer");
    const [primary] = within(row)
      .getAllByRole("link")
      .filter((el) => el.className.includes("applications-primary-action"));
    expect(primary).toHaveTextContent(/^Review draft$/);
    expect(primary).toHaveAttribute("href", "/resume-versions/version-review");
  });

  it("keeps Mark submitted/interview/rejected in the secondary overflow menu", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    const draftRow = rowFor("Senior Engineer");
    // The mutation actions are not rendered as inline row buttons...
    expect(
      within(draftRow).queryByRole("button", { name: /mark submitted/i }),
    ).toBeNull();
    // ...they live behind the "More actions" overflow trigger.
    const trigger = within(draftRow).getByRole("button", {
      name: /more actions/i,
    });
    await userEvent.click(trigger);
    const menu = within(draftRow).getByRole("menu");
    expect(
      within(menu).getByRole("menuitem", { name: /mark submitted/i }),
    ).toBeInTheDocument();
    expect(
      within(menu).getByRole("menuitem", { name: /mark interview/i }),
    ).toBeInTheDocument();
    expect(
      within(menu).getByRole("menuitem", { name: /mark rejected/i }),
    ).toBeInTheDocument();
  });

  it("invokes markApplicationRejected from the overflow menu", async () => {
    markApplicationRejectedMock.mockResolvedValue({
      ...applications[0],
      status: "rejected",
      submission_status: "submitted",
      timeline_stage: "rejected",
      next_action: "Rejected",
    });

    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );

    const draftRow = rowFor("Senior Engineer");
    await userEvent.click(
      within(draftRow).getByRole("button", { name: /more actions/i }),
    );
    await userEvent.click(
      within(draftRow).getByRole("menuitem", { name: /mark rejected/i }),
    );
    expect(markApplicationRejectedMock).toHaveBeenCalledWith("app-draft");
  });

  it("omits Mark rejected/interview/submitted from the menu on a rejected row", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    const rejRow = rowFor("Frontend Eng");
    await userEvent.click(
      within(rejRow).getByRole("button", { name: /more actions/i }),
    );
    const menu = within(rejRow).getByRole("menu");
    expect(
      within(menu).queryByRole("menuitem", { name: /mark rejected/i }),
    ).toBeNull();
    expect(
      within(menu).queryByRole("menuitem", { name: /mark interview/i }),
    ).toBeNull();
    expect(
      within(menu).queryByRole("menuitem", { name: /mark submitted/i }),
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
