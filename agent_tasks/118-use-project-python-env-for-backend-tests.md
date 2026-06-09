# Task 118: Use Project Python Environment for Backend Tests

## Goal

Make backend tests always run in the JobApplicator backend Python
environment, not whatever conda env happens to be active when the
harness or operator runs verification.

Observed failure: `pytest` ran under
`/home/calvin/miniforge3/envs/rmg_env` and could not import the backend
dependencies (`fastapi`, `pydantic`, `docx` / `python-docx`).

Do not change Gmail behavior.
Do not change browser extension behavior.

## Background

`scripts/agentctl.sh` runs each task's `verification` commands with
`bash -c` inside the task worktree. Those commands inherit the operator's
active conda env. A bare `pytest` therefore resolves to whichever
environment is active — including unrelated science envs such as
`rmg_env` that lack the backend wheels.

The backend dependencies are declared in `backend/pyproject.toml` and the
deterministic resume renderer (`backend/app/resume_docx_renderer.py`)
imports `docx`, which is provided by `python-docx`.

## Changes

1. Backend verification runs with the project backend interpreter.
   `scripts/agentctl.sh` resolves a backend Python via
   `resolve_backend_python` (override → `backend/.venv` → conda
   `job_env` → PATH fallback), prepends its `bin/` to `PATH` for
   verification commands, and logs `using python: <path>`.
2. Prefer `python -m pytest` over bare `pytest` in docs and new tasks.
3. Documentation shows:
   ```bash
   conda activate job_env
   python -m pip install -r backend/requirements.txt
   python -m pytest
   ```
4. `python-docx` is listed in `backend/requirements.txt` (and remains in
   `backend/pyproject.toml`).
5. Task/agent-runner docs (`agent_tasks/planning_guidelines.md`,
   `docs/install.md`) updated to avoid accidentally using `rmg_env`.
6. agentctl exposes env configuration (`JOBAPPLY_BACKEND_PYTHON`,
   `JOBAPPLY_BACKEND_CONDA_ENV`) and prints the resolved interpreter in
   both `run_verification_commands` and `doctor`.
7. A dependency preflight runs before backend verification:
   ```bash
   python - <<'PY'
   import fastapi, pydantic, docx
   print("backend dependencies ok")
   PY
   ```

## Verification

```bash
python -m pytest
cd frontend && npm run build
```

## Commit

```bash
git add backend scripts docs requirements.txt pyproject.toml agent_tasks
git commit -m "Use project Python environment for backend tests"
```
