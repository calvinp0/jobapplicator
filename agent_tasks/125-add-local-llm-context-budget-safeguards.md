# Task 125: Add Local LLM Context Budget Safeguards

## Goal

Add explicit context-window, token-budget, compression, and fallback safeguards for local LLM usage.

Local LLMs are not Claude Code. They may have much smaller context windows, slower inference, weaker JSON reliability, and higher risk of silent truncation. The app must never silently overfill or truncate a local LLM prompt.

This task extends the local LLM/provider-routed preflight architecture with safety controls.

Do not remove Claude Code support.
Do not make local LLM the default for final resume tailoring.
Do not weaken evidence/claim validation.
Do not silently truncate local LLM inputs.
Do not change Gmail behavior.
Do not change browser extension behavior.

## Background

Claude Code can handle very large context windows. Local models may only support:

```text
4k
8k
16k
32k
128k if specially configured
```

A local model may also run with a smaller effective context than advertised depending on:
- model file
- quantization
- server configuration
- Ollama `num_ctx`
- GPU/CPU memory limits
- OpenAI-compatible server limits

Therefore the app needs explicit safeguards before local LLM calls.

## Required Design Principle

Before every local LLM call:

```text
1. Determine model/task context budget.
2. Estimate input tokens.
3. Reserve output tokens.
4. If input exceeds budget, compress/select/chunk deterministically.
5. Re-estimate.
6. If still too large, abort or fall back.
7. Log what happened.
8. Never silently truncate.
```

## Inspect

Inspect:

```text
backend/app/local_llm.py
backend/app/settings*
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/preflight*
backend/tests/
frontend/src/pages/Settings*
frontend/src/api/
docs/llm_providers.md
docs/contracts/agent_orchestration.md
docs/contracts/claude_run_directory.md
```

Search:

```bash
rg "local_llm|context|tokens|num_ctx|timeout|preflight|ats_keywords|job_summary|provider|fallback|truncate|compression" backend frontend docs tests
```

Use existing project conventions.

## Settings Requirements

Extend Local LLM settings with explicit capability fields:

```text
Context window tokens
Reserved output tokens
Max input tokens
Abort on over-budget
Allow deterministic compression
Allow deterministic fallback
```

Suggested defaults:

```json
{
  "context_window_tokens": 8192,
  "reserved_output_tokens": 1200,
  "max_input_tokens": 6500,
  "allow_compression": true,
  "allow_fallback": true,
  "abort_on_over_budget": false
}
```

Rules:
- `max_input_tokens` should be computed from context window minus reserved output unless explicitly overridden.
- If values are invalid, reject settings with clear errors.
- UI should explain that local models often have much smaller context windows than Claude.

Settings copy:

```text
Local models have limited context windows. JobApplicator will estimate prompt size before each local call and will compress, fall back, or abort rather than silently truncate inputs.
```

## Model Capability Detection

If using Ollama or OpenAI-compatible local endpoints, best-effort detect model capabilities when possible.

Possible options:
- Store user-configured context window manually.
- If Ollama endpoint exposes model details, read them.
- If unavailable, use configured defaults.

Do not block on perfect auto-detection.

`Test connection` should report:

```text
Connected
Model responded
Configured context window: 8192 tokens
Usable input budget: 6500 tokens
```

If auto-detection fails:

```text
Connected, but model context window could not be detected. Using configured value: 8192.
```

## Token Estimation

Add a lightweight token estimator.

Suggested file:

```text
backend/app/context_budget.py
```

Do not add a heavy dependency unless already available.

Approximation is acceptable:

```text
estimated_tokens = ceil(character_count / 4)
```

or:
- word count based estimate
- optional model-specific tokenizer later

The estimator must be conservative.

Expose functions such as:

```python
estimate_tokens(text: str) -> int

build_context_budget(
    context_window_tokens: int,
    reserved_output_tokens: int,
    max_input_tokens: int | None
) -> ContextBudget

check_context_budget(
    prompt: str,
    budget: ContextBudget
) -> ContextBudgetCheck
```

## Budget Check Result

Return structured info:

```json
{
  "estimated_input_tokens": 9320,
  "context_window_tokens": 8192,
  "reserved_output_tokens": 1200,
  "max_input_tokens": 6500,
  "over_budget": true,
  "overflow_tokens": 2820,
  "action": "compress"
}
```

Log this info in run metadata or preflight manifest when local LLM is used.

## Prompt Assembly Rules

For local LLM preflight tasks, never assemble prompts by dumping entire run directories.

Each task should have a bounded input assembler.

### Job summary
Allowed input:
- job_capture
- job_description

Not allowed:
- evidence files
- full project notes
- prior resumes

### ATS keyword extraction
Allowed input:
- job_description
- job_capture

Not allowed:
- full evidence sources
- full resume variants

### Role requirement extraction
Allowed input:
- job_description
- job_capture

Not allowed:
- evidence sources unless explicitly needed

### Evidence gap planning
Allowed input:
- job_summary
- ats_keywords
- role_requirements
- evidence_sources_index
- short evidence source names/summaries

Not allowed by default:
- full evidence files
- full DOCX extracted text
- giant project_notes.md

### Resume suggestions experimental
Allowed input:
- tailored/current resume JSON or compact resume projection
- job_summary
- ats_keywords
- role_requirements
- selected evidence snippets only

Not allowed:
- entire evidence corpus without selection

## Deterministic Compression

If a local LLM task is over budget and compression is allowed, compress/select inputs deterministically before calling the model.

Examples:

### Job description compression
Keep:
- title/company/location block
- headings
- bullet lists under Requirements/Qualifications/Responsibilities
- repeated keywords
- first N and last N paragraphs
- paragraphs containing skill/tool keywords

Drop:
- legal boilerplate
- equal opportunity statements
- cookie/banner text
- nav/footer text
- unrelated company marketing if too long

### Evidence index compression
Keep:
- source id
- title/name
- type/format
- short description/summary if present
- staged path

Drop:
- full evidence body

## Abort / Fallback Behavior

If input remains over budget after compression:

If `allow_fallback`:
- skip local LLM call
- use deterministic fallback
- record fallback reason

If `abort_on_over_budget`:
- abort that local task with a clear error
- do not silently continue pretending local LLM was used

If neither fallback nor abort is allowed:
- fail task with clear error

Required log example:

```text
jobapply: local LLM input over budget for ats_keyword_extraction: estimated 9320 > 6500
jobapply: compressed input to 5810 estimated tokens
jobapply: local LLM budget check passed
```

Fallback example:

```text
jobapply: local LLM input over budget after compression; using deterministic ATS extractor
```

## No Silent Truncation

Do not use simple slicing like:

```python
prompt = prompt[:max_chars]
```

unless it is part of a named deterministic compression strategy and is logged as such.

Any truncation/compression must:
- be intentional
- be task-specific
- be logged
- preserve headings/requirements where possible

## Preflight Manifest Integration

Extend `input/preflight/preflight_manifest.json` with context budget information for each local LLM task:

```json
{
  "name": "ats_keyword_extraction",
  "provider": "local_openai_compatible",
  "model": "llama3.1:8b",
  "status": "succeeded",
  "context": {
    "context_window_tokens": 8192,
    "reserved_output_tokens": 1200,
    "max_input_tokens": 6500,
    "estimated_input_tokens_initial": 9320,
    "estimated_input_tokens_final": 5810,
    "compression_used": true,
    "fallback_used": false,
    "over_budget": false
  }
}
```

If fallback was used:

```json
{
  "status": "fallback",
  "provider": "deterministic",
  "fallback_reason": "local LLM input remained over budget after compression"
}
```

## UI Requirements

In Settings > LLM Providers:
- show configured context window
- show reserved output tokens
- show usable input budget
- explain local LLM context risks
- show warning if context window is small

Suggested warning:

```text
This context window is small. Local LLM will only be used for compact preflight tasks. Large evidence-heavy tasks will use deterministic fallback or Claude Code.
```

## Tests

Add/update backend tests:

1. Token estimator is conservative and deterministic.
2. Context budget calculation reserves output tokens.
3. Budget check flags over-budget prompts.
4. Budget check passes in-budget prompts.
5. Local LLM call refuses over-budget prompt when no compression/fallback allowed.
6. Local LLM call uses deterministic compression when enabled.
7. Local LLM task falls back when still over budget.
8. Prompt assembler for ATS extraction does not include evidence files.
9. Prompt assembler for job summary does not include evidence files.
10. Evidence gap prompt uses evidence index summaries, not full evidence files.
11. Preflight manifest records context budget info.
12. Logs include over-budget/compression/fallback messages.
13. Settings validation rejects impossible budgets.
14. Settings UI displays context window and usable budget.

Add/update frontend tests:

1. Settings renders context window field.
2. Settings renders reserved output token field.
3. Settings displays usable input budget.
4. Settings shows local context warning.
5. Invalid budget input shows validation error.

## Acceptance Criteria

- Local LLM calls have explicit context budget checks.
- Local LLM prompts are never silently truncated.
- Over-budget local calls compress, fall back, or abort explicitly.
- Preflight manifest records estimated token usage and fallback/compression.
- Settings exposes context window/budget fields.
- Local LLM test connection shows configured budget.
- ATS extraction/local preflight does not send unnecessary evidence files.
- Claude Code remains default for final resume tailoring.
- Tests pass.

## Verification

Run:

```bash
python -m pytest
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Open Settings > LLM Providers.
2. Set context window to a small value, e.g. 2048.
3. Enable local LLM for ATS keyword extraction.
4. Start a tailoring run with a long job description.
5. Confirm the preflight manifest records:
   - initial estimated tokens
   - final estimated tokens
   - compression/fallback
6. Confirm logs mention over-budget handling.
7. Confirm no local prompt silently truncates content.
8. Confirm final tailoring still uses Claude Code.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add local LLM context safeguards
```

Do not push.
