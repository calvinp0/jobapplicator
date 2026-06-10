# Task 124: Add Provider-Routed Preflight Analysis Pipeline

## Goal

Add a provider-routed preflight analysis pipeline before resume tailoring.

This pipeline should extract structured job/ATS analysis from the job description before the main tailoring prompt runs.

It should support local LLM providers for lower-risk tasks, while keeping Claude Code as the default for full resume tailoring.

This task incorporates the ATS keyword extraction step.

Do not remove Claude Code tailoring.
Do not make local LLM the default for full resume tailoring.
Do not weaken evidence/claim validation.
Do not change Gmail behavior.
Do not change browser extension behavior.

## Background

Task 123 added experimental local LLM provider support, but there is currently no separate ATS/summary step outside the single Claude tailoring prompt.

That was intentional: the app should not force local LLMs directly into the high-risk final resume-writing path.

The next architectural step is to split out lower-risk preflight analysis tasks:

```text
job description
  ↓
provider-routed preflight analysis
  ↓
structured preflight artifacts
  ↓
main tailoring prompt
```

This lets the app use local LLMs safely for bounded extraction/classification work while leaving final resume tailoring, claim audits, and recruiter review under the stronger default path.

## Desired Architecture

Current flow:

```text
create run directory
  ↓
write input files
  ↓
single Claude Code prompt does everything
```

New flow:

```text
create run directory
  ↓
write input files
  ↓
run preflight analysis
      - job summary
      - ATS keyword extraction
      - role requirements
      - evidence gap plan
  ↓
write preflight artifacts under input/preflight/
  ↓
run main Claude Code tailoring prompt
  ↓
backend deterministic DOCX renderer
```

The preflight outputs are advisory structured inputs. The main tailoring prompt must still obey the truthfulness/evidence contract.

## Inspect

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/local_llm.py
backend/app/settings*
backend/app/models.py
backend/app/schemas.py
backend/tests/
runtime_prompts/resume_tailoring.md
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/llm_providers.md
frontend/src/pages/Settings*
frontend/src/api/
```

Search:

```bash
rg "local_llm|LLM Providers|ats|keyword|preflight|tailoring_prompt|job_description|create_run_directory|claude_worker|provider" backend runtime_prompts docs frontend/src tests
```

Use existing project conventions.

## New Preflight Artifacts

Add a preflight directory inside each run:

```text
input/preflight/
```

Write the following artifacts:

```text
input/preflight/job_summary.json
input/preflight/ats_keywords.json
input/preflight/role_requirements.json
input/preflight/evidence_gap_plan.json
input/preflight/preflight_manifest.json
```

Optional human-readable projection:

```text
input/preflight/preflight_summary.md
```

These are input artifacts for the main tailoring run.

## Artifact 1: job_summary.json

Suggested schema:

```json
{
  "company": "Example Aero Labs",
  "job_title": "Scientific Machine Learning Engineer",
  "location": "Remote",
  "employment_type": "Full-time",
  "seniority": "Senior",
  "role_family": "Machine Learning Engineering",
  "summary": "Short neutral summary of the job.",
  "source": "input/job_description.md"
}
```

Rules:
- Extract only from job description/capture.
- Do not infer company facts from outside sources.
- Unknown fields should be `null`, not invented.

## Artifact 2: ats_keywords.json

Suggested schema:

```json
{
  "target_company": "Example Aero Labs",
  "target_job_title": "Scientific Machine Learning Engineer",
  "keywords": [
    {
      "keyword": "Scientific Machine Learning",
      "category": "required",
      "kind": "domain",
      "evidence": "Exact phrase from job description...",
      "priority": "high"
    },
    {
      "keyword": "Python",
      "category": "required",
      "kind": "tool",
      "evidence": "Experience with Python...",
      "priority": "high"
    }
  ],
  "groups": {
    "required": ["Scientific Machine Learning", "Python"],
    "preferred": ["Cloud deployment"],
    "tools": ["Python", "PyTorch"],
    "domains": ["Scientific ML", "simulation"],
    "responsibilities": ["build ML models", "collaborate with researchers"]
  }
}
```

Rules:
- Extract exact and normalized keywords from the JD.
- Classify as:
  - required
  - preferred
  - industry
  - responsibility
- Use priority:
  - high
  - medium
  - low
- Include evidence snippets from the JD.
- Do not decide whether Calvin has the keyword yet. That belongs to tailoring/ATS audit.

## Artifact 3: role_requirements.json

Suggested schema:

```json
{
  "requirements": [
    {
      "id": "req_001",
      "requirement": "Experience building machine learning models for scientific data.",
      "category": "technical",
      "importance": "required",
      "source_quote": "...",
      "keywords": ["machine learning", "scientific data"]
    }
  ],
  "responsibilities": [
    {
      "id": "resp_001",
      "responsibility": "Develop production ML pipelines.",
      "source_quote": "...",
      "keywords": ["production", "ML pipelines"]
    }
  ],
  "screening_signals": [
    "Evidence of Python engineering",
    "Evidence of production ML experience"
  ]
}
```

Rules:
- Requirements must be grounded in the job description.
- Do not add generic requirements not present in the JD.

## Artifact 4: evidence_gap_plan.json

This is a bridge between the JD and evidence sources, but still pre-tailoring.

Suggested schema:

```json
{
  "likely_evidence_targets": [
    {
      "requirement_id": "req_001",
      "requirement": "Experience building machine learning models for scientific data.",
      "search_terms": ["scientific ML", "machine learning", "simulation", "Python"],
      "candidate_evidence_files_to_check": [
        "input/evidence_bank.md",
        "input/project_notes.md",
        "input/evidence_sources/001_vtraceevidence.md"
      ],
      "notes": "Check for scientific ML or computational chemistry projects."
    }
  ],
  "known_risks_before_tailoring": [
    {
      "gap": "Cloud deployment not clearly present in the master resume.",
      "source": "job description requirement",
      "severity": "medium"
    }
  ]
}
```

Rules:
- This artifact may suggest where to look.
- It must not claim evidence exists unless it actually read and found it.
- If implemented as JD-only first pass, name it clearly as a plan, not as evidence confirmation.

First implementation can be JD-only plus selected evidence index names.

Better implementation:
- read `input/evidence_sources_index.md`
- include staged evidence filenames as candidate files to check
- do not deeply audit evidence yet

## Artifact 5: preflight_manifest.json

Required.

Suggested schema:

```json
{
  "created_at": "2026-06-10T12:00:00Z",
  "provider": "local_openai_compatible",
  "model": "llama3.1:8b",
  "fallback_used": false,
  "tasks": [
    {
      "name": "job_summary",
      "provider": "local_openai_compatible",
      "model": "llama3.1:8b",
      "status": "succeeded",
      "output": "input/preflight/job_summary.json"
    },
    {
      "name": "ats_keyword_extraction",
      "provider": "local_openai_compatible",
      "model": "llama3.1:8b",
      "status": "succeeded",
      "output": "input/preflight/ats_keywords.json"
    }
  ]
}
```

If local LLM is unavailable and fallback happens:

```json
{
  "fallback_used": true,
  "fallback_reason": "Local LLM connection failed; used deterministic extractor."
}
```

## Provider Routing

Use the provider policy from Task 123.

Preferred routing:

```text
job_summary:
  local allowed

ats_keyword_extraction:
  local allowed

role_requirements:
  local allowed

evidence_gap_plan:
  local allowed, but conservative

resume_tailoring:
  Claude Code default

claim_audit:
  Claude Code default

recruiter_review:
  Claude Code default
```

If local LLM is disabled or unavailable:
- use deterministic heuristic extraction if available
- or use Claude Code/default provider if project convention supports it
- never silently skip preflight without writing manifest

Minimum acceptable fallback:
- deterministic preflight generator using regex/headings/JD text
- manifest records provider as `deterministic`
- output schemas still written

## Deterministic Fallback

Implement deterministic fallback so preflight does not require local LLM.

At minimum:
- parse job title/company from job capture/description if available
- extract repeated/capitalized/known technical keywords
- detect sections like Requirements, Qualifications, Responsibilities
- generate basic role requirements from bullet/heading blocks
- write valid JSON artifacts

This fallback can be simple but must be stable and tested.

## Local LLM Prompting

When local LLM is enabled for a preflight task:
- send bounded inputs
- do not send unnecessary evidence files
- ask for JSON only
- validate JSON
- retry once with a JSON repair prompt if invalid
- fall back to deterministic extractor if still invalid

Do not pass secrets.
Do not pass the full run directory blindly.

## Validation

Add schema validators for the preflight artifacts.

Validation requirements:
- JSON parses
- required top-level keys exist
- keywords list is an array
- keyword category/priority values are valid
- requirements have IDs and source quotes where possible
- manifest lists provider/model/status/output

If validation fails:
- retry local LLM once if local provider was used
- otherwise fail preflight clearly or write deterministic fallback

Preferred:
- preflight should not fail the entire run unless all fallback attempts fail
- manifest must record any degradation

## Integration with Main Tailoring Prompt

Update `runtime_prompts/resume_tailoring.md` so it reads preflight artifacts when present:

```text
input/preflight/job_summary.json
input/preflight/ats_keywords.json
input/preflight/role_requirements.json
input/preflight/evidence_gap_plan.json
input/preflight/preflight_manifest.json
```

Prompt guidance:
- Treat preflight artifacts as advisory.
- Truthfulness/evidence rules still dominate.
- ATS audit should use `ats_keywords.json` as the starting keyword list.
- If preflight conflicts with the job description, the job description wins.
- If preflight claims evidence exists without support, ignore that claim and note risk.

## Run Directory Contract

Update docs:

```text
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/llm_providers.md
```

Document:
- `input/preflight/` directory
- preflight artifact schemas
- provider routing
- deterministic fallback
- how the main prompt uses preflight outputs
- local LLM experimental status

## Worker Integration

In the run worker flow:

```text
1. create/stage run directory
2. run preflight analysis
3. log preflight progress
4. write input/preflight/*
5. then launch Claude Code tailoring
```

Add log lines:

```text
jobapply: running preflight analysis
jobapply: preflight provider: local_openai_compatible / deterministic / claude_code
jobapply: wrote input/preflight/ats_keywords.json
jobapply: wrote input/preflight/preflight_manifest.json
```

Also append user-facing progress events:

```text
Running preflight job analysis
Extracting ATS keywords
Writing preflight analysis
```

## Settings UI

If Task 123 already added local LLM task toggles, update Settings labels to show these preflight tasks:

```text
Use local LLM for:
[x] Job summary
[x] ATS keyword extraction
[x] Role requirement extraction
[x] Evidence gap planning
[ ] Resume suggestions experimental
[ ] Full resume tailoring experimental
```

Do not turn on local provider by default unless Task 123 already made it opt-in.

## Tests

Add/update backend tests:

1. Preflight deterministic fallback writes all required artifacts.
2. `ats_keywords.json` extracts required/preferred/tool/domain keywords from a fixture JD.
3. `job_summary.json` extracts company/job title when present.
4. `role_requirements.json` extracts requirements/responsibilities from headings/bullets.
5. `evidence_gap_plan.json` references staged evidence index files without claiming unsupported evidence.
6. `preflight_manifest.json` records provider/model/status/output.
7. Local provider path validates JSON output.
8. Invalid local JSON triggers one repair attempt if implemented.
9. Invalid local JSON falls back to deterministic extractor.
10. Local provider disabled uses deterministic fallback.
11. Main tailoring prompt mentions and reads `input/preflight/*`.
12. Worker runs preflight before launching Claude Code.
13. Worker logs preflight provider and artifact paths.
14. Preflight artifacts are staged inside the run directory only.
15. Existing tailoring tests still pass.

Add/update frontend tests if Settings changed:

1. Settings shows local LLM preflight task toggles.
2. ATS keyword extraction toggle appears.
3. Full resume tailoring remains experimental/off by default.

## Acceptance Criteria

- Each tailoring run gets an `input/preflight/` directory.
- `ats_keywords.json` is created before the main tailoring prompt.
- `job_summary.json`, `role_requirements.json`, `evidence_gap_plan.json`, and `preflight_manifest.json` are created.
- Local LLM can be used for preflight when enabled.
- Deterministic fallback works when local LLM is disabled/unavailable.
- Main tailoring prompt reads preflight artifacts.
- ATS audit can start from `ats_keywords.json`.
- Claude Code remains default for final resume tailoring.
- Provider/model/fallback are logged.
- Tests pass.

## Verification

Run:

```bash
python -m pytest
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Ensure Local LLM is disabled.
2. Start a tailoring run.
3. Confirm `input/preflight/` exists.
4. Confirm these files exist and parse:

```text
input/preflight/job_summary.json
input/preflight/ats_keywords.json
input/preflight/role_requirements.json
input/preflight/evidence_gap_plan.json
input/preflight/preflight_manifest.json
```

5. Confirm `preflight_manifest.json` says provider is `deterministic`.
6. Enable local LLM in Settings.
7. Test connection.
8. Enable local LLM for ATS keyword extraction/job summary.
9. Start another tailoring run.
10. Confirm manifest records local provider/model or fallback.
11. Confirm main prompt snapshot includes preflight inputs.
12. Confirm final tailoring still uses Claude Code unless explicitly changed.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add provider-routed preflight analysis
```

Do not push.
