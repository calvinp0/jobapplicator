# Task 026: Add Local MVP Smoke Proof

## Goal

Add a repeatable local MVP smoke proof so the app is verified as a whole system, not as isolated agent-task slices.

Recent failures showed that individual tasks can pass locally while the integrated app still fails:

- CORS task claimed success but the running backend did not expose CORS middleware.
- Seed data worked once but failed after DB deletion because `runs/demo-run-0001/input` still existed.
- Backend and seed script could use different SQLite database paths depending on launch directory.
- Frontend could load but fail API calls due to CORS or empty backend DB.
- Agent summaries were trusted without hard runtime proof.

This task should make the local MVP smoke flow deterministic and trustworthy.

Do not implement new product features.

## Background

Read:

```text
scripts/seed_demo_data.py
backend/app/main.py
backend/app/db.py
backend/app/run_directory.py
frontend/src/api/index.ts
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
README.md
```

## Scope

Update:

```text
scripts/seed_demo_data.py
scripts/smoke_local_mvp.sh
docs/smoke_tests/local_mvp.md
README.md
```

Optionally update:

```text
backend/tests/test_cors.py
backend/app/main.py
agent_tasks/planning_guidelines.md
```

## Required Fixes

### 1. Make seed data robust after DB/filesystem resets

`python scripts/seed_demo_data.py` currently fails if the database was deleted but the demo run directory still exists:

```text
FileExistsError: runs/demo-run-0001/input
```

Fix this safely.

Required behavior:

- The demo seed script may remove only the fixed demo run directory:

```text
runs/demo-run-0001
```

- It must not remove arbitrary run directories.
- It must be safe to rerun.
- It must handle these cases:

```text
DB exists + demo records exist + run dir exists
DB deleted + run dir exists
DB exists + partial demo records exist
DB exists + no run dir exists
```

Preferred behavior:

```text
If using fixed demo run_id "demo-run-0001", remove/recreate only that demo run directory before creating the demo run.
```

### 2. Use a deterministic local DB path for the smoke flow

The backend default DB path depends on the current working directory:

```text
sqlite:///./jobapply.db
```

This caused confusion because DB files appeared in both:

```text
jobapply.db
backend/jobapply.db
```

The smoke script must set:

```bash
JOBAPPLY_DATABASE_URL="sqlite:////home/calvin/code/jobapply/backend/jobapply.db"
```

or compute the absolute repo-root path dynamically and use:

```text
<repo>/backend/jobapply.db
```

The seed script should respect `JOBAPPLY_DATABASE_URL`.

Do not hardcode Calvin's home path in committed code. Compute from repo root.

### 3. Add CORS runtime proof

The smoke script must prove that the loaded backend app includes CORS.

It should check:

```bash
python - <<'PY'
from backend.app.main import app
assert any("CORSMiddleware" in str(m.cls) for m in app.user_middleware)
print("PASS CORS middleware loaded")
PY
```

It should also document this curl check:

```bash
curl -i -H "Origin: http://localhost:5173" http://localhost:8000/health
```

Expected header:

```text
access-control-allow-origin: http://localhost:5173
```

If feasible in the script, start the backend temporarily and assert this header automatically. If that is too much for this task, put it in the manual smoke checklist.

### 4. Add smoke script

Create:

```text
scripts/smoke_local_mvp.sh
```

It should run from repo root.

It should:

```bash
set -euo pipefail
```

Required checks:

```text
1. Print repo root.
2. Export deterministic JOBAPPLY_DATABASE_URL.
3. Run pytest.
4. Run frontend npm install/test/build.
5. Run extension npm install/test/build if extension/package.json exists.
6. Remove stale demo run directory only: runs/demo-run-0001.
7. Optionally remove the deterministic demo DB if the script is invoked with --reset.
8. Run python scripts/seed_demo_data.py.
9. Assert backend app imports.
10. Assert CORS middleware is loaded.
11. Optionally inspect the SQLite DB or use backend route functions to confirm seeded Example Aero Labs data exists.
```

Suggested CLI:

```bash
scripts/smoke_local_mvp.sh
scripts/smoke_local_mvp.sh --reset
```

`--reset` may remove:

```text
backend/jobapply.db
runs/demo-run-0001
```

It must not remove any other run directories.

### 5. Add smoke-test documentation

Create:

```text
docs/smoke_tests/local_mvp.md
```

Document:

```text
1. How to run the smoke script.
2. How to start backend.
3. How to start frontend.
4. How to seed demo data.
5. How to verify CORS.
6. How to click through the app-only MVP.
```

The click-through checklist should include:

```text
Jobs
Demo job
Runs
Run detail
Resume version detail
Applications
Application detail
Timeline/event display
```

## CORS Test

If `backend/tests/test_cors.py` does not already exist, add it.

Test:

```text
GET /jobs with Origin: http://localhost:5173
assert access-control-allow-origin == http://localhost:5173
```

Also test:

```text
GET /jobs with Origin: http://127.0.0.1:5173
assert access-control-allow-origin == http://127.0.0.1:5173
```

Optionally test preflight:

```text
OPTIONS /jobs with Origin and Access-Control-Request-Method
```

Do not overbuild production CORS config.

## Required Proof

This task is not complete unless these commands pass:

```bash
bash -n scripts/smoke_local_mvp.sh
scripts/smoke_local_mvp.sh --reset
pytest
cd frontend && npm test && npm run build
cd extension && npm test && npm run build
```

If extension dependencies are missing, run:

```bash
cd extension && npm install
```

before the extension verification.

Also verify:

```bash
python - <<'PY'
from backend.app.main import app
assert any("CORSMiddleware" in str(m.cls) for m in app.user_middleware)
print("PASS CORS middleware loaded")
PY
```

## Safety Rules

Do not delete arbitrary run directories.

Do not run broad cleanup commands.

Do not push.

Do not implement Gmail.

Do not implement LinkedIn automation.

Do not add new product features.

Do not change existing task statuses except this task's queue completion through the harness.

## Out of Scope

Do not build a production deployment system.

Do not add Docker unless already present and trivial.

Do not redesign the database layer.

Do not redesign the frontend.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add local MVP smoke proof
```

Do not push.
