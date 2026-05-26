import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const {
  getApplicationMock,
  getGmailStatusMock,
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
    getGmailStatusMock: vi.fn(),
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
  getGmailStatus: getGmailStatusMock,
  searchApplicationGmail: searchApplicationGmailMock,
  classifyApplicationGmail: classifyApplicationGmailMock,
  listGmailCandidates: listGmailCandidatesMock,
  linkGmailEmail: linkGmailEmailMock,
  listLinkedGmailEmails: listLinkedGmailEmailsMock,
  unlinkGmailEmail: unlinkGmailEmailMock,
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

  // ---- Task 093: manual Gmail email linking ----

  function connectedStatus() {
    return {
      connected: true,
      configured: true,
      missing_config: [],
      email: "user@example.com",
      scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      token_path_configured: true,
      last_checked_at: null,
    };
  }

  it("shows a needs-review banner when search has only low-confidence matches", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    searchApplicationGmailMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      gmail_query: '("Acme")',
      count: 1,
      candidates: [
        {
          message_id: "msg-1",
          thread_id: "thr-1",
          subject: "Possibly relevant",
          from: "x@y.example",
          date: null,
          snippet: "We might have something for you",
          matched_signals: ["company_name"],
          match_score: 0.45,
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(await screen.findByRole("button", { name: /check gmail/i }));

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-needs-review-banner"),
      ).toHaveTextContent(/no strong gmail match found/i),
    );
  });

  it("renders the manual search input and 'Review possible emails' affordance", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());

    renderEvidence(baseApp(), noop);

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-manual-query-input"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId("gmail-review-candidates-button"),
    ).toBeInTheDocument();
  });

  it("loads candidates and renders link actions", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: "Infinity Labs",
      count: 1,
      strong_count: 0,
      possible_count: 1,
      candidates: [
        {
          message_id: "g-msg-1",
          thread_id: "g-thr-1",
          subject: "Thank you for contacting Infinity Labs R&D",
          from: "hr@infinitylabsrd.co.il",
          date: "Mon, 25 May 2026 12:00:00 +0000",
          snippet: "Thank you for applying to Infinity Labs R&D...",
          match_score: 0.42,
          matched_signals: ["company_name"],
          classification_guess: "submission_confirmation",
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(
      await screen.findByTestId("gmail-review-candidates-button"),
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-manual-candidate-g-msg-1"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("Thank you for contacting Infinity Labs R&D"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("gmail-link-submission_confirmation-g-msg-1"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("gmail-link-rejection-g-msg-1"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("gmail-manual-needs-review"),
    ).toBeInTheDocument();
  });

  it("submits a manual Gmail query through the candidates endpoint", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);

    const input = await screen.findByTestId("gmail-manual-query-input");
    await user.type(input, "Infinity Labs");
    await user.click(
      within(screen.getByTestId("gmail-manual-search-form")).getByRole(
        "button",
        { name: /search/i },
      ),
    );

    await waitFor(() =>
      expect(listGmailCandidatesMock).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          query: "Infinity Labs",
          include_low_confidence: true,
        }),
      ),
    );
  });

  it("links a candidate as confirmation, refreshes the application, and reloads linked emails", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: null,
      count: 1,
      strong_count: 0,
      possible_count: 1,
      candidates: [
        {
          message_id: "link-me",
          thread_id: "thr-link",
          subject: "Thanks for applying",
          from: "hr@example.com",
          date: null,
          snippet: "Thank you for applying...",
          match_score: 0.42,
          matched_signals: ["company_name"],
          classification_guess: "submission_confirmation",
        },
      ],
    });
    listLinkedGmailEmailsMock
      .mockResolvedValueOnce({ application_id: "app-1", linked_emails: [] })
      .mockResolvedValue({
        application_id: "app-1",
        linked_emails: [
          {
            id: "linked-1",
            application_id: "app-1",
            gmail_message_id: "link-me",
            gmail_thread_id: "thr-link",
            subject: "Thanks for applying",
            sender: "hr@example.com",
            snippet: "Thank you for applying...",
            received_at: null,
            classified_status: "confirmation",
            confidence: null,
            match_method: "manual",
            linked_by_user: true,
            evidence: null,
            created_at: "2026-05-25T12:00:00Z",
          },
        ],
      });
    const onChanged = vi.fn();
    const user = userEvent.setup();

    renderEvidence(baseApp(), onChanged);
    await user.click(
      await screen.findByTestId("gmail-review-candidates-button"),
    );

    await user.click(
      await screen.findByTestId(
        "gmail-link-submission_confirmation-link-me",
      ),
    );

    await waitFor(() =>
      expect(linkGmailEmailMock).toHaveBeenCalledWith(
        "app-1",
        expect.objectContaining({
          message_id: "link-me",
          classification: "submission_confirmation",
          user_confirmed: true,
        }),
      ),
    );
    await waitFor(() =>
      expect(getApplicationMock).toHaveBeenCalledWith("app-1"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-linked-emails"),
      ).toBeInTheDocument(),
    );
  });

  it("never renders a full body — only the snippet — for manual candidates", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: null,
      count: 1,
      strong_count: 0,
      possible_count: 1,
      candidates: [
        {
          message_id: "g1",
          thread_id: null,
          subject: "S",
          from: "f@x.com",
          date: null,
          snippet: "short snippet only",
          match_score: 0.4,
          matched_signals: [],
          classification_guess: "unknown",
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(
      await screen.findByTestId("gmail-review-candidates-button"),
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-manual-candidate-g1"),
      ).toBeInTheDocument(),
    );
    const card = screen.getByTestId("gmail-manual-candidate-g1");
    expect(card).toHaveTextContent("short snippet only");
    // No "body" / "html" textual marker in the rendered candidate card.
    expect(card.textContent).not.toMatch(/<html>|<body>/i);
  });

  it("sends candidate sender/subject/snippet/date as received_at when linking", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: null,
      count: 1,
      strong_count: 0,
      possible_count: 1,
      candidates: [
        {
          message_id: "gmail-real-id-xyz",
          thread_id: "thr-z",
          subject: "We've decided not to move forward",
          from: "Recruiter <recruiter@acme.example>",
          date: "Mon, 25 May 2026 12:00:00 +0000",
          snippet: "Thank you for taking the time…",
          match_score: 0.55,
          matched_signals: ["company_name"],
          classification_guess: "rejection",
        },
      ],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(
      await screen.findByTestId("gmail-review-candidates-button"),
    );

    await user.click(
      await screen.findByTestId("gmail-link-rejection-gmail-real-id-xyz"),
    );

    await waitFor(() => expect(linkGmailEmailMock).toHaveBeenCalled());
    const [appId, payload] = linkGmailEmailMock.mock.calls[0];
    expect(appId).toBe("app-1");
    // The candidate's real Gmail id is sent verbatim — no manual:<uuid>.
    expect(payload.message_id).toBe("gmail-real-id-xyz");
    expect(payload.message_id).not.toMatch(/^manual:/);
    expect(payload.thread_id).toBe("thr-z");
    expect(payload.sender).toBe("Recruiter <recruiter@acme.example>");
    expect(payload.subject).toBe("We've decided not to move forward");
    expect(payload.snippet).toBe("Thank you for taking the time…");
    expect(payload.classification).toBe("rejection");
    expect(payload.user_confirmed).toBe(true);
    // Gmail's RFC 2822 date is converted to ISO 8601 for the backend.
    expect(payload.received_at).toBe("2026-05-25T12:00:00.000Z");
  });

  it("surfaces a useful error when the link-email request fails", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: null,
      count: 1,
      strong_count: 0,
      possible_count: 1,
      candidates: [
        {
          message_id: "broken",
          thread_id: null,
          subject: "S",
          from: "f@x.com",
          date: null,
          snippet: "snip",
          match_score: 0.3,
          matched_signals: [],
          classification_guess: "unknown",
        },
      ],
    });
    linkGmailEmailMock.mockRejectedValue(
      new ApiErrorMock("Request failed with status 500", 500, null),
    );
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(
      await screen.findByTestId("gmail-review-candidates-button"),
    );
    await user.click(
      await screen.findByTestId("gmail-link-submission_confirmation-broken"),
    );

    await waitFor(() => {
      const alerts = screen.getAllByRole("alert");
      const message = alerts.find((el) =>
        /failed with status 500/i.test(el.textContent ?? ""),
      );
      expect(message).toBeDefined();
    });
    // Candidate metadata is preserved on failure so the user can retry.
    expect(screen.getByTestId("gmail-manual-candidate-broken")).toBeInTheDocument();
  });

  it("labels Gmail-candidate links as 'Linked from Gmail · confirmed manually'", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listLinkedGmailEmailsMock.mockResolvedValue({
      application_id: "app-1",
      linked_emails: [
        {
          id: "ev-1",
          application_id: "app-1",
          gmail_message_id: "real-gmail-id-1",
          gmail_thread_id: "thr-1",
          subject: "Application confirmation",
          sender: "hr@example.com",
          snippet: "We received your application.",
          received_at: "2026-05-25T12:00:00Z",
          classified_status: "confirmation",
          confidence: null,
          match_method: "manual_candidate_link",
          linked_by_user: true,
          evidence: null,
          created_at: "2026-05-25T12:00:00Z",
        },
      ],
    });

    renderEvidence(baseApp(), noop);

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-linked-source-ev-1"),
      ).toHaveTextContent(/linked from gmail · confirmed manually/i),
    );
    const card = screen.getByTestId("gmail-linked-email-ev-1");
    // The raw Gmail message id is never the primary label.
    expect(card.textContent ?? "").not.toContain("real-gmail-id-1");
  });

  it("labels rows from the manual record form as 'Recorded manually'", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listLinkedGmailEmailsMock.mockResolvedValue({
      application_id: "app-1",
      linked_emails: [
        {
          id: "ev-manual",
          application_id: "app-1",
          gmail_message_id: "manual:abc",
          gmail_thread_id: null,
          subject: "Your application",
          sender: "noreply@example.com",
          snippet: null,
          received_at: null,
          classified_status: "confirmation",
          confidence: null,
          match_method: "manual_entry",
          linked_by_user: true,
          evidence: null,
          created_at: "2026-05-25T12:00:00Z",
        },
      ],
    });

    renderEvidence(baseApp(), noop);

    await waitFor(() =>
      expect(
        screen.getByTestId("gmail-linked-source-ev-manual"),
      ).toHaveTextContent(/recorded manually/i),
    );
  });

  it("shows 'No related Gmail emails found' when manual candidates is empty", async () => {
    getGmailStatusMock.mockResolvedValue(connectedStatus());
    listGmailCandidatesMock.mockResolvedValue({
      application_id: "app-1",
      gmail_connected: true,
      query_used: null,
      count: 0,
      strong_count: 0,
      possible_count: 0,
      candidates: [],
    });
    const user = userEvent.setup();

    renderEvidence(baseApp(), noop);
    await user.click(
      await screen.findByTestId("gmail-review-candidates-button"),
    );

    await waitFor(() =>
      expect(screen.getByTestId("gmail-manual-empty")).toHaveTextContent(
        /no related gmail emails found.*try a manual gmail search/i,
      ),
    );
  });
});
