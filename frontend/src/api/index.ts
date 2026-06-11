import { API_BASE, ApiError, apiRequest, apiUpload } from "./client";
import {
  parseContentDispositionFilename,
  triggerBrowserDownload,
} from "../lib/downloads";
import type {
  ActivityItem,
  ActivityResponse,
  ActivitySummary,
  Application,
  ApplicationCreate,
  ApplicationEvent,
  ApplicationEventCreate,
  ClaudeRun,
  EmailLink,
  EmailLinkCreatePayload,
  EvidenceBank,
  EvidenceBankCreate,
  EvidenceSource,
  EvidenceSourceType,
  ExportSettings,
  FileImportResult,
  ResetLocalDataResponse,
  GmailAuthUrlResponse,
  GmailCandidateEmail,
  GmailCandidatesResponse,
  GmailClassificationResponse,
  GmailEvidenceItem,
  GmailLinkedEmailsResponse,
  GmailLinkEmailPayload,
  GmailLinkEmailResponse,
  GmailManualCandidate,
  ManualLinkClassification,
  GmailSearchResponse,
  GmailStatusResponse,
  GmailSyncApplicationResult,
  GmailSyncApplicationsResponse,
  GmailUnlinkResponse,
  GmailOAuthSettings,
  GmailOAuthSettingsUpdate,
  Job,
  JobCapture,
  JobCaptureConfirm,
  LlmProvider,
  LlmProviderSetting,
  LocalLlmModelsResult,
  LocalLlmPullEvent,
  LocalLlmPullRequest,
  LocalLlmSettings,
  LocalLlmSettingsUpdate,
  LocalLlmTaskPolicy,
  LocalLlmTestRequest,
  LocalLlmTestResult,
  MasterResume,
  MasterResumeCreate,
  PromptHarnessDetail,
  PromptHarnessSummary,
  PromptValidationResult,
  ApplySuggestionsResult,
  ResumeSuggestion,
  ResumeSuggestions,
  ResumeVersion,
  RevisionFeedback,
  RevisionFeedbackCreate,
  RecruiterReview,
  RunExport,
  RunExportFile,
  RunLog,
  RunProgress,
  WordHandoffMetadata,
  WordHandoffStatus,
  WordHandoffTextRead,
  WordResultImportResponse,
} from "./types";

export { API_BASE, ApiError } from "./client";
export type {
  ActivityItem,
  ActivityResponse,
  ActivitySummary,
  Application,
  ApplicationCreate,
  ApplicationEvent,
  ApplicationEventCreate,
  ClaudeRun,
  EmailLink,
  EmailLinkCreatePayload,
  EvidenceBank,
  EvidenceBankCreate,
  EvidenceSource,
  EvidenceSourceType,
  ExportSettings,
  FileImportResult,
  ResetLocalDataResponse,
  GmailAuthUrlResponse,
  GmailCandidateEmail,
  GmailCandidatesResponse,
  GmailClassificationResponse,
  GmailEvidenceItem,
  GmailLinkedEmailsResponse,
  GmailLinkEmailPayload,
  GmailLinkEmailResponse,
  GmailManualCandidate,
  ManualLinkClassification,
  GmailSearchResponse,
  GmailStatusResponse,
  GmailSyncApplicationResult,
  GmailSyncApplicationsResponse,
  GmailUnlinkResponse,
  GmailOAuthSettings,
  GmailOAuthSettingsUpdate,
  Job,
  JobCapture,
  JobCaptureConfirm,
  LlmProvider,
  LlmProviderSetting,
  LocalLlmModelsResult,
  LocalLlmPullEvent,
  LocalLlmPullRequest,
  LocalLlmSettings,
  LocalLlmSettingsUpdate,
  LocalLlmTaskPolicy,
  LocalLlmTestRequest,
  LocalLlmTestResult,
  MasterResume,
  MasterResumeCreate,
  PromptHarnessDetail,
  PromptHarnessSummary,
  PromptValidationResult,
  ApplySuggestionsResult,
  ResumeSuggestion,
  ResumeSuggestions,
  ResumeVersion,
  RevisionFeedback,
  RevisionFeedbackCreate,
  RecruiterReview,
  RunExport,
  RunExportFile,
  RunLog,
  RunProgress,
  WordHandoffMetadata,
  WordHandoffStatus,
  WordHandoffTextRead,
  WordResultImportResponse,
};

export function getHealth(): Promise<{ status: string }> {
  return apiRequest("/health");
}

export function getActivity(): Promise<ActivityResponse> {
  return apiRequest("/activity");
}

export function listCaptures(): Promise<JobCapture[]> {
  return apiRequest("/captures");
}

export function getCapture(captureId: string): Promise<JobCapture> {
  return apiRequest(`/captures/${captureId}`);
}

export function confirmCapture(
  captureId: string,
  payload?: JobCaptureConfirm,
): Promise<Job> {
  return apiRequest(`/captures/${captureId}/confirm`, {
    method: "POST",
    body: payload,
  });
}

export function listJobs(): Promise<Job[]> {
  return apiRequest("/jobs");
}

export function getJob(jobId: string): Promise<Job> {
  return apiRequest(`/jobs/${jobId}`);
}

export function listMasterResumes(): Promise<MasterResume[]> {
  return apiRequest("/master-resumes");
}

export function createMasterResume(
  payload: MasterResumeCreate,
): Promise<MasterResume> {
  return apiRequest("/master-resumes", { method: "POST", body: payload });
}

export function listEvidenceBanks(): Promise<EvidenceBank[]> {
  return apiRequest("/evidence-banks");
}

export function createEvidenceBank(
  payload: EvidenceBankCreate,
): Promise<EvidenceBank> {
  return apiRequest("/evidence-banks", { method: "POST", body: payload });
}

export function listEvidenceSources(): Promise<EvidenceSource[]> {
  return apiRequest("/evidence-sources");
}

export function importMasterResumeFile(
  file: File,
): Promise<FileImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiUpload("/master-resumes/import-file", form);
}

export function importEvidenceSourceFile(
  file: File,
): Promise<FileImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiUpload("/evidence-sources/import-file", form);
}

export function resetLocalData(
  confirmation: string,
): Promise<ResetLocalDataResponse> {
  return apiRequest("/settings/reset-local-data", {
    method: "POST",
    body: { confirmation },
  });
}

export interface CreateRunPayload {
  job_id: string;
  master_resume_id: string;
  evidence_bank_id?: string | null;
  evidence_source_ids?: string[];
  llm_provider?: string;
}

export function createRun(payload: CreateRunPayload): Promise<ClaudeRun> {
  return apiRequest("/runs", { method: "POST", body: payload });
}

export function listRuns(): Promise<ClaudeRun[]> {
  return apiRequest("/runs");
}

export function getRun(runId: string): Promise<ClaudeRun> {
  return apiRequest(`/runs/${runId}`);
}

export function invokeRun(runId: string): Promise<ClaudeRun> {
  return apiRequest(`/runs/${runId}/invoke`, { method: "POST" });
}

export function getRunLog(runId: string): Promise<RunLog> {
  return apiRequest(`/runs/${runId}/log`);
}

export function getRunProgress(runId: string): Promise<RunProgress> {
  return apiRequest(`/runs/${runId}/progress`);
}

export function getRunRecruiterReview(
  runId: string,
): Promise<RecruiterReview> {
  return apiRequest(`/runs/${runId}/recruiter-review`);
}

export function importRun(runId: string): Promise<ResumeVersion> {
  return apiRequest(`/runs/${runId}/import`, { method: "POST" });
}

// ---- Resume export / download (task 122) ----

/**
 * Download a known run artifact (DOCX, markdown, audit). The backend sets a
 * ``Content-Disposition: attachment`` header with the human-readable
 * filename, which we honour when saving. Throws {@link ApiError} on a
 * missing/forbidden artifact so callers can surface a clear error.
 */
export async function downloadRunArtifact(
  runId: string,
  artifactName: string,
): Promise<void> {
  const path = `/runs/${runId}/artifacts/${encodeURIComponent(
    artifactName,
  )}/download`;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "*/*" },
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(
      `Request to ${path} failed with status ${response.status}`,
      response.status,
      body,
    );
  }
  const blob = await response.blob();
  const filename =
    parseContentDispositionFilename(
      response.headers.get("content-disposition"),
    ) ?? artifactName;
  triggerBrowserDownload(blob, filename);
}

/** Download the tailored resume DOCX — the headline run output. */
export function downloadRunResume(runId: string): Promise<void> {
  return downloadRunArtifact(runId, "tailored_resume.docx");
}

/** Copy a run's artifacts into the managed exports folder. */
export function exportRun(runId: string): Promise<RunExport> {
  return apiRequest(`/runs/${runId}/export`, { method: "POST" });
}

/** Read the app-managed exports folder path shown on the Settings page. */
export function getExportSettings(): Promise<ExportSettings> {
  return apiRequest("/settings/exports");
}

export function listResumeVersions(): Promise<ResumeVersion[]> {
  return apiRequest("/resume-versions");
}

export function getResumeVersion(versionId: string): Promise<ResumeVersion> {
  return apiRequest(`/resume-versions/${versionId}`);
}

export function approveResumeVersion(
  versionId: string,
): Promise<ResumeVersion> {
  return apiRequest(`/resume-versions/${versionId}/approve`, { method: "POST" });
}

export function openResumeVersionFile(versionId: string): Promise<void> {
  return apiRequest(`/files/open`, {
    method: "POST",
    body: { resume_version_id: versionId },
  });
}

export function submitRevisionFeedback(
  versionId: string,
  body: RevisionFeedbackCreate,
): Promise<RevisionFeedback> {
  return apiRequest(`/resume-versions/${versionId}/revision-feedback`, {
    method: "POST",
    body,
  });
}

export function listRevisionFeedbacks(): Promise<RevisionFeedback[]> {
  return apiRequest("/revision-feedbacks");
}

// ---- Resume suggestion review (task 113) ----

export function getResumeSuggestions(
  versionId: string,
): Promise<ResumeSuggestions> {
  return apiRequest(`/resume-versions/${versionId}/suggestions`);
}

export function acceptSuggestion(
  versionId: string,
  suggestionId: string,
): Promise<ResumeSuggestion> {
  return apiRequest(
    `/resume-versions/${versionId}/suggestions/${suggestionId}/accept`,
    { method: "POST" },
  );
}

export function rejectSuggestion(
  versionId: string,
  suggestionId: string,
): Promise<ResumeSuggestion> {
  return apiRequest(
    `/resume-versions/${versionId}/suggestions/${suggestionId}/reject`,
    { method: "POST" },
  );
}

export function reviseSuggestion(
  versionId: string,
  suggestionId: string,
  instruction: string,
): Promise<ResumeSuggestion> {
  return apiRequest(
    `/resume-versions/${versionId}/suggestions/${suggestionId}/revise`,
    { method: "POST", body: { instruction } },
  );
}

export function applyResumeSuggestions(
  versionId: string,
): Promise<ApplySuggestionsResult> {
  return apiRequest(`/resume-versions/${versionId}/apply-suggestions`, {
    method: "POST",
  });
}

export function createWordHandoff(runId: string): Promise<WordHandoffMetadata> {
  return apiRequest(`/runs/${runId}/word-handoff`, { method: "POST" });
}

export function getWordHandoff(runId: string): Promise<WordHandoffMetadata> {
  return apiRequest(`/runs/${runId}/word-handoff`);
}

export function getWordHandoffStatus(
  runId: string,
): Promise<WordHandoffStatus> {
  return apiRequest(`/runs/${runId}/word-handoff/status`);
}

export function getWordHandoffPrompt(
  runId: string,
): Promise<WordHandoffTextRead> {
  return apiRequest(`/runs/${runId}/word-handoff/prompt`);
}

export function getWordHandoffInstructions(
  runId: string,
): Promise<WordHandoffTextRead> {
  return apiRequest(`/runs/${runId}/word-handoff/instructions`);
}

export function importWordResult(
  runId: string,
): Promise<WordResultImportResponse> {
  return apiRequest(`/runs/${runId}/import-word-result`, { method: "POST" });
}

export function listLlmProviders(): Promise<LlmProvider[]> {
  return apiRequest("/llm-providers");
}

export function listPromptHarnesses(): Promise<PromptHarnessSummary[]> {
  return apiRequest("/prompts");
}

export function getPromptHarness(promptId: string): Promise<PromptHarnessDetail> {
  return apiRequest(`/prompts/${promptId}`);
}

export function savePromptOverride(
  promptId: string,
  content: string,
): Promise<PromptHarnessDetail> {
  return apiRequest(`/prompts/${promptId}/override`, {
    method: "PUT",
    body: { content },
  });
}

export function deletePromptOverride(
  promptId: string,
): Promise<PromptHarnessDetail> {
  return apiRequest(`/prompts/${promptId}/override`, { method: "DELETE" });
}

export function validatePromptHarness(
  promptId: string,
): Promise<PromptValidationResult> {
  return apiRequest(`/prompts/${promptId}/validate`, { method: "POST" });
}

export function getLlmProviderSetting(): Promise<LlmProviderSetting> {
  return apiRequest("/settings/llm-provider");
}

export function setLlmProviderSetting(
  defaultProvider: string,
): Promise<LlmProviderSetting> {
  return apiRequest("/settings/llm-provider", {
    method: "PUT",
    body: { default_provider: defaultProvider },
  });
}

export function getLocalLlmSettings(): Promise<LocalLlmSettings> {
  return apiRequest("/settings/local-llm");
}

export function setLocalLlmSettings(
  payload: LocalLlmSettingsUpdate,
): Promise<LocalLlmSettings> {
  return apiRequest("/settings/local-llm", { method: "PUT", body: payload });
}

export function testLocalLlmConnection(
  payload: LocalLlmTestRequest = {},
): Promise<LocalLlmTestResult> {
  return apiRequest("/llm/local/test-connection", {
    method: "POST",
    body: payload,
  });
}

/**
 * List the models installed on the configured local endpoint (task 135).
 *
 * Optional ``base_url`` / ``provider`` overrides mirror the connection-test
 * override rule, so the UI can list models for unsaved edits before saving.
 * Installed-model listing is Ollama-native only; for the OpenAI-compatible
 * provider the call returns ``ok = false`` with ``error_kind = "unsupported"``.
 */
export function listLocalLlmModels(
  overrides: { base_url?: string | null; provider?: string | null } = {},
): Promise<LocalLlmModelsResult> {
  const params = new URLSearchParams();
  if (overrides.base_url) params.set("base_url", overrides.base_url);
  if (overrides.provider) params.set("provider", overrides.provider);
  const query = params.toString();
  return apiRequest(`/llm/local/models${query ? `?${query}` : ""}`);
}

/**
 * Explicitly pull (install) a model on the configured Ollama server (task 137).
 *
 * This is the only path that triggers a model pull — it never fires as a side
 * effect of any other flow, and the UI (task 139) gates it behind a
 * confirmation dialog. Pulling is Ollama-native only; a non-Ollama provider is
 * refused with HTTP 409 (surfaced as an {@link ApiError}).
 *
 * The backend streams newline-delimited JSON (NDJSON): an ``advisory`` line
 * first (disk/VRAM fit is unknown), one ``progress`` line per server update,
 * and a final ``result`` line. Each parsed event is delivered to ``onEvent`` as
 * it arrives so the caller can render live progress. Resolves once the stream
 * ends; rejects (without emitting events) when the request itself fails.
 */
export async function pullLocalLlmModel(
  payload: LocalLlmPullRequest,
  onEvent: (event: LocalLlmPullEvent) => void,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const path = "/llm/local/pull";
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/x-ndjson",
    },
    body: JSON.stringify(payload),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(
      `Request to ${path} failed with status ${response.status}`,
      response.status,
      body,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      onEvent(JSON.parse(trimmed) as LocalLlmPullEvent);
    } catch {
      // Ignore a malformed line rather than abort the whole pull stream.
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex >= 0) {
      flushLine(buffer.slice(0, newlineIndex));
      buffer = buffer.slice(newlineIndex + 1);
      newlineIndex = buffer.indexOf("\n");
    }
  }
  buffer += decoder.decode();
  flushLine(buffer);
}

export function listApplications(): Promise<Application[]> {
  return apiRequest("/applications");
}

export function getApplication(applicationId: string): Promise<Application> {
  return apiRequest(`/applications/${applicationId}`);
}

export function createApplication(
  payload: ApplicationCreate,
): Promise<Application> {
  return apiRequest("/applications", { method: "POST", body: payload });
}

export function submitApplication(
  applicationId: string,
): Promise<Application> {
  return apiRequest(`/applications/${applicationId}/submit`, {
    method: "POST",
  });
}

export function markApplicationRejected(
  applicationId: string,
): Promise<Application> {
  return apiRequest(`/applications/${applicationId}/mark-rejected`, {
    method: "POST",
  });
}

export function markApplicationInterview(
  applicationId: string,
): Promise<Application> {
  return apiRequest(`/applications/${applicationId}/mark-interview`, {
    method: "POST",
  });
}

export function listApplicationEvents(
  applicationId: string,
): Promise<ApplicationEvent[]> {
  return apiRequest(`/applications/${applicationId}/events`);
}

export function createApplicationEvent(
  applicationId: string,
  payload: ApplicationEventCreate,
): Promise<ApplicationEvent> {
  return apiRequest(`/applications/${applicationId}/events`, {
    method: "POST",
    body: payload,
  });
}

export function getGmailStatus(): Promise<GmailStatusResponse> {
  return apiRequest("/gmail/status");
}

export function getGmailAuthUrl(): Promise<GmailAuthUrlResponse> {
  return apiRequest("/gmail/auth-url");
}

export function getGmailOAuthSettings(): Promise<GmailOAuthSettings> {
  return apiRequest("/settings/gmail-oauth");
}

export function setGmailOAuthSettings(
  payload: GmailOAuthSettingsUpdate,
): Promise<GmailOAuthSettings> {
  return apiRequest("/settings/gmail-oauth", { method: "PUT", body: payload });
}

export function deleteGmailOAuthSettings(): Promise<GmailOAuthSettings> {
  return apiRequest("/settings/gmail-oauth", { method: "DELETE" });
}

export interface SearchApplicationGmailPayload {
  max_results?: number;
  extra_terms?: string[];
  include_ats_terms?: boolean;
}

export function searchApplicationGmail(
  applicationId: string,
  payload: SearchApplicationGmailPayload = {},
): Promise<GmailSearchResponse> {
  const body = {
    max_results: payload.max_results ?? 10,
    include_ats_terms:
      payload.include_ats_terms === undefined
        ? true
        : payload.include_ats_terms,
    extra_terms: payload.extra_terms ?? [],
  };
  return apiRequest(`/applications/${applicationId}/gmail/search`, {
    method: "POST",
    body,
  });
}

export interface SyncApplicationsGmailPayload {
  max_applications?: number;
  max_results_per_application?: number;
  classify?: boolean;
  include_terminal?: boolean;
}

export function syncApplicationsGmail(
  payload: SyncApplicationsGmailPayload = {},
): Promise<GmailSyncApplicationsResponse> {
  const body: Record<string, unknown> = {};
  if (payload.max_applications !== undefined)
    body.max_applications = payload.max_applications;
  if (payload.max_results_per_application !== undefined)
    body.max_results_per_application = payload.max_results_per_application;
  if (payload.classify !== undefined) body.classify = payload.classify;
  if (payload.include_terminal !== undefined)
    body.include_terminal = payload.include_terminal;
  return apiRequest("/gmail/sync-applications", {
    method: "POST",
    body,
  });
}

export function classifyApplicationGmail(
  applicationId: string,
  candidate: GmailCandidateEmail,
): Promise<GmailClassificationResponse> {
  return apiRequest(`/applications/${applicationId}/gmail/classify`, {
    method: "POST",
    body: { candidate },
  });
}

export function listApplicationEmailLinks(
  applicationId: string,
): Promise<EmailLink[]> {
  return apiRequest(`/applications/${applicationId}/email-links`);
}

export function createApplicationEmailLink(
  applicationId: string,
  payload: EmailLinkCreatePayload,
): Promise<EmailLink> {
  return apiRequest(`/applications/${applicationId}/email-links`, {
    method: "POST",
    body: payload,
  });
}

// ---- Task 093: manual Gmail email linking --------------------------

export interface ListGmailCandidatesPayload {
  query?: string | null;
  max_results?: number;
  include_low_confidence?: boolean;
}

export function listGmailCandidates(
  applicationId: string,
  payload: ListGmailCandidatesPayload = {},
): Promise<GmailCandidatesResponse> {
  const body: Record<string, unknown> = {
    include_low_confidence:
      payload.include_low_confidence === undefined
        ? true
        : payload.include_low_confidence,
    max_results: payload.max_results ?? 20,
  };
  if (payload.query !== undefined && payload.query !== null) {
    body.query = payload.query;
  }
  return apiRequest(`/applications/${applicationId}/gmail/candidates`, {
    method: "POST",
    body,
  });
}

export function linkGmailEmail(
  applicationId: string,
  payload: GmailLinkEmailPayload,
): Promise<GmailLinkEmailResponse> {
  return apiRequest(`/applications/${applicationId}/gmail/link-email`, {
    method: "POST",
    body: payload,
  });
}

export function listLinkedGmailEmails(
  applicationId: string,
): Promise<GmailLinkedEmailsResponse> {
  return apiRequest(`/applications/${applicationId}/gmail/linked-emails`);
}

export function unlinkGmailEmail(
  applicationId: string,
  linkedEmailId: string,
): Promise<GmailUnlinkResponse> {
  return apiRequest(
    `/applications/${applicationId}/gmail/linked-emails/${linkedEmailId}`,
    { method: "DELETE" },
  );
}
