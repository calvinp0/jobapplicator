# Task 129: Add compact provider trace to application runs

## Status

planned

## Goal

Show which execution providers were used during an application/tailoring run without making the UI noisy.

The application process should make it easy to answer:

* Was the local LLM used?
* Which steps used Ollama/local LLM?
* Which steps used Claude Code?
* Was deterministic backend rendering used?
* Did any step compress, fallback, or abort because of context limits?

The default UI must stay compact. Advanced provider details should be available only behind an expandable disclosure.

## Context

Local LLM support is now experimental and may be used for preflight/helper steps such as:

* job summary
* ATS keyword extraction
* role requirement extraction
* evidence gap planning
* email classification
* resume suggestions, if enabled

Final resume tailoring may still use Claude Code. DOCX rendering is deterministic backend work.

At the moment, it is hard for the user to tell during a resume tailoring/application run whether local Ollama was actually used. The user can inspect logs, run folders, or `ollama ps`, but the application workflow should surface this in a small, trustworthy way.

This task adds a provider/run trace that is visible in the application process and persisted with the run.

## Product design

Use three levels of visibility.

### Level 1 — always visible compact summary

Show a small one-line provider summary in the application/run process area.

Examples:

```text
Preflight: Ollama · Tailoring: Claude Code · DOCX: Backend
```

or:

```text
Providers used: Ollama · Claude Code · Backend
```

This should be subtle. Do not add a large diagnostics panel.

### Level 2 — expandable run trace

Add a collapsed-by-default disclosure such as:

```text
▸ Run trace
```

When expanded, show per-step provider usage:

```text
Run trace
────────────────────────────────
Job summary             Ollama / qwen3.5:9b       complete   1.8s
ATS keywords            Ollama / qwen3.5:9b       complete   2.4s
Role requirements       Ollama / qwen3.5:9b       complete   2.1s
Evidence gap plan       Ollama / qwen3.5:9b       fallback   0.4s
Resume generation       Claude Code               complete   42s
Claim audit             Claude Code               complete   18s
DOCX render             Backend renderer          complete   0.7s
```

### Level 3 — advanced technical details

Behind a nested Details disclosure, show:

* endpoint host, but avoid showing full sensitive URLs by default
* model name
* provider type
* configured JobApplicator context budget
* usable input budget
* requested Ollama `num_ctx`
* server-reported context, if known
* whether context was verified
* compression/fallback/abort decisions
* warnings

Do not show raw API keys.

## Backend requirements

Add a provider trace model for application/tailoring runs.

A trace event should include at minimum:

```json
{
  "step": "job_summary",
  "label": "Job summary",
  "provider": "ollama",
  "provider_label": "Ollama",
  "model": "qwen3.5:9b",
  "status": "complete",
  "duration_ms": 1800,
  "started_at": "ISO-8601 timestamp",
  "completed_at": "ISO-8601 timestamp",
  "context_budget_tokens": 8192,
  "usable_input_tokens": 6500,
  "requested_num_ctx": 8192,
  "server_reported_context_tokens": 262144,
  "context_verified": true,
  "compression_used": false,
  "fallback_used": false,
  "warning": null
}
```

Allowed statuses:

```text
pending
running
complete
failed
skipped
fallback
aborted
```

Allowed providers should include at least:

```text
ollama
openai_compatible
claude_code
backend
deterministic
unknown
```

Provider labels should be user-facing:

```text
Ollama
OpenAI-compatible local LLM
Claude Code
Backend renderer
Deterministic backend
Unknown
```

## Persistence requirements

Persist provider trace data inside the run directory.

Preferred file:

```text
runs/<run_id>/provider_trace.json
```

Also include a compact provider summary in existing run metadata if there is a run manifest/status JSON.

Example summary:

```json
{
  "provider_summary": {
    "preflight": "Ollama / qwen3.5:9b",
    "tailoring": "Claude Code",
    "docx": "Backend renderer",
    "providers_used": ["ollama", "claude_code", "backend"],
    "warnings": []
  }
}
```

For preflight, also mirror relevant context/provider information into:

```text
runs/<run_id>/input/preflight/preflight_manifest.json
```

Do not duplicate large raw prompts.

## API requirements

Expose provider trace through the run/application API used by the frontend.

The API should return:

```json
{
  "provider_summary": {
    "label": "Preflight: Ollama · Tailoring: Claude Code · DOCX: Backend",
    "providers_used": ["ollama", "claude_code", "backend"],
    "has_warnings": false
  },
  "provider_trace": [
    {
      "step": "job_summary",
      "label": "Job summary",
      "provider_label": "Ollama",
      "model": "qwen3.5:9b",
      "status": "complete",
      "duration_ms": 1800
    }
  ]
}
```

Keep the compact response suitable for list/detail views. Large technical fields may be nested under `details`.

## Frontend requirements

Add provider trace display in two places.

### 1. Activity Center / run details

Show compact provider summary in the run card or run detail area.

Default collapsed example:

```text
Preflight: Ollama · Tailoring: Claude Code · DOCX: Backend
▸ Run trace
```

Expanded trace should use compact rows. Avoid green pill overload. Use quiet text, small status indicators, and aligned columns.

### 2. Resume review workspace

Add a small provenance strip near the top of the workspace, near run status or artifact metadata.

Example:

```text
Generated with: Preflight Ollama · Tailoring Claude Code · DOCX Backend
```

This strip should not compete with the document preview or AI review panel.

## UI constraints

Do not add:

* a giant diagnostics panel
* raw logs in the main UI
* full endpoint URLs in the default view
* large colored pills for every step
* another primary action button

Use disclosure/details patterns. Default view should remain compact.

## Trace event generation requirements

Record trace events for at least these steps when present:

```text
job_summary
ats_keywords
role_requirements
evidence_gap_plan
resume_suggestions
resume_generation
claim_audit
docx_render
template_fidelity_audit
```

Expected provider mapping:

```text
job_summary             local LLM provider if enabled, otherwise deterministic/backend
ats_keywords            local LLM provider if enabled, otherwise deterministic/backend
role_requirements       local LLM provider if enabled, otherwise deterministic/backend
evidence_gap_plan       local LLM provider if enabled, otherwise deterministic/backend
resume_suggestions      local LLM only if explicitly enabled, otherwise Claude Code/backend as currently implemented
resume_generation       Claude Code unless full local tailoring is explicitly enabled
claim_audit             Claude Code unless local claim audit is explicitly enabled
docx_render             backend renderer
template_fidelity_audit backend/deterministic
```

If local LLM is disabled, the trace should still explain what happened:

```text
Preflight: deterministic backend · Tailoring: Claude Code · DOCX: Backend
```

## Error and fallback requirements

When a local LLM step fails and deterministic fallback is allowed, record both the failed provider attempt and fallback result, or record a single event with:

```json
{
  "status": "fallback",
  "provider": "ollama",
  "fallback_used": true,
  "warning": "Ollama request failed; deterministic fallback used."
}
```

When a step is skipped because it is disabled, record `skipped` only if useful for the UI/debug trace. Do not clutter the default summary with skipped steps.

When a step is aborted due to context budget, record:

```json
{
  "status": "aborted",
  "warning": "Input remained over budget after compression."
}
```

## Tests

Add backend tests covering:

* provider trace file is written for a tailoring/application run
* local LLM preflight records Ollama provider/model when enabled
* deterministic fallback is represented in trace data
* Claude Code tailoring step is represented separately from local LLM preflight
* DOCX render step is represented as backend/deterministic
* API returns compact provider summary and expandable trace data
* advanced fields do not expose API keys

Add frontend tests covering:

* run card/details shows compact provider summary
* run trace is collapsed by default
* expanding run trace shows per-step provider/model/status/duration
* resume review workspace shows compact provenance strip
* warnings are visible without dominating the layout

## Acceptance criteria

* A user can tell from the application process whether local Ollama was used.
* The default UI remains compact.
* Expanded run trace shows provider, model, status, duration, and warnings per step.
* Provider trace is persisted with the run.
* Run API exposes both compact summary and detailed trace.
* Resume review workspace shows a compact provenance strip.
* Local LLM context details are visible only behind a details disclosure.
* No API keys are exposed in logs, trace files, or frontend.
* Existing application/tailoring flows continue to work when local LLM is disabled.

## Verification

Run:

```bash
cd /home/calvin/code/jobapply
python -m pytest backend/tests/test_local_llm.py
python -m pytest backend/tests
cd frontend
npm run build
npm test -- --run
```

If the frontend test command differs in this repo, use the existing frontend test command documented in `package.json`.

## Out of scope

* Do not change Gmail integration.
* Do not change browser extension capture.
* Do not change resume tailoring prompt rules.
* Do not route full resume tailoring to local LLM by default.
* Do not add a new large dashboard panel.
* Do not expose raw provider credentials.

