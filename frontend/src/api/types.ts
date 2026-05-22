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

export interface EvidenceBank {
  id: string;
  name: string;
  source_path: string | null;
  content_markdown: string;
  created_at: string;
  updated_at: string;
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

export interface Application {
  id: string;
  job_id: string;
  resume_version_id: string | null;
  status: string;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}
