import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
  getGmailAuthUrlMock,
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
    getGmailAuthUrlMock: vi.fn(),
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
  getGmailAuthUrl: getGmailAuthUrlMock,
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

const job = {
  id: "job-1",
  source_platform: "linkedin",
  external_url: null,
  external_job_id: null,
  company: "Example Aero Labs",
  title: "Scientific Machine Learning Engineer",
  location: null,
  description_text: "",
  application_method: null,
  created_from_capture_id: null,
  created_at: "2026-05-22T10:00:00Z",
  updated_at: "2026-05-22T10:00:00Z",
};

const application = {
  id: "app-1",
  job_id: "job-1",
  resume_version_id: null,
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
};

describe("ApplicationsPage Sync Gmail", () => {
  beforeEach(() => {
    listApplicationsMock.mockResolvedValue([application]);
    listJobsMock.mockResolvedValue([job]);
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

  it("shows a 'Connect Gmail in Settings' hint when Gmail is configured but not connected", async () => {
    getGmailStatusMock.mockResolvedValue({
      connected: false,
      configured: true,
      missing_config: [],
      email: null,
      scopes: [],
      token_path_configured: true,
      last_checked_at: null,
    });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId("sync-gmail-hint")).toHaveTextContent(
        /connect gmail in settings/i,
      ),
    );
    expect(getGmailAuthUrlMock).not.toHaveBeenCalled();
  });

  it("shows a 'not configured / open Settings' hint when Gmail OAuth env vars are missing", async () => {
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
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId("sync-gmail-hint")).toHaveTextContent(
        /not configured.*open settings/i,
      ),
    );
  });

  it("renders a Sync Gmail button", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /sync gmail/i }),
    ).toBeInTheDocument();
  });

  it("calls the sync endpoint when Sync Gmail is clicked", async () => {
    syncApplicationsGmailMock.mockResolvedValue({
      gmail_connected: true,
      checked_count: 1,
      updated_count: 0,
      no_match_count: 1,
      needs_review_count: 0,
      results: [
        {
          application_id: "app-1",
          job_title: "Scientific Machine Learning Engineer",
          company: "Example Aero Labs",
          previous_email_status: "watching",
          new_email_status: "no_match",
          previous_application_status: "submitted",
          new_application_status: "submitted",
          matched_email_count: 0,
          classification: null,
          confidence: null,
          evidence: [],
          application_status_changed: false,
          gmail_query: "(\"Example Aero Labs\") newer_than:180d",
          skipped_reason: null,
        },
      ],
    });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sync gmail/i }),
    );
    expect(syncApplicationsGmailMock).toHaveBeenCalledTimes(1);
  });

  it("renders a loading state while syncing", async () => {
    let resolve: ((value: unknown) => void) | undefined;
    syncApplicationsGmailMock.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sync gmail/i }),
    );
    expect(screen.getByRole("button", { name: /syncing gmail/i })).toBeDisabled();
    resolve?.({
      gmail_connected: true,
      checked_count: 0,
      updated_count: 0,
      no_match_count: 0,
      needs_review_count: 0,
      results: [],
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /sync gmail/i }),
      ).not.toBeDisabled(),
    );
  });

  it("renders summary counts after sync", async () => {
    syncApplicationsGmailMock.mockResolvedValue({
      gmail_connected: true,
      checked_count: 3,
      updated_count: 1,
      no_match_count: 1,
      needs_review_count: 1,
      results: [
        {
          application_id: "app-1",
          job_title: "Scientific Machine Learning Engineer",
          company: "Example Aero Labs",
          previous_email_status: "watching",
          new_email_status: "classified_rejection",
          previous_application_status: "submitted",
          new_application_status: "rejected",
          matched_email_count: 1,
          classification: "rejection",
          confidence: 0.86,
          evidence: [
            {
              field: "snippet",
              text: "not moving forward",
              reason: "contains rejection phrase",
            },
          ],
          application_status_changed: true,
          gmail_query: "...",
          skipped_reason: null,
        },
      ],
    });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sync gmail/i }),
    );
    await waitFor(() =>
      expect(screen.getByText(/Checked 3 applications/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Updated 1/i)).toBeInTheDocument();
    expect(screen.getByText(/No match 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Needs review 1/i)).toBeInTheDocument();
    expect(screen.getByText(/not moving forward/i)).toBeInTheDocument();
  });

  it("shows a Gmail disconnected message when not connected", async () => {
    syncApplicationsGmailMock.mockResolvedValue({
      gmail_connected: false,
      checked_count: 0,
      updated_count: 0,
      no_match_count: 0,
      needs_review_count: 0,
      results: [],
      message: "Connect Gmail before syncing applications",
    });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sync gmail/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByText(/Connect Gmail before syncing applications/i),
      ).toBeInTheDocument(),
    );
  });

  it("refreshes the applications list after a successful sync", async () => {
    syncApplicationsGmailMock.mockResolvedValue({
      gmail_connected: true,
      checked_count: 1,
      updated_count: 1,
      no_match_count: 0,
      needs_review_count: 0,
      results: [
        {
          application_id: "app-1",
          job_title: "Scientific Machine Learning Engineer",
          company: "Example Aero Labs",
          previous_email_status: "watching",
          new_email_status: "classified_rejection",
          previous_application_status: "submitted",
          new_application_status: "rejected",
          matched_email_count: 1,
          classification: "rejection",
          confidence: 0.86,
          evidence: [],
          application_status_changed: true,
          gmail_query: "...",
          skipped_reason: null,
        },
      ],
    });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: /applications/i }),
      ).toBeInTheDocument(),
    );
    listApplicationsMock.mockClear();
    await userEvent.click(
      screen.getByRole("button", { name: /sync gmail/i }),
    );
    await waitFor(() => expect(listApplicationsMock).toHaveBeenCalledTimes(1));
  });
});
