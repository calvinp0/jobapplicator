import { apiRequest } from "./client";
import type {
  Application,
  ApplicationCreate,
  ApplicationEvent,
  ApplicationEventCreate,
  ClaudeRun,
  EmailLink,
  EmailLinkCreatePayload,
  EvidenceBank,
  EvidenceBankCreate,
  GmailAuthUrlResponse,
  GmailCandidateEmail,
  GmailClassificationResponse,
  GmailEvidenceItem,
  GmailSearchResponse,
  GmailStatusResponse,
  Job,
  JobCapture,
  LlmProvider,
  LlmProviderSetting,
  MasterResume,
  MasterResumeCreate,
  ResumeVersion,
  RevisionFeedback,
  RevisionFeedbackCreate,
  RunLog,
  RunProgress,
  WordHandoffMetadata,
  WordHandoffTextRead,
  WordResultImportResponse,
} from "./types";

export { API_BASE, ApiError } from "./client";
export type {
  Application,
  ApplicationCreate,
  ApplicationEvent,
  ApplicationEventCreate,
  ClaudeRun,
  EmailLink,
  EmailLinkCreatePayload,
  EvidenceBank,
  EvidenceBankCreate,
  GmailAuthUrlResponse,
  GmailCandidateEmail,
  GmailClassificationResponse,
  GmailEvidenceItem,
  GmailSearchResponse,
  GmailStatusResponse,
  Job,
  JobCapture,
  LlmProvider,
  LlmProviderSetting,
  MasterResume,
  MasterResumeCreate,
  ResumeVersion,
  RevisionFeedback,
  RevisionFeedbackCreate,
  RunLog,
  RunProgress,
  WordHandoffMetadata,
  WordHandoffTextRead,
  WordResultImportResponse,
};

export function getHealth(): Promise<{ status: string }> {
  return apiRequest("/health");
}

export function listCaptures(): Promise<JobCapture[]> {
  return apiRequest("/captures");
}

export function getCapture(captureId: string): Promise<JobCapture> {
  return apiRequest(`/captures/${captureId}`);
}

export function confirmCapture(captureId: string): Promise<Job> {
  return apiRequest(`/captures/${captureId}/confirm`, { method: "POST" });
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

export interface CreateRunPayload {
  job_id: string;
  master_resume_id: string;
  evidence_bank_id?: string | null;
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

export function importRun(runId: string): Promise<ResumeVersion> {
  return apiRequest(`/runs/${runId}/import`, { method: "POST" });
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

export function createWordHandoff(runId: string): Promise<WordHandoffMetadata> {
  return apiRequest(`/runs/${runId}/word-handoff`, { method: "POST" });
}

export function getWordHandoff(runId: string): Promise<WordHandoffMetadata> {
  return apiRequest(`/runs/${runId}/word-handoff`);
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
