# Task 147: Add local LLM admin monitor and streaming diagnostics

## Status

ready

## Goal

Add an admin/debug console for local LLM requests so the user can see what really happened during preflight runs.

The compact provider trace is useful for normal application workflow, but it is not enough for diagnosing local LLM behavior. When a local LLM step times out after 600 seconds, the app must show whether the timeout happened during connection, prompt evaluation, thinking generation, content generation, or a stalled stream.

## Context

Recent local LLM runs show:

```text
Preflight: deterministic backend · Tailoring: Claude Code · DOCX: Backend

Local LLM step fell back to deterministic extractor: generation timed out after 600s: reached http://100.104.129.123:11434/api/chat but it did not finish generating
```

The run trace shows local LLM attempts falling back after 600 seconds, but it does not show:

- whether Ollama started generating
- time to first token
- prompt eval duration
- generated token count before timeout
- whether output was thinking-only
- whether `message.content` ever appeared
- whether generation stalled
- tokens per second
- requested options such as `num_ctx`, `num_predict`, and temperature
- active local provider degraded state
- whether fallback happened after timeout or after explicit abort

The user needs an admin console that can show local LLM requests live.

## Product design

Add an Admin Console or Diagnostics page with a Local LLM Monitor section.

Possible route:

```text
/admin/local-llm
```

or a tab inside Settings:

```text
Settings → Local LLM → Diagnostics
```

The normal application run page should remain compact. The admin monitor can be more technical.

## Admin monitor UI requirements

Show:

```text
Local LLM Monitor
```

Sections:

### 1. Active request

Show the currently running local LLM request if any:

```text
Run                <application/tailoring run title>
Step               ATS keywords
Provider           Ollama
Model              qwen3.5:9b
Endpoint           100.104.129.123:11434 /api/chat
Started            12:14:21
Elapsed            04:12
Status             Generating
```

### 2. Request options

Show safe request metadata:

```text
Configured budget  16000
Estimated input    3842 tokens
Requested num_ctx  16000
num_predict        512
Temperature        0
Stream             true
```

Do not show API keys or authorization headers.

### 3. Live generation

Show live metrics when streaming is enabled:

```text
Prompt eval        done / 3842 tokens / 31.2s
Generated          187 tokens
Tokens/sec         2.8
Thinking detected  yes
Content detected   no
Last token age     0.4s
```

### 4. Server/context

Show known server context metadata:

```text
Server-reported max context     262144
Requested num_ctx               16000
Active runner context           unknown
Trust status                    unverified
Manual check                    run `ollama ps` on the Ollama server
```

### 5. Event timeline

Show recent diagnostic events:

```text
12:14:21 request created
12:14:21 connected to Ollama
12:14:22 prompt upload complete
12:14:53 first chunk received
12:14:53 thinking stream started
12:15:20 generated 100 thinking tokens
12:24:21 generation timeout; fallback used
```

The event stream should update live while the request is running.

## Backend requirements

### 1. Add local LLM diagnostic event store

Add an in-memory rolling diagnostic store for local LLM events.

It should keep recent events for:

- active request
- recent completed requests
- recent failed requests

Suggested retention:

```text
last 1000 local LLM events
last 50 local LLM requests
```

No sensitive content should be stored by default.

### 2. Add request-level diagnostic record

Each local LLM request should have a diagnostic record with:

```json
{
  "request_id": "uuid",
  "run_id": "string or null",
  "step": "ats_keywords",
  "provider": "ollama",
  "model": "qwen3.5:9b",
  "endpoint_host": "100.104.129.123:11434",
  "endpoint_path": "/api/chat",
  "status": "running",
  "started_at": "ISO-8601",
  "completed_at": null,
  "elapsed_ms": 0,
  "configured_context_budget_tokens": 16000,
  "usable_input_budget_tokens": 14800,
  "estimated_input_tokens": 3842,
  "requested_num_ctx": 16000,
  "num_ctx_sent": true,
  "num_predict": 512,
  "temperature": 0,
  "stream": true,
  "server_reported_context_tokens": 262144,
  "active_runner_context_tokens": null,
  "context_trust_status": "unverified",
  "time_to_first_chunk_ms": null,
  "time_to_first_content_ms": null,
  "prompt_eval_count": null,
  "prompt_eval_duration_ms": null,
  "eval_count": 0,
  "eval_duration_ms": 0,
  "approx_generated_chars": 0,
  "thinking_detected": false,
  "content_detected": false,
  "last_chunk_at": null,
  "fallback_used": false,
  "fallback_reason": null,
  "error": null
}
```

### 3. Use streaming for Ollama diagnostics

For Ollama-native provider, support `stream: true` internally.

The backend should:

- receive JSON lines from Ollama
- update diagnostic records as chunks arrive
- detect whether chunks contain `message.thinking`
- detect whether chunks contain `message.content`
- count approximate generated chars/tokens
- record time to first chunk
- record time to first content
- store final Ollama metrics if provided:
  - `total_duration`
  - `load_duration`
  - `prompt_eval_count`
  - `prompt_eval_duration`
  - `eval_count`
  - `eval_duration`

The final parsed model output should still use only `message.content`, not thinking.

### 4. Add generation controls

For local preflight calls, set bounded defaults:

```text
temperature: 0
num_predict:
  job_summary: 512
  ats_keywords: 384
  role_requirements: 512
  evidence_gap_plan: 768
```

Make these configurable later, but defaults should be applied now.

### 5. Classify timeout type

Differentiate timeout errors:

```text
connect_timeout
read_timeout
generation_timeout
stalled_generation_timeout
provider_degraded_skip
```

If the backend connected and received at least one chunk, but did not finish before timeout, report:

```text
generation_timeout
```

If no chunk arrived:

```text
read_timeout
```

If chunks stopped arriving for a configurable idle timeout:

```text
stalled_generation_timeout
```

### 6. Provider degraded behavior

After repeated local LLM timeouts in a run, mark provider degraded for that run.

The diagnostic store should show:

```text
local provider marked degraded after 2 timeout failures
remaining local LLM steps skipped
```

### 7. Add API endpoints

Add admin diagnostics endpoints, for example:

```text
GET /api/admin/local-llm/diagnostics
GET /api/admin/local-llm/diagnostics/stream
```

The non-stream endpoint returns current snapshot.

The stream endpoint can use SSE if the app already has SSE patterns. If not, polling every 1-2 seconds is acceptable.

Returned data should include:

- active request
- recent requests
- recent events
- provider degraded state if applicable

### 8. Security and privacy

Do not store or expose:

- API keys
- authorization headers
- full raw prompts by default
- full raw thinking text by default
- full raw generated content by default

It is acceptable to expose:

- generated char counts
- thinking detected true/false
- content detected true/false
- short sanitized error messages
- safe endpoint host/path

## Frontend requirements

Add a Local LLM Monitor page or Settings diagnostics tab.

The page should show:

- active request card
- request options
- live generation metrics
- server/context section
- event timeline
- recent completed/failed local LLM requests

The UI may poll every 1-2 seconds.

Keep the normal application run page compact. Add only a small link near the provider trace when local LLM fails:

```text
Open Local LLM diagnostics
```

## Run trace integration

When a local LLM step times out, the run trace should link to the diagnostic record if available.

Example:

```text
Job summary
Ollama attempted → deterministic fallback
generation timeout after 600s
Diagnostics: request abc123
```

## Tests

Add backend tests for:

- diagnostic record is created for local LLM request
- Ollama streaming chunks update diagnostic state
- thinking chunks are detected but not persisted as raw thinking text
- content chunks are detected
- final Ollama metrics are recorded
- timeout classification distinguishes no chunks vs partial chunks
- provider degraded state is recorded after repeated timeouts
- diagnostic API does not expose API keys or raw prompts
- local preflight sends `num_predict` and `temperature: 0`

Add frontend tests for:

- Local LLM Monitor displays active request
- live metrics render from diagnostic snapshot
- event timeline renders recent events
- timeout/fallback/degraded state is visible
- application run trace links to diagnostics when available
- raw prompt/thinking/API keys are not rendered

## Acceptance criteria

- User can see local LLM requests live.
- User can tell whether Ollama was reached.
- User can tell whether generation started.
- User can tell whether the model was producing thinking or content.
- User can see elapsed time, token/chunk counts, and timeout classification.
- Local preflight calls use bounded `num_predict` defaults.
- Thinking text is not stored or displayed by default.
- The normal application run page remains compact.
- Sensitive data is not exposed.

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

## Manual verification

Configure Ollama:

```text
Provider: Ollama
Endpoint: http://100.104.129.123:11434
Model: qwen3.5:9b
JobApplicator context budget: 16000
Ollama num_ctx: 16000
Timeout: 600
```

Start a resume tailoring run.

Open Local LLM Monitor.

Expected:

- active local LLM request appears while preflight is running
- request shows provider/model/endpoint/options
- live generation metrics update if Ollama streams
- thinking detected is shown if the model emits thinking
- timeout is classified as generation/read/stalled timeout
- fallback is shown
- subsequent skipped steps show provider degraded reason

## Out of scope

- Do not package the app as a single local web app.
- Do not add public internet deployment.
- Do not route full resume tailoring to local LLM by default.
- Do not expose raw prompts or thinking by default.
- Do not change Gmail.
- Do not change browser extension capture.
