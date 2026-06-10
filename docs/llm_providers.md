# LLM Providers

This app uses LLMs through two independent surfaces:

1. **CLI tailoring providers** — the high-risk `auto` resume-tailoring flow
   (ADR-009). Backed by CLI workers (Claude Code, Codex CLI, Gemini CLI)
   that satisfy the run-directory contract. **Claude Code is the default**
   and remains the recommended provider for final resume tailoring, claim
   auditing, and recruiter review.
2. **Experimental local LLM** — an opt-in, off-by-default subsystem for
   *low-risk* tasks, backed by a local OpenAI-compatible HTTP endpoint
   (Ollama, vLLM, LM Studio, llama.cpp's server). This document focuses on
   that subsystem.

> The two surfaces are deliberately separate. The local LLM **never** drives
> the `auto` resume-tailoring flow and **never** takes over claim auditing or
> recruiter review. ADR-009 scopes the CLI registry to CLI workers and
> excludes hosted/HTTP-API providers from that path; the local LLM lives
> alongside it, not inside it.

## Why local LLMs (and why they are experimental)

Local models can be useful for privacy-sensitive runs, cheap iteration, and
offline experimentation: job-description summarization, ATS keyword
extraction, email classification, and simple suggestion drafting.

They tend to underperform on nuanced resume tailoring, evidence-grounded
claim auditing, strict JSON generation, and instruction-following under long
context. For those reasons, local LLM support is **experimental, opt-in,
schema-validated, clearly logged, and easy to fall back from**. Claude Code
remains the default for every high-risk output.

## Task policy

The policy lives in `backend/app/local_llm.py` (`TASK_RISK`,
`local_allowed_for_task`). Defaults are conservative — nothing runs locally
until you both enable the subsystem *and* toggle the specific task on.

| Task | Risk | Local default | Notes |
|------|------|---------------|-------|
| Job summary (`job_summary`) | low | on | Allowed when enabled. Preflight task. |
| ATS keyword extraction (`ats_keywords`) | low | on | Allowed when enabled. Preflight task. |
| Role requirement extraction (`role_requirements`) | low | on | Allowed when enabled. Preflight task (task 124). |
| Evidence gap planning (`evidence_gap_plan`) | low | on | Allowed when enabled. Preflight task (task 124); conservative — names where to look, never claims evidence exists. |
| Email classification (`email_classification`) | low | on | Allowed when enabled. |
| Resume suggestions (`resume_suggestions`) | experimental | off | Requires explicit opt-in. |
| Full resume tailoring (`resume_tailoring`) | high | off | Claude Code default; local only if explicitly enabled. |
| Claim audit (`claim_audit`) | high | off | Claude Code default; local only if explicitly enabled. |
| Recruiter review (`recruiter_review`) | claude-only | n/a | Never local; not configurable. |

Even with the master switch on, high-risk tasks stay on Claude Code unless
you deliberately turn them on. Recruiter review is always Claude Code.

## Configuration (Settings → LLM Providers)

The Settings page exposes an **LLM Providers** section (separate from the
**Claude / LLM** CLI-provider selector). Fields:

- **Enable local LLM (experimental)** — master on/off switch (default off).
- **Provider** — `OpenAI-compatible` or `Ollama` (both speak the same
  chat-completions shape in this iteration).
- **Local LLM endpoint** — e.g. `http://localhost:11434/v1` for Ollama's
  OpenAI-compatible surface, or any OpenAI-compatible base URL.
- **Model name** — e.g. `llama3.1:8b`, `qwen2.5-coder:14b`, `mistral-small`.
- **Timeout (seconds)** — default `60`.
- **Context window tokens** — configured local model context size, default
  `8192`.
- **Reserved output tokens** — output headroom kept out of the input prompt,
  default `1200`.
- **Max input tokens** — usable input budget. Defaults to the configured
  context window minus reserved output tokens, capped at `6500` in the
  default settings.
- **Ollama context length (`num_ctx`, optional)** — sets the Ollama model
  server's running context length. When set and the **provider is Ollama**,
  the backend sends `options.num_ctx` on Ollama's native `/api/chat` request
  so the server actually runs at that context length (its OpenAI-compatible
  `/v1` surface ignores the option, so `num_ctx` is **Ollama-native only** and
  is never sent for the OpenAI-compatible provider). This is **distinct** from
  **Context window tokens** above: `num_ctx` configures the model server,
  while the context-budget fields drive JobApplicator's own prompt budgeting.
  Leave it unset to use the server's own default.
- **Over-budget handling** — deterministic compression, deterministic
  fallback, and abort-on-over-budget controls. Local prompts are never
  silently truncated.
- **API key (optional)** — only needed if your endpoint requires one. It is
  stored locally in the settings table, masked in the UI, and never returned
  in plaintext.
- **Use local LLM for** — per-task checkboxes matching the policy table.

Settings persist in the existing `app_settings` key/value table under the
`local_llm_config` key. No secrets are committed to the repo.

### API surface

- `GET /settings/local-llm` — sanitized config snapshot (API key masked).
- `PUT /settings/local-llm` — save config (validates URL, model, timeout).
- `DELETE /settings/local-llm` — reset to defaults.
- `POST /llm/local/test-connection` — connection test (see below).
- `POST /llm/local/suggest-resume-edits` — experimental, bounded resume
  suggestions; refuses unless `resume_suggestions` is enabled.

## Setting up Ollama / an OpenAI-compatible endpoint

**Ollama** exposes an OpenAI-compatible API at `/v1`:

```bash
# Install: https://ollama.com/download
ollama pull llama3.1:8b
ollama serve            # serves http://localhost:11434
```

Set the endpoint to `http://localhost:11434/v1` and the model to a pulled
model (e.g. `llama3.1:8b`). No API key is required for a default local
Ollama install.

**Other servers** (vLLM, LM Studio, llama.cpp `server`) generally expose an
OpenAI-compatible `/v1/chat/completions` endpoint — point the base URL at
that surface and set a matching model name.

## Testing the connection

Local models often have much smaller effective context windows than Claude
Code. Before every local call, the backend estimates prompt tokens, reserves
output headroom, compresses/selects bounded task input when allowed, and then
falls back or aborts if the prompt still does not fit. The app must not
silently overfill or truncate a local-model prompt.

In Settings → LLM Providers, click **Test connection**. The backend sends a
minimal chat-completion request to the configured endpoint/model and reports
the connection result plus configured budget information:

- **Connected — model responded. Configured context window: 8192 tokens.
  Usable input budget: 6500 tokens.**
- An error/timeout message (connection refused, timeout, HTTP error, or a
  malformed response).

The test uses the values currently in the form (including an unsaved
`num_ctx`), so you can verify unsaved edits before saving.

### Server-context detection (task 127)

The configured context budget is JobApplicator's *assumption* about the
model's context window. The connection test also makes a best-effort attempt
to read the context the model **server is actually running**, so the gap
between the two is observable. The result adds three fields to the test
response:

- `server_reported_context_tokens` — the server's own context length for the
  model (`int`), or `null` when it could not be read.
- `context_verified` — `true` only when the server actually reported a context
  length.
- `context_warning` — a short explanation, present only when the context could
  **not** be verified.

Only the **Ollama-native** provider exposes this: the backend queries Ollama's
native `/api/show` endpoint (derived from the configured base URL by stripping
a trailing `/v1`) and reads the model's reported context length. When it
succeeds the success message appends `Server-reported context: N tokens.` and
`context_verified` is `true`.

For the **OpenAI-compatible** provider there is no portable way to read the
server's context window, so detection always returns `context_verified = false`
with a `context_warning` explaining that *an OpenAI-compatible endpoint does
not expose its context window, so JobApplicator cannot verify that the
server's real context matches the configured budget*. A network error, an
unreachable Ollama server, or a missing metadata field degrade the same way —
detection never raises and never blocks the connection test.

Detection is **reporting only**: a detected context is never auto-applied to
the budget. You stay in control of the **Context window tokens** budget; the
detection result just tells you whether your assumption matches reality.

## Schema validation and fallback

For any local task that produces structured output, the client
(`LocalLLMClient.chat_json`) requests a JSON object, validates required
fields, and — on a validation failure — retries **once** with a repair
prompt. If the repair still fails, the result is marked invalid so the
caller can fail clearly or fall back to Claude Code where applicable. The
client never raises on network errors; it returns a non-OK result, which is
the clean fall-back signal.

Each structured call logs a single line:

```text
LLM provider: local_openai_compatible | Model: llama3.1:8b | Task: ats_keywords | Schema validation: passed | Fallback used: no
```

## Run metadata

Where a task records provenance, the provider/model is stamped via
`local_llm.task_run_metadata(task)`:

```json
{ "task": "ats_keywords", "provider": "local_openai_compatible", "model": "llama3.1:8b", "local_llm_enabled": true }
```

High-risk tasks resolve to `claude_code` regardless of the local config, so
the recorded provenance always reflects what actually ran.

## Why Claude Code remains the default for tailoring

Final resume tailoring is evidence-grounded and must not invent unsupported
claims (ADR-004). Claim auditing and recruiter review are the guardrails
that catch unsupported content. Local models are more likely to drift on
these constraints and on strict JSON, so they are kept off these paths by
default. Use local LLMs to iterate cheaply on summaries and keyword
extraction; keep Claude Code for the outputs that ship.

## Preflight analysis pipeline (task 124)

The low-risk preflight tasks are wired into the tailoring run as a
**provider-routed preflight analysis pipeline** that runs *before* the main
Claude Code tailoring prompt. The worker (`backend/app/claude_worker.py`)
calls `app.preflight.run_preflight` after staging inputs and before
launching Claude. Each run gets an `input/preflight/` directory containing:

```text
input/preflight/job_summary.json        # company/title/location/summary
input/preflight/ats_keywords.json       # classified ATS keywords + groups
input/preflight/role_requirements.json  # requirements + responsibilities
input/preflight/evidence_gap_plan.json  # where to look (a plan, not evidence)
input/preflight/preflight_manifest.json # provider/model/status per task
input/preflight/preflight_summary.md    # optional human-readable projection
```

Routing per task uses the policy above:

- `job_summary`, `ats_keyword_extraction`, `role_requirements`, and
  `evidence_gap_plan` may run on the local provider when the subsystem is
  enabled and the task is toggled on.
- Otherwise — or on any local connection/JSON failure — a **deterministic**
  extractor (regex/headings/JD-text parsing in `app.preflight`) produces the
  same artifacts. Preflight therefore never requires a local LLM.
- `resume_tailoring`, `claim_audit`, and `recruiter_review` are **not**
  preflight tasks; they remain on Claude Code in the main tailoring run.

The manifest records the provider/model that produced each artifact and
whether a fallback occurred. For local-provider attempts it also records
context-budget checks, the effective assumed context per task, and a top-level
summary of the assumed vs. server-reported context for the run (task 127):

```json
{
  "created_at": "2026-06-10T12:00:00Z",
  "provider": "local_ollama",
  "model": "llama3.1:8b",
  "fallback_used": false,
  "context": {
    "assumed_context_tokens": 8192,
    "server_reported_context_tokens": 131072,
    "context_verified": true,
    "requested_num_ctx": 16384,
    "note": "Ollama reports a context length of 131072 tokens for model llama3.1:8b. Requested num_ctx is 16384."
  },
  "tasks": [
    {"name": "ats_keyword_extraction", "provider": "local_ollama",
     "model": "llama3.1:8b", "status": "succeeded",
     "output": "input/preflight/ats_keywords.json",
     "context": {
       "context_window_tokens": 8192,
       "reserved_output_tokens": 1200,
       "max_input_tokens": 6500,
       "effective_assumed_context_tokens": 8192,
       "requested_num_ctx": 16384,
       "estimated_input_tokens_initial": 9320,
       "estimated_input_tokens_final": 5810,
       "compression_used": true,
       "fallback_used": false,
       "over_budget": false
     }}
  ]
}
```

The top-level `context` summary is present only when the run intends the local
provider. `server_reported_context_tokens` / `context_verified` come from the
same best-effort detection as the connection test: only the Ollama-native
provider reports a context length (via `/api/show`); an OpenAI-compatible or
unreachable server records `context_verified = false`. Detection is
best-effort and reporting only — a detection failure records
`context_verified = false` and **never fails preflight**, and a detected
context is never auto-applied to the budget. The per-task
`effective_assumed_context_tokens` records the context window each local task
budgeted against, and `requested_num_ctx` appears when an Ollama `num_ctx` is
configured.

When the local provider is unavailable the manifest records
`"provider": "deterministic"` (and `"fallback_used": true` with a
`fallback_reason` when local was attempted first). If a local prompt remains
over budget after deterministic compression and fallback is enabled, the
individual task is recorded with `"status": "fallback"`,
`"provider": "deterministic"`, and a context block showing the failed budget
check.

Local preflight prompt assembly is task-specific and bounded:

- `job_summary`, `ats_keyword_extraction`, and `role_requirements` use only
  `input/job_description.md` plus `input/job_capture.md` when present.
- `evidence_gap_plan` uses the job description and staged evidence index/file
  names. It does not read full evidence bodies, DOCX extracted text, prior
  resumes, or the full candidate context.

Preflight is **advisory and best-effort**: it never fails the tailoring run.
The main prompt treats the artifacts as a starting point only — the
truthfulness/evidence contract still governs the final resume, the ATS audit
starts from `ats_keywords.json`, and if preflight conflicts with the job
description, the job description wins. The `evidence_gap_plan.json` only
suggests where to look; it never asserts that evidence exists. See
`docs/contracts/claude_run_directory.md` for the per-artifact schemas.
