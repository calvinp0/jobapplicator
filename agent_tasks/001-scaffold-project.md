# Task 001: Normalize Project Scaffold

## Goal

Normalize the existing job-applicator scaffold so future agent tasks can build from clear specs, contracts, ADRs, runtime prompts, and candidate context.

## Background

Read:

- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/contracts/claude_run_directory.md`
- `docs/adr/*.md`
- `runtime_prompts/resume_tailoring.md`

## Scope

Ensure the repository has these top-level folders:

- `backend/`
- `frontend/`
- `extension/`
- `candidate_context/`
- `docs/`
- `docs/adr/`
- `docs/contracts/`
- `runtime_prompts/`
- `agent_tasks/`
- `evals/`
- `runs/`

Add missing `.gitkeep` files where needed.

Add or update `.gitignore`.

Add a root `README.md` describing the MVP workflow and repo layout.

## Out of Scope

Do not implement backend models.

Do not implement frontend UI.

Do not implement the browser extension.

Do not invoke Claude Code.

Do not generate resumes.

## Acceptance Criteria

- Repo structure matches the architecture docs.
- README exists.
- `.gitignore` excludes generated run outputs but keeps `runs/.gitkeep`.
- Existing ADRs and contracts are preserved.
- No product direction is changed.

## Verification

Run:

```bash
tree -a -I ".git|__pycache__|node_modules"
```

## Git 

Stage all changes and commit:
```text
Normalize project scaffold
```

Do not push.



## Candidate context can wait

For now, just put placeholders in candidate files. That is enough for agents.

Example:
```bash
cat > candidate_context/candidate_profile.md <<'EOF'
# Candidate Profile

TODO: Fill with stable candidate background and target positioning.
EOF

cat > candidate_context/evidence_bank.md <<'EOF'
# Evidence Bank

TODO: Add factual evidence that may support resume bullets.
EOF
```


