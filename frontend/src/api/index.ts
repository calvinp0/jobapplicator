import { apiRequest } from "./client";
import type {
  Application,
  ClaudeRun,
  EvidenceBank,
  Job,
  JobCapture,
  MasterResume,
} from "./types";

export { API_BASE, ApiError } from "./client";
export type {
  Application,
  ClaudeRun,
  EvidenceBank,
  Job,
  JobCapture,
  MasterResume,
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

export function listEvidenceBanks(): Promise<EvidenceBank[]> {
  return apiRequest("/evidence-banks");
}

export function listRuns(): Promise<ClaudeRun[]> {
  return apiRequest("/runs");
}

export function listApplications(): Promise<Application[]> {
  return apiRequest("/applications");
}

export function getApplication(applicationId: string): Promise<Application> {
  return apiRequest(`/applications/${applicationId}`);
}
