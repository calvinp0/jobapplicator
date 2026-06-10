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
| Job description summarization (`job_summary`) | low | on | Allowed when enabled. |
| ATS keyword extraction (`ats_keywords`) | low | on | Allowed when enabled. |
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

In Settings → LLM Providers, click **Test connection**. The backend sends a
minimal chat-completion request to the configured endpoint/model and reports
one of:

- **Connected — model responded.**
- An error/timeout message (connection refused, timeout, HTTP error, or a
  malformed response).

The test uses the values currently in the form, so you can verify unsaved
edits before saving.

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

## Current integration status

The app does not yet run ATS keyword extraction or job-description
summarization as separate steps outside the single Claude tailoring prompt.
The provider config, task policy, client, connection test, and the
experimental suggestions endpoint are in place and ready for those steps to
be wired in by a future task — without weakening the tailoring guarantees
above.
