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
- **Provider** — `OpenAI-compatible` or `Ollama`. The two speak **different
  endpoints**: the OpenAI-compatible provider calls
  `POST {base_url}/chat/completions`, while the Ollama provider calls Ollama's
  native `POST {base_url}/api/chat` (task 129).
- **Local LLM endpoint** — depends on the provider:
  - **Ollama provider** — the server base URL, e.g. `http://localhost:11434`
    (the backend calls the native `/api/chat`; a trailing `/v1` is tolerated
    and stripped).
  - **OpenAI-compatible provider** — a base URL the backend appends
    `/chat/completions` to, e.g. `http://localhost:11434/v1`. For Ollama's
    OpenAI-compatible surface the base URL **must** include `/v1`, otherwise
    the request 404s.
- **Model name** — e.g. `llama3.1:8b`, `qwen2.5-coder:14b`, `mistral-small`.
- **Timeout (seconds)** — the per-call bound on each outbound local LLM
  request. Leave it unset to use a **provider-aware default**: the
  OpenAI-compatible provider uses `60`, while the **Ollama** provider uses
  `180` (task 130). The longer Ollama default exists because Ollama-native
  models often pay a large first-token / model-load cost on a cold start, so a
  freshly loaded model can take well over a minute to answer the first
  preflight task; a 60s bound would cut that off and silently force the
  deterministic fallback on every run, making the provider look broken when it
  is merely cold. An **explicit** timeout you configure always overrides the
  default and is used verbatim for every provider. The effective value in force
  is surfaced via `GET /settings/local-llm` (`effective_timeout_seconds`).
- **Context window tokens** — configured local model context size, default
  `8192`.
- **Reserved output tokens** — output headroom kept out of the input prompt,
  default `1200`.
- **Max input tokens** — usable input budget. Defaults to the configured
  context window minus reserved output tokens, capped at `6500` in the
  default settings.
- **Ollama context length (`num_ctx`, optional)** — sets the Ollama model
  server's running context length. The Ollama provider always uses the native
  `/api/chat` endpoint; when `num_ctx` is set the backend adds an
  `options.num_ctx` block to that request so the server actually runs at that
  context length. It is an optional add-on, not what selects the endpoint. The
  OpenAI-compatible `/v1` surface ignores the option, so `num_ctx` is
  **Ollama-native only** and is never sent for the OpenAI-compatible provider.
  This is **distinct** from
  **Context window tokens** above: `num_ctx` configures the model server,
  while the context-budget fields drive JobApplicator's own prompt budgeting.
  Leave it unset to use the server's own default.
- **Reasoning control (`thinking_mode`)** — how the model's "thinking" /
  chain-of-thought output is handled. Reasoning-capable local models
  (DeepSeek-R1, Qwen3, and other Ollama models) emit reasoning — usually
  wrapped in `<think>...</think>` markers — *before* the JSON object the
  preflight pipeline expects, which would otherwise make schema validation
  fail and discard an otherwise usable answer. Modes:
  - **`strip_thinking`** *(default)* — allow the model to reason but remove the
    `<think>`/`<thinking>` blocks from the reply **before** JSON parsing, so the
    structured answer is recovered. Existing users get this without
    reconfiguring.
  - **`hide_thinking`** — like `strip_thinking` for parsing, and additionally
    keeps the reasoning out of the surfaced content so it never reaches
    persisted artifacts or logs downstream.
  - **`no_thinking`** — ask the model not to reason at all. For the **Ollama**
    provider the backend sends the native `think: false` option on the
    `/api/chat` request; for **OpenAI-compatible** servers (which have no
    portable disable-reasoning flag) it reinforces *reply with ONLY the JSON
    object, no reasoning* in the system prompt. A provider-specific reasoning
    flag is **never** sent to an OpenAI-compatible endpoint.

  Disabling reasoning is **best-effort** — a reasoning-tuned model may emit a
  `<think>` block anyway — so **stripping is the reliable mechanism**: every
  structured call strips `<think>`/`<thinking>` blocks before parsing
  regardless of the selected mode. The default (`strip_thinking`) is safe for
  every model.
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
- `GET /llm/local/models` — list installed models (Ollama-native only;
  see below).
- `POST /llm/local/suggest-resume-edits` — experimental, bounded resume
  suggestions; refuses unless `resume_suggestions` is enabled.

## Setting up Ollama / an OpenAI-compatible endpoint

```bash
# Install: https://ollama.com/download
ollama pull llama3.1:8b
ollama serve            # serves http://localhost:11434
```

Ollama exposes **two** chat surfaces, and the two providers target different
ones:

- **Ollama provider (native)** — set the endpoint to the server base URL
  `http://localhost:11434` (no `/v1`). The backend calls Ollama's native
  `POST /api/chat`. This is the recommended setup for Ollama and is the only
  surface that honours `options.num_ctx`.
- **OpenAI-compatible provider** — Ollama also exposes an OpenAI-compatible
  API at `/v1`. To use it, select the `OpenAI-compatible` provider and set the
  endpoint to `http://localhost:11434/v1`; the backend appends
  `/chat/completions`. The `/v1` suffix is **required** — pointing the
  OpenAI-compatible provider at a bare `http://localhost:11434` calls
  `/chat/completions`, which does not exist on Ollama and returns `404`.

Set the model to a pulled model (e.g. `llama3.1:8b`). No API key is required
for a default local Ollama install.

**Other servers** (vLLM, LM Studio, llama.cpp `server`) generally expose an
OpenAI-compatible `/v1/chat/completions` endpoint — use the
`OpenAI-compatible` provider, point the base URL at that surface, and set a
matching model name.

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
- A classified failure message (see below).

The test uses the values currently in the form (including an unsaved
`num_ctx`), so you can verify unsaved edits before saving.

### Classified connection failures (task 136)

Rather than echoing a raw transport error, the test **diagnoses why** it
failed and surfaces a stable `error_kind` on the response so the UI can show a
clear, distinct error for each class. The kinds are:

- `none` — success; the model responded.
- `endpoint_unavailable` — the server could not be reached at all (connection
  refused, DNS failure, timeout). Check the host/port and that the server is
  running.
- `bad_url` — the host is reachable but the endpoint or API surface looks wrong
  (e.g. a 404 / 405). Check the base URL and the selected provider — for
  example, pointing the **OpenAI-compatible** provider at a bare
  `http://host:11434` (missing `/v1`) lands here, as does an **Ollama** base URL
  that does not expose the native API.
- `model_not_installed` — the server is reachable and the model is **not**
  installed on it. This is **Ollama-native only**: the test lists the server's
  installed models (via `/api/tags`) *before* the chat probe, so a missing
  model is reported as `Model "<name>" is not installed on this Ollama server.
  Installed: ...` instead of leaking a raw `HTTP 404` from the chat probe. The
  OpenAI-compatible surface cannot list models, so a missing model there cannot
  be detected before the probe.
- `unexpected` — any other failure, with the underlying detail preserved.

For the **Ollama-native** provider a successful test also returns the
`installed_models` list (from `/api/tags`); for the OpenAI-compatible provider
that list is empty because model listing is unsupported on that surface.

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

## Listing installed models (Ollama-native only)

`GET /llm/local/models` reports which models are actually installed on the
configured endpoint, so the UI can offer a picker of real models instead of a
free-text field.

Installed-model detection is **Ollama-native only**: the backend queries
Ollama's native `/api/tags` endpoint (derived from the configured base URL by
stripping a trailing `/v1`, since the native API and the OpenAI-compatible
`/v1` surface share a host). For the **OpenAI-compatible** provider there is no
portable model-listing endpoint, so the call returns
`ok = false`, an empty `models` list, and `error_kind = "unsupported"` (it
never raises and never hits the network).

The endpoint accepts optional `base_url` / `provider` query overrides — the
same override rule the connection test uses — so the UI can list models for
unsaved edits before saving. The response shape is:

```json
{ "provider": "local_ollama", "ok": true, "models": ["llama3.1:8b", "qwen2.5-coder:14b"], "error": null, "error_kind": null }
```

On a transport failure the call does not raise; it returns `ok = false` with a
classified `error_kind`:

- `endpoint_unavailable` — the server could not be reached (connection
  refused, DNS failure, timeout).
- `bad_url` — the host is reachable but returned a status indicating the path
  or API surface is wrong (HTTP 404 / 405).
- `unexpected` — any other failure, with the underlying detail preserved.
- `unsupported` — the configured provider is OpenAI-compatible, which has no
  model-listing endpoint (see above).

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
  "local_attempted": true,
  "local_degraded": false,
  "local_skipped": false,
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
     "local_attempted": true,
     "performance": {
       "prompt_token_estimate": 5810,
       "elapsed_ms": 4210,
       "effective_timeout_seconds": 180
     },
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
budgeted against (the smaller preflight default unless the user configured one
— see *Preflight context budget* below), and `requested_num_ctx` appears when
an Ollama `num_ctx` is configured.

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

### Provider-degradation guardrails (task 132)

Each preflight task routes to the local provider independently, so a slow or
wedged local server would otherwise make *every* eligible task pay a full
timeout before falling back — a single cold or unresponsive server can add
several multiples of the timeout to a run. Preflight therefore tracks a small
**per-run** degraded state:

- The **first** local-LLM timeout in a run marks the provider *degraded*. A
  degraded provider is still attempted on later tasks (a single cold task can
  recover), but the state is recorded.
- After **repeated** timeouts (`LOCAL_SKIP_TIMEOUT_THRESHOLD = 2`) the
  remaining tasks **skip** the local provider entirely and go straight to the
  deterministic extractor, recorded with a `fallback_reason` of
  `"local provider skipped after repeated timeouts"`.

A *timeout* is distinguished from an ordinary schema-validation failure (which
does **not** degrade the provider). Skipping never raises — the deterministic
path always produces a valid artifact — so preflight still never fails the run.
The state is **per run only**: a fresh `run_preflight` starts clean. It is
carried by the in-memory `PreflightResult` (`local_degraded` / `local_skipped`),
the per-task `fallback_reason`, and — for local runs — the top-level
`local_degraded` / `local_skipped` manifest flags (task 133, below).

### Local LLM performance and attempted-but-fell-back (task 133)

So an operator can audit *how* the local provider behaved (and see clearly when
it was tried and then degraded), every preflight run records local performance
and attempt signals in the manifest:

- **Per task that issued a local call** — `local_attempted: true` and a
  `performance` object with `prompt_token_estimate` (the budgeted
  `estimated_input_tokens_final`, not recomputed), `elapsed_ms` (the call's
  measured time; absent on a timeout, which fires before a latency is recorded),
  and `effective_timeout_seconds` (the per-call timeout that bounded it, from
  task 130). A task that fell back *before* contacting the server (over budget,
  or skipped after repeated timeouts) is not "attempted" and records neither
  field.
- **Per run (local runs only)** — top-level `local_attempted` (distinct from
  `fallback_used`: a run can fall back without ever issuing a local call, and a
  run can attempt local and still fall back), plus `local_degraded` and
  `local_skipped` from the guardrail state above. A deterministic-only run omits
  all three so it never gains misleading "attempted" fields.

When the local provider was attempted **and** the run fell back, preflight emits
a stable `Local LLM attempted but fell back: <reason>` line — noting *degraded*
or *skipped after repeated timeouts* when applicable — through both the
`render_preflight_summary` projection (`preflight_summary.md`) and the run's
trace callbacks (`run.log` / progress stream), so the situation is obvious at a
glance instead of looking like a run that never tried the local provider. The
phrasing is fixed (`LOCAL_ATTEMPTED_FELL_BACK_MARKER`) so the run-trace UI can
key on it.

### Preflight context budget (task 132)

Preflight prompts are short — a single job description plus a fixed JSON shape —
and a reasoning model handed a large declared context wastes it for no benefit.
So preflight budgets against a smaller default context window
(`PREFLIGHT_DEFAULT_CONTEXT_WINDOW_TOKENS`) than the general local-LLM default
(`DEFAULT_CONTEXT_WINDOW_TOKENS`, 8192) whenever the user has **not** explicitly
configured `context_window_tokens`. This is a *default*, never a cap: an
explicit user-configured context window is always honoured verbatim. The
over-budget handling (compression / fallback / abort) is unchanged; only the
default the budgeting starts from is smaller. Preflight also never adds a
sequential-thinking / chain-of-thought step — each prompt asks for a single
JSON object and relies on the local-LLM reasoning controls (task 131) to
suppress model-side thinking.
