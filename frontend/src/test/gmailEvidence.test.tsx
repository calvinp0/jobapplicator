import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  getApplicationMock,
  getGmailStatusMock,
  searchApplicationGmailMock,
  classifyApplicationGmailMock,
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
    getGmailStatusMock: vi.fn(),
    searchApplicationGmailMock: vi.fn(),
    classifyApplicationGmailMock: vi.fn(),
    ApiErrorMock,
  };
});

vi.mock("../api", () => ({
  getApplication: getApplicationMock,
  getGmailStatus: getGmailStatusMock,
  searchApplicationGmail: searchApplicationGmailMock,
  classifyApplicationGmail: classifyApplicationGmailMock,
  ApiError: ApiErrorMock,
}));

import { GmailEvidence } from "../components/GmailEvidence";
import type { Application } from "../api";

function renderEvidence(
  application: Application,
  onChanged: (a: Application) => void,
) {
  return render(
    <MemoryRouter>
      <GmailEvidence application={application} onApplicationChanged={onChanged} />
    </MemoryRouter>,
  );
}

function baseApp(overrides: Partial<Application> = {}): Application {
  return {
    id: "app-1",
    job_id: "job-1",
    resume_version_id: "version-1",
    status: "submitted",
    submitted_at: "2026-05-22T12:00:00Z",
    created_at: "2026-05-22T10:00:00Z",
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
    gmail_query: null,
    last_gmail_check_at: null,
    last_matched_email_at: null,
    matched_email_count: 0,
    latest_email_subject: null,
    latest_email_from: null,
    latest_email_snippet: null,
    latest_email_classification: null,
    latest_email_confidence: null,
    latest_email_evidence: null,
    ...overrides,
  };
}

describe("GmailEvidence", () => {
  const noop = vi.fn();
  const originalOpen = window.open;

  beforeEach(() => {
    getApplicationMock.mockResolvedValue(baseApp());
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: '("Acme Corp" OR "Senior Engineer") after:2026/5/21',
      count: 0,
      candidates: [],
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
    window.open = vi.fn();
  });

  afterEach(() => {
    window.open = originalOpen;
    vi.clearAllMocks();
  });

  it("renders the privacy note", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });

    renderEvidence(baseApp(), noop);

    expect(
      screen.getByText(
        /gmail is used read-only for application tracking\. jobapplicator does not send, delete, archive, or label emails\./i,
      ),
    ).toBeInTheDocument();
  });

  it("directs the user to Settings when Gmail is configured but not connected", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });

    renderEvidence(baseApp(), noop);

    await waitFor(() =>
      expect(screen.getByTestId("gmail-connect-hint")).toHaveTextContent(
        /connect gmail in settings/i,
      ),
    );
    // No Connect Gmail button is rendered inside the application detail.
    expect(
      screen.queryByRole("button", { name: /connect gmail/i }),
    ).not.toBeInTheDocument();
    // And no call is made to the /gmail/auth-url endpoint from here.
    const settingsLink = screen
      .getByTestId("gmail-connect-hint")
      .querySelector("a");
    expect(settingsLink?.getAttribute("href")).toBe("/settings");
    expect(screen.getByTestId("gmail-status-line")).toHaveTextContent(
      /not connected/i,
    );
  });

  it("shows the not-configured hint pointing to Settings", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: false,
      missing_config: [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
      ],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });

    renderEvidence(baseApp(), noop);

    await waitFor(() =>
      expect(screen.getByTestId("gmail-connect-hint")).toHaveTextContent(
        /not configured.*configure it in settings/i,
      ),
    );
    expect(
      screen.queryByRole("button", { name: /connect gmail/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("gmail-status-line")).toHaveTextContent(
      /not configured/i,
    );
  });

  it("shows Check Gmail action when connected and not yet checked", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });

    renderEvidence(baseApp(), noop);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /^check gmail$/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId("gmail-status-line")).toHaveTextContent(
      /not checked/i,
    );
  });

  it("calls the search endpoint when Check Gmail is clicked", async () => {
    const user = userEvent.setup();
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });

    const refreshed = baseApp({
      email_status: "no_match",
      last_gmail_check_at: "2026-05-25T12:00:00Z",
    });
    getApplicationMock.mockResolvedValue(refreshed);
    const onChanged = vi.fn();

    renderEvidence(baseApp(), onChanged);

    await user.click(await screen.findByRole("button", { name: /check gmail/i }));

    await waitFor(() =>
      expect(searchApplicationGmailMock).toHaveBeenCalledWith("app-1", {
        max_results: 10,
        include_ats_terms: true,
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(refreshed));
    expect(
      screen.getByText(/no related emails found/i),
    ).toBeInTheDocument();
  });

  it("renders candidate metadata: subject, sender, snippet and matched signals", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: '("Acme Corp") newer_than:180d',
      count: 1,
      candidates: [
        {
          message_id: "msg-1",
          thread_id: "thr-1",
          subject: "Application update from Acme",
          from: "jobs@acme.example",
          date: "Mon, 25 May 2026 12:00:00 +0000",
          snippet: "Thanks for applying — we will not be moving forward.",
          matched_signals: ["company_name", "ats_sender_domain"],
          match_score: 0.78,
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);

    await user.click(await screen.findByRole("button", { name: /check gmail/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Application update from Acme"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("jobs@acme.example")).toBeInTheDocument();
    expect(
      screen.getByText(/thanks for applying — we will not be moving forward/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/matched signals: company_name, ats_sender_domain/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/match score: 0\.78/i)).toBeInTheDocument();
  });

  it("does not render any full-body content for candidates (snippet only)", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: '("Acme Corp") newer_than:180d',
      count: 1,
      candidates: [
        {
          message_id: "msg-1",
          thread_id: "thr-1",
          subject: "S",
          from: "f@example.com",
          date: null,
          snippet: "short snippet only",
          matched_signals: [],
          match_score: 0.5,
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(await screen.findByRole("button", { name: /check gmail/i }));

    await waitFor(() => expect(screen.getByText("S")).toBeInTheDocument());
    // No "body"/"html" UI surface — assert the only candidate text on the page
    // is the snippet (the safe-metadata field).
    const item = screen.getByText("short snippet only").closest("li");
    expect(item).not.toBeNull();
    expect(item!.textContent ?? "").not.toMatch(/<html|<body/i);
  });

  it("calls the classify endpoint and renders evidence with explicit text labels", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: '("Acme Corp") newer_than:180d',
      count: 1,
      candidates: [
        {
          message_id: "msg-1",
          thread_id: "thr-1",
          subject: "Application update",
          from: "jobs@acme.example",
          date: null,
          snippet: "we will not be moving forward",
          matched_signals: ["company_name"],
          match_score: 0.7,
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(await screen.findByRole("button", { name: /check gmail/i }));

    const item = (await screen.findByText("Application update")).closest("li");
    expect(item).not.toBeNull();

    await user.click(
      within(item!).getByRole("button", { name: /^classify$/i }),
    );

    await waitFor(() =>
      expect(classifyApplicationGmailMock).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({ message_id: "msg-1" }),
      ),
    );

    // Classification label rendered as explicit text (not color-only).
    await waitFor(() =>
      expect(
        within(item!).getByText(/classification: rejection/i),
      ).toBeInTheDocument(),
    );
    expect(within(item!).getByText(/confidence: 86%/i)).toBeInTheDocument();
    expect(
      within(item!).getByText(
        /matched rejection phrase in email snippet/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(item!).getAllByText(/we will not be moving forward/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      within(item!).getByText(/application status updated to/i),
    ).toBeInTheDocument();
  });

  it("renders the latest classification summary from application fields", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
    const app = baseApp({
      email_status: "classified_rejection",
      latest_email_subject: "Application update from jobs@acme",
      latest_email_from: "jobs@acme.example",
      latest_email_classification: "rejection",
      latest_email_confidence: 0.73,
      last_gmail_check_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    });

    renderEvidence(app, noop);

    expect(screen.getByTestId("gmail-status-line")).toHaveTextContent(
      /rejection detected/i,
    );
    expect(
      screen.getByText(/application update from jobs@acme/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/jobs@acme\.example/i)).toBeInTheDocument();
    // Explicit text label for the latest classification (uses the
    // classifier-aware vocabulary, not color-only).
    expect(screen.getByText(/^Rejection/)).toBeInTheDocument();
    expect(screen.getByText(/confidence 0\.73/)).toBeInTheDocument();
  });

  it("surfaces an inline error when the search endpoint fails", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
    searchApplicationGmailMock.mockRejectedValue(
      new ApiErrorMock("Request failed with status 500", 500, null),
    );
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(await screen.findByRole("button", { name: /check gmail/i }));

    await waitFor(() => {
      const alerts = screen.getAllByRole("alert");
      const message = alerts.find((el) =>
        /failed with status 500/i.test(el.textContent ?? ""),
      );
      expect(message).toBeDefined();
    });
  });

  it("surfaces an inline error when classification fails", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    });
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: '("Acme")',
      count: 1,
      candidates: [
        {
          message_id: "msg-1",
          thread_id: null,
          subject: "Update",
          from: "x@y.example",
          date: null,
          snippet: "snip",
          matched_signals: [],
          match_score: 0.4,
        },
      ],
    });
    classifyApplicationGmailMock.mockRejectedValue(
      new ApiErrorMock("Could not classify", 500, null),
    );
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(await screen.findByRole("button", { name: /check gmail/i }));
    const item = (await screen.findByText("Update")).closest("li");
    await user.click(
      within(item!).getByRole("button", { name: /^classify$/i }),
    );

    await waitFor(() => {
      const alerts = screen.getAllByRole("alert");
      const message = alerts.find((el) =>
        /could not classify/i.test(el.textContent ?? ""),
      );
      expect(message).toBeDefined();
    });
  });
});
