# Task 025: Add Backend Local CORS Support

## Goal

Add CORS support to the local FastAPI backend so the Vite frontend can call the backend during local development.

Current observed issue:

```text
Cross-Origin Request Blocked:
CORS header 'Access-Control-Allow-Origin' missing
```

The backend is running and responds to `/health`, `/docs`, and `/openapi.json`, but browser requests from:

```text
http://localhost:5173
```

to:

```text
http://localhost:8000
```

are blocked by the browser.

This task should fix local frontend/backend integration only. Do not change unrelated backend behavior.

## Background

Read:

```text
backend/app/main.py
frontend/src/api/index.ts
docs/architecture.md
docs/product_requirements.md
README.md
```

Also inspect backend startup/config files if present.

Observed facts:

```text
curl http://localhost:8000/docs        returns 200
curl http://localhost:8000/openapi.json returns 200
browser frontend calls to http://localhost:8000 fail due to missing CORS header
grep -R "CORS\|allow_origins\|CORSMiddleware" -n backend returned no results
```

## Scope

Update:

```text
backend/app/main.py
```

Optionally update:

```text
backend/tests/
README.md
docs/smoke_tests/
```

## Required Behavior

Add FastAPI CORS middleware using:

```python
from fastapi.middleware.cors import CORSMiddleware
```

Allow local frontend origins:

```text
http://localhost:5173
http://127.0.0.1:5173
```

The backend should return:

```text
Access-Control-Allow-Origin: http://localhost:5173
```

for browser requests from that origin.

## Configuration

Prefer a simple local-development default for now.

Acceptable implementation:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

If the existing backend already has a settings/config pattern, use it, but keep the change small.

Do not overbuild environment profiles unless the existing project already has that pattern.

## Tests

Add a backend test if straightforward.

Suggested test:

```text
Send GET /jobs with Origin: http://localhost:5173
Assert status 200
Assert access-control-allow-origin == http://localhost:5173
```

Also test that `/health` still works.

## Out of Scope

Do not implement auth.

Do not change frontend API code unless absolutely necessary.

Do not change database behavior.

Do not change seed data.

Do not implement production CORS policy.

Do not add unrelated settings systems.

Do not touch browser extension code.

## Manual Verification

After implementation, from repo root or backend launch context:

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Then in another terminal:

```bash
curl -i \
  -H "Origin: http://localhost:5173" \
  http://localhost:8000/jobs
```

Expected header:

```text
access-control-allow-origin: http://localhost:5173
```

Then run frontend:

```bash
cd frontend
VITE_API_BASE=http://localhost:8000 npm run dev
```

Open:

```text
http://localhost:5173
```

The frontend should no longer show:

```text
failed to load captures
failed to load jobs
```

because of CORS.

## Verification

Run:

```bash
pytest
```

If frontend is touched, also run:

```bash
cd frontend && npm test && npm run build
```

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Add backend local CORS support
```

Do not push.
