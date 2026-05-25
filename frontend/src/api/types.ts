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
  // ``source`` is "filesystem" for resumes discovered from
  // candidate_context/master_resumes/ and "database" for DB-backed rows.
  // ``source_format`` is the lowercase file extension for filesystem
  // entries (e.g. "docx") and null otherwise. ``is_demo`` flags the
  // seeded demo row so real files render ahead of it.
  source?: "filesystem" | "database";
  source_format?: string | null;
  is_demo?: boolean;
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
  llm_provider?: string | null;
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

export interface EmailLink {
  id: string;
  application_id: string;
  gmail_message_id: string;
  gmail_thread_id: string | null;
  subject: string | null;
  sender: string | null;
  received_at: string | null;
  classified_status: string | null;
  confidence: number | null;
  created_at: string;
}

export interface EmailLinkCreatePayload {
  gmail_message_id: string;
  classified_status: string;
  gmail_thread_id?: string | null;
  subject?: string | null;
  sender?: string | null;
  received_at?: string | null;
  confidence?: number | null;
}

export interface Application {
  id: string;
  job_id: string;
  resume_version_id: string | null;
  status: string;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  timeline_stage: string;
  last_email_link: EmailLink | null;
  email_link_count: number;
  submission_status: string;
  email_status: string;
  next_action: string;
  latest_run_id: string | null;
  latest_run_status: string | null;
  last_email_at: string | null;
  // Gmail tracking surface (docs/contracts/gmail_integration.md).
  gmail_query?: string | null;
  last_gmail_check_at?: string | null;
  last_matched_email_at?: string | null;
  matched_email_count?: number;
  latest_email_subject?: string | null;
  latest_email_from?: string | null;
  latest_email_snippet?: string | null;
  latest_email_classification?: string | null;
  latest_email_confidence?: number | null;
  latest_email_evidence?: string | null;
}

export interface GmailStatusResponse {
  connected: boolean;
  configured: boolean;
  missing_config: string[];
  email: string | null;
  scopes: string[];
  token_path_configured: boolean;
  last_checked_at: string | null;
}

export interface GmailAuthUrlResponse {
  auth_url: string;
  scope: string;
}

export interface GmailCandidateEmail {
  message_id: string | null;
  thread_id: string | null;
  subject: string | null;
  from: string | null;
  date: string | null;
  snippet: string | null;
  matched_signals: string[];
  match_score: number;
}

export interface GmailSearchResponse {
  application_id: string;
  gmail_connected: boolean;
  gmail_query: string | null;
  count: number;
  candidates: GmailCandidateEmail[];
  message?: string | null;
}

export interface GmailEvidenceItem {
  field: string;
  text: string;
  reason: string;
}

export interface GmailClassificationResponse {
  application_id: string;
  message_id: string | null;
  classification: string;
  confidence: number;
  email_status: string;
  application_status: string;
  evidence: GmailEvidenceItem[];
  reason: string;
  application_status_changed: boolean;
  email_link_id: string | null;
}

export interface GmailSyncApplicationResult {
  application_id: string;
  job_title: string | null;
  company: string | null;
  previous_email_status: string;
  new_email_status: string;
  previous_application_status: string;
  new_application_status: string;
  matched_email_count: number;
  classification: string | null;
  confidence: number | null;
  evidence: GmailEvidenceItem[];
  application_status_changed: boolean;
  gmail_query: string | null;
  skipped_reason: string | null;
}

export interface GmailSyncApplicationsResponse {
  gmail_connected: boolean;
  checked_count: number;
  updated_count: number;
  no_match_count: number;
  needs_review_count: number;
  results: GmailSyncApplicationResult[];
  message?: string | null;
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

export interface LlmProvider {
  id: string;
  display_name: string;
  default_binary: string;
  binary_env_var: string;
}

export interface LlmProviderSetting {
  default_provider: string;
  available: LlmProvider[];
}
