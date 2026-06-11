export interface PromptHarnessSummary {
  id: string;
  label: string;
  description: string;
  default_path: string;
  has_override: boolean;
  effective_source: "default" | "override";
  updated_at: string | null;
}

export interface PromptHarnessDetail {
  id: string;
  label: string;
  description: string;
  default_path: string;
  has_override: boolean;
  effective_source: "default" | "override";
  default_content: string;
  override_content: string | null;
  effective_content: string;
  effective_hash: string;
  updated_at: string | null;
}

export interface PromptValidationResult {
  valid: boolean;
  warnings: string[];
}

export interface CaptureDiagnostics {
  extractor?: string;
  selectors_matched?: {
    title?: boolean;
    company?: boolean;
    location?: boolean;
    description?: boolean;
  };
  fallbacks_used?: Record<string, boolean>;
  document_title?: string | null;
  body_text_length?: number;
  url_has_current_job_id?: boolean;
  has_selected_text?: boolean;
}

export interface JobCapture {
  id: string;
  source_platform: string;
  capture_method: string;
  external_url: string | null;
  // Task 110: ``source_url`` is the raw URL the extension captured;
  // ``canonical_url`` is the deterministically cleaned form. Both are
  // optional so captures from before the canonicalizer landed still load.
  source_url?: string | null;
  canonical_url?: string | null;
  external_job_id: string | null;
  company: string | null;
  title: string | null;
  location: string | null;
  description_text: string;
  application_method: string | null;
  raw_text: string | null;
  // Task 109: fallback fields populated by the browser extension when
  // LinkedIn's structured selectors did not resolve. Older captures may
  // not have any of these (all nullable).
  page_title?: string | null;
  page_text?: string | null;
  selected_text?: string | null;
  diagnostics?: CaptureDiagnostics | null;
  captured_at: string;
  user_confirmed: boolean;
  created_at: string;
  job_id: string | null;
}

export interface JobCaptureConfirm {
  company: string;
  title: string;
  location: string;
  external_url: string;
  description_text: string;
  application_method: string;
}

export interface Job {
  id: string;
  source_platform: string;
  external_url: string | null;
  // Task 110: same canonical/source URL pair as JobCapture.
  source_url?: string | null;
  canonical_url?: string | null;
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

// Result of importing a file into an app-managed candidate_context folder
// (task 121). The original upload is copied so the app owns a stable copy;
// ``stored_path`` is the managed project-relative path.
export interface FileImportResult {
  id: string;
  name: string;
  source_type: string;
  source_format: string;
  original_filename: string;
  stored_path: string;
  imported_at: string;
}

// Response from POST /settings/reset-local-data (task 121).
export interface ResetLocalDataResponse {
  ok: boolean;
  backup_path: string | null;
  deleted: Record<string, number>;
}

export type EvidenceSourceType =
  | "evidence_bank"
  | "resume_variant"
  | "master_resume"
  | "project_note"
  | "candidate_note"
  | "other";

// Combined selector shape for tailoring-run evidence: DB-backed
// EvidenceBank rows and filesystem discoveries under
// candidate_context/ subfolders share this representation so the
// multi-select picker renders both with a uniform badge set.
export interface EvidenceSource {
  id: string;
  name: string;
  source_type: EvidenceSourceType;
  source_format: string | null;
  source: "database" | "filesystem";
  source_path: string | null;
  updated_at: string;
  is_demo: boolean;
}

// ---- Provider trace (task 129) ----
// Records which execution provider produced each step of a tailoring run so
// the UI can answer "was the local LLM used?" without log spelunking. The
// compact fields drive the default (subtle) view; advanced/technical fields
// live under ``details`` so they only show behind a disclosure. No
// credentials are ever included.

export interface ProviderTraceDetails {
  context_budget_tokens?: number | null;
  usable_input_tokens?: number | null;
  requested_num_ctx?: number | null;
  server_reported_context_tokens?: number | null;
  context_verified?: boolean | null;
  endpoint_host?: string | null;
}

export interface ProviderTraceEvent {
  step: string;
  label: string;
  provider: string;
  provider_label: string;
  model: string | null;
  status: string;
  duration_ms?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  compression_used?: boolean;
  fallback_used?: boolean;
  warning?: string | null;
  details?: ProviderTraceDetails;
}

export interface ProviderSummary {
  label: string;
  preflight?: string;
  tailoring?: string;
  docx?: string;
  providers_used: string[];
  warnings?: string[];
  has_warnings: boolean;
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
  evidence_source_ids?: string[];
  provider_summary?: ProviderSummary | null;
  provider_trace?: ProviderTraceEvent[];
}

export interface RunLog {
  run_id: string;
  lines: string[];
  truncated: boolean;
}

// ---- Activity center (task 117) ----
// The bottom-left activity center renders this domain-agnostic feed without
// knowing about runs/captures/applications. ``group`` decides the section,
// ``status`` drives the coloured dot, and ``href`` is a ready frontend route.

export interface ActivityItem {
  id: string;
  type: string;
  status: string;
  group: "running" | "attention" | "recent" | string;
  title: string;
  subtitle?: string | null;
  detail?: string | null;
  started_at?: string | null;
  href: string;
}

export interface ActivitySummary {
  running_count: number;
  attention_count: number;
  pending_capture_count: number;
}

export interface ActivityResponse {
  summary: ActivitySummary;
  items: ActivityItem[];
}

export interface RunProgress {
  run_id: string;
  lines: string[];
  truncated: boolean;
}

export interface RecruiterReview {
  run_id: string;
  available: boolean;
  content: string | null;
  path: string | null;
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

// ---- Resume export / download (task 122) ----

export interface RunExportFile {
  name: string;
  source: string;
}

export interface RunExport {
  ok: boolean;
  export_dir: string;
  files: RunExportFile[];
}

export interface ExportSettings {
  path: string;
}

export interface EmailLink {
  id: string;
  application_id: string;
  gmail_message_id: string;
  gmail_thread_id: string | null;
  subject: string | null;
  sender: string | null;
  snippet?: string | null;
  received_at: string | null;
  classified_status: string | null;
  confidence: number | null;
  // Task 093: manual-linking metadata. Present on rows created (or
  // re-linked) through ``POST /applications/{id}/gmail/link-email``.
  match_method?: string | null;
  match_score?: number | null;
  linked_by_user?: boolean;
  evidence?: Array<{ field: string; text: string; reason: string }> | null;
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

// Task 093: manual Gmail email linking. These types mirror the
// candidate / link-email / linked-emails surface added by the backend.

export interface GmailManualCandidate {
  message_id: string | null;
  thread_id: string | null;
  subject: string | null;
  from: string | null;
  date: string | null;
  snippet: string | null;
  match_score: number;
  matched_signals: string[];
  classification_guess: string | null;
}

export interface GmailCandidatesResponse {
  application_id: string;
  gmail_connected: boolean;
  query_used: string | null;
  count: number;
  strong_count: number;
  possible_count: number;
  candidates: GmailManualCandidate[];
  message?: string | null;
}

export type ManualLinkClassification =
  | "submission_confirmation"
  | "rejection"
  | "interview_request"
  | "recruiter_followup"
  | "assessment"
  | "offer"
  | "application_update"
  | "unknown";

export interface GmailLinkEmailPayload {
  message_id: string;
  thread_id?: string | null;
  classification?: ManualLinkClassification;
  sender?: string | null;
  subject?: string | null;
  snippet?: string | null;
  received_at?: string | null;
  match_score?: number | null;
  user_confirmed: boolean;
}

export interface GmailLinkEmailResponse {
  application_id: string;
  email_link: EmailLink;
  classification: string;
  email_status: string;
  application_status: string;
  application_status_changed: boolean;
}

export interface GmailLinkedEmailsResponse {
  application_id: string;
  linked_emails: EmailLink[];
}

export interface GmailUnlinkResponse {
  application_id: string;
  removed_email_link_id: string;
  remaining_linked_count: number;
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
  // Optional ids of evidence sources to stage on the revision run in
  // addition to the original sources used by the source draft. Each id
  // is resolved server-side through the same DB + filesystem discovery
  // path as first-draft runs.
  additional_evidence_source_ids?: string[];
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

// ---- Resume suggestions (task 113) ----

export interface EvidenceRef {
  source: string;
  quote: string;
}

export type SuggestionStatus = "pending" | "accepted" | "rejected" | "revised";

export interface ResumeSuggestion {
  id: string;
  section_id: string;
  section_heading: string;
  operation: string;
  current_text: string;
  suggested_text: string;
  reason: string;
  evidence_refs: EvidenceRef[];
  ats_keywords: string[];
  confidence: number | null;
  risk: string;
  status: SuggestionStatus;
  revision_instruction: string;
}

// ---- Structured resume (tailored_resume.json schema, task 111/114) ----
// The deterministic resume document the DOCX renderer consumes. The review
// workspace renders this as a Word-like page. Fields are intentionally loose
// (most optional) so the preview degrades gracefully across section types.

export interface StructuredResumeHeader {
  name: string;
  contact_items?: string[];
  subtitle?: string;
}

export interface StructuredResumeEntry {
  // experience entries
  title?: string;
  organization?: string;
  location?: string;
  dates?: string;
  subtitle?: string;
  bullets?: string[];
  // education entries
  institution?: string;
  degree?: string;
}

export interface StructuredResumeSkillGroup {
  label?: string;
  items: string[];
}

export interface StructuredResumeSection {
  type: string;
  heading: string;
  paragraphs?: string[];
  groups?: StructuredResumeSkillGroup[];
  entries?: StructuredResumeEntry[];
  items?: string[];
}

export interface StructuredResume {
  header: StructuredResumeHeader;
  sections: StructuredResumeSection[];
  metadata?: Record<string, unknown>;
}

export interface ResumeSuggestions {
  resume_version_id: string;
  target_company: string;
  target_job_title: string;
  suggestions: ResumeSuggestion[];
  applied_at: string | null;
  has_working_resume: boolean;
  // Task 114: structured resume documents backing the document preview.
  // ``base_resume`` is the tailored resume captured at import; ``working_resume``
  // is the rebuilt document after accepted suggestions were applied. Both are
  // optional — pre-task-114 drafts return neither.
  base_resume?: StructuredResume | null;
  working_resume?: StructuredResume | null;
}

export interface ApplySuggestionsResult {
  resume_version_id: string;
  applied_at: string;
  accepted_count: number;
  working_resume: Record<string, unknown> | null;
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

export interface WordHandoffFileStatus {
  name: string;
  path: string;
  exists: boolean;
}

// Filesystem-derived view of a run's Word handoff package — see task 112.
// ``state`` drives which UI block renders; the ``files`` map drives the
// per-file existence indicators and copy-path actions.
export type WordHandoffState =
  | "not_prepared"
  | "prepared"
  | "missing_files"
  | "import_ready"
  | "imported";

export interface WordHandoffStatus {
  run_id: string;
  state: WordHandoffState;
  handoff_dir: string;
  handoff_dir_exists: boolean;
  files: {
    resume_docx: WordHandoffFileStatus;
    prompt_txt: WordHandoffFileStatus;
    instructions_md: WordHandoffFileStatus;
    expected_output_docx: WordHandoffFileStatus;
    final_resume_docx: WordHandoffFileStatus;
  };
  missing_required_files: string[];
  message: string;
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

// Experimental local LLM provider (task 123). Separate from the CLI
// tailoring provider above: this drives only opt-in, low-risk tasks and is
// never the default for high-risk resume tailoring. The plaintext API key
// is never sent — only a masked preview and a boolean flag.
export interface LocalLlmTaskPolicy {
  task: string;
  risk: "low" | "experimental" | "high" | "claude_only";
  configurable: boolean;
  default_local: boolean;
}

export interface LocalLlmSettings {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  allowed_tasks: Record<string, boolean>;
  context_window_tokens: number;
  reserved_output_tokens: number;
  max_input_tokens: number;
  // Optional Ollama server context length (task 126). Distinct from
  // context_window_tokens: num_ctx configures the model server, while the
  // context-budget fields only drive JobApplicator's own prompt budgeting.
  // null means "leave the server at its own default".
  num_ctx: number | null;
  allow_compression: boolean;
  allow_fallback: boolean;
  abort_on_over_budget: boolean;
  has_api_key: boolean;
  api_key_preview: string;
  updated_at: string | null;
  task_policy: LocalLlmTaskPolicy[];
}

export interface LocalLlmSettingsUpdate {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  allowed_tasks: Record<string, boolean>;
  context_window_tokens: number;
  reserved_output_tokens: number;
  max_input_tokens?: number | null;
  num_ctx?: number | null;
  allow_compression: boolean;
  allow_fallback: boolean;
  abort_on_over_budget: boolean;
  api_key?: string | null;
  preserve_existing_key?: boolean;
}

export interface LocalLlmTestResult {
  ok: boolean;
  message: string;
  model: string;
  provider: string;
  latency_ms: number | null;
  error: string | null;
  // Connection-error classification (task 136). ``error_kind`` is a stable
  // tag — ``none`` on success, otherwise ``endpoint_unavailable``,
  // ``bad_url``, ``model_not_installed``, or ``unexpected`` — so the UI can
  // render a distinct message per class. ``installed_models`` carries the
  // server's installed models (Ollama-native only; empty for the
  // OpenAI-compatible surface, which cannot list models).
  error_kind: string | null;
  installed_models: string[];
  context_window_tokens: number;
  max_input_tokens: number;
  // Server-context detection (task 127). server_reported_context_tokens is
  // the context the model server says it is running (Ollama-native only);
  // context_verified is true only when that read succeeded; context_warning
  // explains why the context could not be verified.
  server_reported_context_tokens: number | null;
  context_verified: boolean;
  context_warning: string | null;
}

// Response of GET /llm/local/models (task 135). Lists the models installed on
// the configured local endpoint. ``ok`` is true only when the listing actually
// succeeded; ``models`` is the installed-model names (empty otherwise).
// ``error`` / ``error_kind`` explain a failure — including ``unsupported`` when
// the configured provider is OpenAI-compatible, which has no model-listing
// endpoint.
export interface LocalLlmModelsResult {
  provider: string;
  ok: boolean;
  models: string[];
  error: string | null;
  error_kind: string | null;
}

export interface LocalLlmTestRequest {
  base_url?: string | null;
  model?: string | null;
  timeout_seconds?: number | null;
  context_window_tokens?: number | null;
  reserved_output_tokens?: number | null;
  max_input_tokens?: number | null;
  num_ctx?: number | null;
  api_key?: string | null;
  provider?: string | null;
  preserve_existing_key?: boolean;
}

// Sanitized snapshot of the persisted Gmail OAuth config (task 088).
// The plaintext client secret is never sent — only a masked preview and
// a boolean flag.
export interface GmailOAuthSettings {
  configured: boolean;
  source: "settings" | "environment" | "none";
  google_client_id: string | null;
  has_google_client_secret: boolean;
  google_client_secret_preview: string;
  google_redirect_uri: string;
  gmail_token_path: string;
  updated_at: string | null;
}

export interface GmailOAuthSettingsUpdate {
  google_client_id: string;
  google_client_secret?: string | null;
  google_redirect_uri: string;
  gmail_token_path?: string | null;
  preserve_existing_secret?: boolean;
}
