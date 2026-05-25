import { apiRequest } from "./client";
import type {
  Application,
  ApplicationCreate,
  ApplicationEvent,
  ApplicationEventCreate,
  ClaudeRun,
  EvidenceBank,
  EvidenceBankCreate,
  Job,
  JobCapture,
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
  EvidenceBank,
  EvidenceBankCreate,
  Job,
  JobCapture,
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
