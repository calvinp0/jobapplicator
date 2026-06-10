# Task 123: Add Experimental Local LLM Provider Support

## Goal

Add experimental support for local LLM providers, such as Ollama or an OpenAI-compatible local endpoint, without making them the default for high-risk resume tailoring.

The app should support multiple LLM providers through a common interface:

```text
Claude Code
Local LLM / Ollama
OpenAI-compatible endpoint later
```

Local LLMs should initially be allowed only for low-risk or experimental tasks unless the user explicitly chooses them.

Do not remove Claude Code support.
Do not make local LLM the default resume tailoring provider.
Do not weaken claim/evidence validation.
Do not change Gmail behavior.
Do not change browser extension behavior.

## Product Rationale

Local LLMs may be useful for:
- privacy-sensitive runs
- cheap iteration
- job description summarization
- ATS keyword extraction
- email classification
- simple suggestion drafting
- offline experimentation

But local models may underperform on:
- nuanced resume tailoring
- evidence-grounded claim auditing
- recruiter review
- strict JSON generation
- instruction following under long context

Therefore, local LLM support must be:
- opt-in
- visible in Settings
- validated with schemas
- logged clearly
- easy to fall back from

## Inspect

Inspect:

```text
backend/app/claude_worker.py
backend/app/routers/
backend/app/settings*
backend/app/models.py
backend/app/schemas.py
backend/tests/
frontend/src/pages/Settings*
frontend/src/api/
runtime_prompts/
docs/contracts/
```

Search:

```bash
rg "Claude Code|claude|LLM|provider|model|tailoring|gmail classification|ats|keyword|settings" backend frontend runtime_prompts docs tests
```

Use existing project conventions.

## Provider Model

Introduce a provider abstraction.

Suggested concepts:

```text
LLMProvider
LLMProviderConfig
LLMTaskPolicy
LLMCallResult
```

Providers:

```text
claude_code
local_openai_compatible
ollama
```

For first implementation, support one local mode:

```text
local_openai_compatible
```

because Ollama can expose OpenAI-compatible chat endpoints depending on setup, and other local servers can too.

If Ollama native support is easier, use:

```text
ollama
```

but keep the interface provider-neutral.

## Settings UI

Add a Settings section:

```text
LLM Providers
```

Fields:

```text
Default provider:
  Claude Code
  Local LLM experimental

Local LLM endpoint:
  http://localhost:11434
  or OpenAI-compatible base URL

Model name:
  llama3.1:8b
  qwen2.5-coder:14b
  mistral-small
  etc.

Timeout seconds:
  60

Use local LLM for:
  [ ] Job description summarization
  [ ] ATS keyword extraction
  [ ] Email classification
  [ ] Resume suggestions experimental
  [ ] Full resume tailoring experimental
```

Include warning copy:

```text
Local LLM support is experimental. High-risk outputs such as final resume tailoring and claim audits should use Claude Code unless you review carefully.
```

Add:

```text
[Test connection]
```

which calls the backend and shows:
- connected
- model responded
- error/timeout

## Backend Settings

Persist settings in the existing settings system.

Suggested config:

```json
{
  "default_provider": "claude_code",
  "local_llm": {
    "enabled": false,
    "provider": "openai_compatible",
    "base_url": "http://localhost:11434/v1",
    "model": "llama3.1:8b",
    "timeout_seconds": 60,
    "allowed_tasks": {
      "job_summary": true,
      "ats_keywords": true,
      "email_classification": true,
      "resume_suggestions": false,
      "resume_tailoring": false,
      "claim_audit": false
    }
  }
}
```

Do not commit user secrets.

If API key is needed, allow optional API key but keep it local/settings-managed and masked in UI.

## Backend Provider Client

Add a small client for local OpenAI-compatible chat completion.

Suggested file:

```text
backend/app/llm_providers.py
```

Support:

```text
chat(messages, response_format=None, timeout=None)
test_connection()
```

First implementation can use:
- Python standard library `urllib`
- or existing HTTP client dependency if already present

Do not add a huge dependency unless needed.

## Task Policy

Define which tasks can use which provider.

Suggested first policy:

```text
job_description_summary:
  local allowed

ats_keyword_extraction:
  local allowed

email_classification:
  local allowed

resume_suggestions:
  local experimental

resume_tailoring:
  claude_code default, local disabled unless explicitly enabled

claim_audit:
  claude_code default

recruiter_review:
  claude_code default
```

Do not let local LLM silently take over full resume tailoring unless the user explicitly enables it.

## Schema Validation

For any local LLM task producing structured output:
- validate JSON
- validate required fields
- retry once with a repair prompt if invalid
- if still invalid, fail clearly or fall back to Claude Code where applicable

Log:

```text
LLM provider: local_openai_compatible
Model: ...
Task: ats_keyword_extraction
Schema validation: passed/failed
Fallback used: yes/no
```

## Initial Integration Scope

Keep first integration small.

Minimum useful integration:
1. Settings UI and backend settings.
2. Test connection endpoint.
3. Local LLM client.
4. Provider capability/policy metadata.
5. Use local LLM optionally for ATS keyword extraction or job description summary if such a separate step exists.
6. Log provider/model in run metadata.

Do not force full resume tailoring through local LLM in the first implementation.

If the codebase does not yet have separate ATS extraction step outside the big Claude prompt, just implement provider config/test connection and document it as ready for future task integration.

## Optional Experimental Resume Suggestions

If simple, allow an experimental endpoint:

```text
POST /api/llm/local/suggest-resume-edits
```

that takes small bounded input and returns suggestions JSON.

This must:
- validate suggestion schema
- mark output as experimental
- not overwrite final resume automatically
- require user review

Do not block task completion on this endpoint.

## Run Metadata

Runs should record provider information where applicable.

Suggested:

```json
{
  "llm_provider": "claude_code",
  "llm_model": "claude-code",
  "local_llm_enabled": false
}
```

For local tasks:

```json
{
  "task": "ats_keyword_extraction",
  "provider": "local_openai_compatible",
  "model": "llama3.1:8b"
}
```

## Documentation

Update:

```text
docs/contracts/agent_orchestration.md
docs/llm_providers.md
README_INSTALL.md
```

Document:
- local LLM is experimental
- recommended tasks
- Ollama/OpenAI-compatible setup
- how to test connection
- why Claude Code remains default for final tailoring
- schema validation/fallback behavior

## Tests

Add/update backend tests:

1. Local LLM settings can be saved/loaded.
2. API key/secret is masked in read responses if supported.
3. Test connection endpoint handles success.
4. Test connection endpoint handles timeout/error.
5. Local provider client formats OpenAI-compatible request.
6. Task policy defaults full resume tailoring to Claude Code.
7. Local provider is allowed for low-risk tasks.
8. Local provider is blocked for resume tailoring unless explicitly enabled.
9. Invalid JSON from local provider fails validation.
10. Run metadata records provider/model where applicable.

Add/update frontend tests:

1. Settings renders LLM Providers section.
2. Local LLM fields are editable.
3. Test connection button calls backend.
4. Warning text appears for experimental local LLM.
5. Full resume tailoring local option is clearly experimental/off by default.
6. Saved settings are displayed correctly.

## Acceptance Criteria

- Settings has LLM Providers section.
- User can configure local endpoint/model.
- User can test local LLM connection.
- Local LLM is clearly marked experimental.
- Claude Code remains default for resume tailoring.
- Task policy prevents accidental local use for high-risk outputs.
- Provider/model can be logged in run metadata.
- Backend tests pass.
- Frontend builds/tests pass.

## Verification

Run:

```bash
python -m pytest
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Start Ollama or a local OpenAI-compatible server if available.
2. Open Settings.
3. Enable Local LLM experimental.
4. Set endpoint/model.
5. Click Test connection.
6. Confirm success or clear error.
7. Confirm local LLM is not automatically used for resume tailoring.
8. Confirm Settings warning is visible.
9. Confirm Claude Code remains default.
10. Confirm run metadata/provider display if implemented.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add experimental local LLM provider
```

Do not push.
