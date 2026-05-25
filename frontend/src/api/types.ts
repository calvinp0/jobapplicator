export interface JobCapture {
  id: string;
  source_platform: string;
  capture_method: string;
  external_url: string | null;
  external_job_id: string | null;
  company: string | null;
  title: string | null;
  location: string | null;
  description_text: string;
  application_method: string | null;
  raw_text: string | null;
  captured_at: string;
  user_confirmed: boolean;
  created_at: string;
  job_id: string | null;
}

export interface Job {
  id: string;
  source_platform: string;
  external_url: string | null;
  external_job_id: string | null;
  company: string;
  title: string;
  location: string | null;
  description_text: string;
  application_method: string | null;
  created_from_capture_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MasterResume {
  id: string;
  name: string;
  source_path: string | null;
  content_markdown: string;
  created_at: string;
  updated_at: string;
}

export interface MasterResumeCreate {
  name: string;
  source_path?: string | null;
  content_markdown: string;
}

export interface EvidenceBank {
  id: string;
  name: string;
  source_path: string | null;
  content_markdown: string;
  created_at: string;
  updated_at: string;
}

export interface EvidenceBankCreate {
  name: string;
  source_path?: string | null;
  content_markdown: string;
}

export interface ClaudeRun {
  id: string;
  job_id: string;
  master_resume_id: string;
  evidence_bank_id: string | null;
  run_dir: string;
  status: string;
  prompt_hash: string | null;
  input_hash: string | null;
  output_hash: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface RunLog {
  run_id: string;
  lines: string[];
  truncated: boolean;
}

export interface RunProgress {
  run_id: string;
  lines: string[];
  truncated: boolean;
}

export interface ResumeVersion {
  id: string;
  job_id: string;
  master_resume_id: string;
  claude_run_id: string | null;
  version_number: number;
  content_markdown: string | null;
  docx_path: string | null;
  pdf_path: string | null;
  content_hash: string | null;
  prompt_hash: string | null;
  source: string;
  approved_at: string | null;
  created_at: string;
}

export interface Application {
  id: string;
  job_id: string;
  resume_version_id: string | null;
  status: string;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationCreate {
  job_id: string;
  resume_version_id?: string | null;
  status?: string;
}

export interface ApplicationEvent {
  id: string;
  application_id: string;
  event_type: string;
  event_time: string;
  notes: string | null;
  source: string | null;
  created_at: string;
}

export interface ApplicationEventCreate {
  event_type: string;
  notes?: string | null;
  source?: string | null;
}

export interface RevisionFeedbackCreate {
  feedback_markdown: string;
  structured_flags?: Record<string, unknown>;
}

export interface RevisionFeedback {
  id: string;
  job_id: string;
  source_resume_version_id: string;
  followup_claude_run_id: string | null;
  feedback_markdown: string;
  status: string;
  created_at: string;
}

export interface WordHandoffMetadata {
  run_id: string;
  status: string;
  tailoring_method: string;
  handoff_dir: string;
  resume_docx: string | null;
  prompt_file: string | null;
  instructions_file: string | null;
  expected_output: string;
}

export interface WordHandoffTextRead {
  run_id: string;
  content: string;
}

export interface WordResultImportResponse {
  run_id: string;
  status: string;
  message: string;
  word_result?: string | null;
  final_resume?: string | null;
  expected_output?: string | null;
}
