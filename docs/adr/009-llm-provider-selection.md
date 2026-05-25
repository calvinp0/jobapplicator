# ADR-009: LLM Provider Selection for Auto Tailoring

## Status

Accepted

## Context

The `auto` tailoring flow (see `tailoring_method` in
`docs/contracts/claude_run_directory.md`, introduced by task 058) currently
invokes a single LLM-driven CLI worker: Claude Code. Other CLI-based LLM
workers — Codex CLI, Gemini CLI, and likely more in the future — can
produce the same outputs from the same run-directory inputs. Users have
asked to choose which CLI runs the `auto` flow without disturbing the rest
of the system.

The decision must reconcile several existing constraints:

- `tailoring_method` already distinguishes `auto` from `word_handoff`.
  Provider selection is a sub-dimension of the `auto` path; it is
  orthogonal to `tailoring_method` and does not apply to `word_handoff`
  (which is a manual Claude-for-Word flow with no backend CLI invocation).
- ADR-002 (Claude Code Worker Boundary) holds the backend as the source of
  truth: the worker may only read and write inside its run directory; the
  backend creates inputs, validates outputs, computes hashes, and imports
  approved artifacts.
- ADR-004 (Evidence-Constrained Resume Tailoring) requires that concrete
  claims be supported by approved source material and that unsupported
  requirements appear as gaps in the claim audit rather than as silent
  insertions.
- The run-directory contract describes the required outputs
  (`output/tailored_resume.docx`, `output/tailored_resume.md`,
  `output/change_log.md`, `output/claim_audit.md`). Any provider must
  satisfy that contract or its run fails post-invocation validation.

## Decision

### Configurable provider for the `auto` flow

The backend supports a configurable LLM provider for the `auto` tailoring
flow. The provider is selected per run; it does not apply to
`word_handoff` runs. Initial providers:

- `claude_code` — the existing Claude Code CLI worker. This is the
  default provider and preserves current behavior for runs that do not
  specify one.
- `codex` — the Codex CLI worker.
- `gemini` — the Gemini CLI worker.

New providers may be added without changing the run-directory contract,
the backend's validation/import logic, or `runtime_prompts/`. Adding a
provider is purely a registry change plus a CLI shim.

### Provider identity

A provider is identified by a stable string id (`claude_code`, `codex`,
`gemini`, etc.). For each provider the registry records:

- the stable id used in the database and the API;
- the CLI binary to invoke, with an env-var override so an operator can
  point at a non-default install location;
- the non-interactive invocation shape — the worker passes the prompt on
  stdin and the CLI writes outputs under the run's `output/` directory.
  Anything beyond that (permission-mode flags, allowlist flags, dry-run
  hooks) is provider-specific glue and lives in the provider shim.

### Run record persists the provider

Each `ClaudeRun` persists the provider id used to execute it. The run
record is self-describing: a reader can determine, after the fact, which
CLI produced the artifacts without joining against external state. The
provider id stays on the run even if the user later changes the
application-wide default.

The `ClaudeRun` model and `claude_worker` module names are retained for
continuity; renaming them is explicitly out of scope (see below).

### Default lives in app settings

The user-facing default provider lives in app settings and is editable
through the Settings page. New runs adopt the current default unless the
run-creation request explicitly overrides it. The default is `claude_code`
on a fresh install.

### Cross-provider invariants

The following rules apply identically to every provider; they are not
configurable per-provider and are reasserted by this ADR:

- **Worker boundary (ADR-002).** No provider may mutate the database. The
  backend remains the source of truth. Each provider may read only from
  its run directory's `input/` (per the read boundary in the run-directory
  contract) and may write only the files in the write boundary (`output/`
  required files plus `progress/progress.log`).
- **Evidence constraint (ADR-004).** No provider may invent unsupported
  claims. The shared runtime prompt enforces evidence constraints and the
  claim audit must continue to flag gaps. A provider that silently
  inserts unsupported claims is non-conforming, regardless of how
  fluently it produces a draft.
- **Output contract.** A run is `completed` only when the CLI exits `0`
  *and* the full required-output set under `output/` is present. The
  backend validates outputs after invocation and at import. Providers do
  not get a relaxed validation path.

### Non-goals

This iteration explicitly excludes:

- **Hosted-API providers.** Only CLI-based workers are in scope. Calling
  a vendor's HTTP API directly from the backend is a different boundary
  decision and is not addressed here.
- **Provider-specific runtime prompts.** All providers share the existing
  `runtime_prompts/resume_tailoring.md`. Per-provider prompt forks are
  not introduced now; if a future provider needs prompt-level differences,
  that warrants a separate ADR.
- **Fallback or cascade between providers.** If the selected provider's
  run fails, the run is marked `failed`; the backend does not silently
  retry with a different provider. The user retries with their chosen
  provider (or picks a different one explicitly).

## Rationale

Treating provider as a sub-dimension of `auto` keeps `tailoring_method`
focused on *how the draft is produced overall* (a backend-driven
subprocess vs. a manual Word handoff) and isolates the CLI choice to a
single axis. Conflating the two would force `tailoring_method` to grow a
combinatorial set of values (`auto_claude_code`, `auto_codex`,
`auto_gemini`, `word_handoff`), which collapses two independent decisions
into one enum.

Reusing the run-directory contract as the conformance surface means the
provider abstraction is small: any CLI that can read the documented
inputs and write the documented outputs is a candidate provider. The
backend's existing validation, hashing, and import logic does not need
provider-specific branches.

Persisting the provider id on each `ClaudeRun` makes the run record
self-describing. Provenance for a generated draft must survive the user
changing their default later; recording the id at run creation time
prevents drift between "what produced this artifact" and "what the user
currently prefers."

Refusing a fallback/cascade is deliberate. Automatic fallback would
double the number of (provider, prompt) pairs we need to reason about for
any given failure, and it would obscure which CLI actually produced a
given draft. A failed run is a clear, recoverable event; surfacing it to
the user is preferable to silently changing what they asked for.

Reasserting ADR-002 and ADR-004 across providers is necessary because
those invariants are easy to lose in a registry-style abstraction. A new
provider shim is the most likely place to accidentally broaden the write
scope or to skip claim-audit enforcement; the ADR documents that those
checks live at the contract layer, not the provider layer.

## Consequences

- A follow-up backend task introduces the provider registry, persists
  the provider id on `ClaudeRun`, and threads it through run creation.
- A follow-up backend task adds the app-settings field for the default
  provider and exposes it through the Settings API.
- A follow-up frontend task surfaces the default-provider control on the
  Settings page and (optionally) a per-run override on the generation UI.
- The run-directory contract does not change: any provider must satisfy
  the existing input/output boundaries verbatim.
- Runtime prompts under `runtime_prompts/` are unchanged: all providers
  share `resume_tailoring.md`.
- `ClaudeRun` and the `claude_worker` module keep their names. The
  abstraction lives behind them; renaming is deferred to a future ADR if
  it ever becomes worth the churn.
- Adding a future provider (e.g. a hypothetical `llamacli`) requires
  only a registry entry, a CLI shim, and a conformance check against the
  run-directory contract. No schema migration, no contract change.

## Alternatives Considered

- **Hard-code one provider and keep Claude Code as the only worker.**
  Rejected. Users have asked for choice, and CLI-based workers are
  cheap to swap behind a small shim. Holding the line at one provider
  forfeits a low-cost improvement.
- **Encode the provider into `tailoring_method` (e.g.
  `auto_claude_code`, `auto_codex`).** Rejected. Conflates two
  independent axes — the production mechanism (auto vs. word_handoff)
  and the CLI used by the auto path — and produces a combinatorial enum
  that downstream code has to demultiplex anyway.
- **Per-provider runtime prompts.** Rejected for this iteration. Forking
  prompts per provider would double the surface area we evolve and would
  let providers drift on evidence constraints. If a specific provider
  needs prompt differences later, that warrants its own ADR with the
  evidence-constraint guardrails explicit.
- **Hosted-API providers as a peer option (Claude API, OpenAI API,
  Gemini API direct).** Rejected for this iteration. A hosted API is a
  different trust and networking boundary and would require its own
  decisions about credentials, retries, and offline behavior. The local
  CLI shape is what the backend already speaks; expanding it later is a
  separate ADR.
- **Automatic fallback to a different provider on failure.** Rejected.
  Hides which provider produced a given artifact, complicates
  provenance, and obscures errors the user should see.
- **Rename `ClaudeRun` and `claude_worker` to provider-neutral names.**
  Rejected for now. The names are load-bearing for the database schema,
  routers, and tests; renaming is high-churn for no behavioral gain.
  Future ADRs may revisit it.

## Notes

- This ADR refers to and is bounded by ADR-002 (Claude Code Worker
  Boundary) and ADR-004 (Evidence-Constrained Resume Tailoring). Both
  invariants apply to every provider; this ADR does not relax either.
- The run-directory contract is in
  `docs/contracts/claude_run_directory.md`. Any provider must satisfy
  its read and write boundaries.
- The `tailoring_method` field (task 058) is unchanged by this ADR.
  Provider selection only affects runs whose `tailoring_method == auto`.
- Downstream work (not part of this ADR): provider-registry backend
  task, app-settings default-provider task, frontend Settings/run
  override task.
