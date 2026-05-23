import { apiRequest } from "./client";
import type {
  Application,
  ClaudeRun,
  EvidenceBank,
  EvidenceBankCreate,
  Job,
  JobCapture,
  MasterResume,
  MasterResumeCreate,
  ResumeVersion,
} from "./types";

export { API_BASE, ApiError } from "./client";
export type {
  Application,
  ClaudeRun,
  EvidenceBank,
  EvidenceBankCreate,
  Job,
  JobCapture,
  MasterResume,
  MasterResumeCreate,
  ResumeVersion,
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

export function listApplications(): Promise<Application[]> {
  return apiRequest("/applications");
}

export function getApplication(applicationId: string): Promise<Application> {
  return apiRequest(`/applications/${applicationId}`);
}
