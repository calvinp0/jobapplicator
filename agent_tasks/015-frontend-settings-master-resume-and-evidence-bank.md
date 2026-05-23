# Task 015: Frontend settings page for master resumes and evidence banks

## Goal

Replace the placeholder `/settings` page with the minimum UI needed
to seed the cockpit: list and create master resumes, list and create
evidence banks. Without these, the existing job-detail "Generate
resume" form has no selectable options, so the cockpit is not
usable end-to-end.

## Background

Read:

- `docs/product_requirements.md` (resume tailoring, MMVP workflow)
- `docs/architecture.md` (Candidate Context section)
- `backend/app/routers/master_resumes.py` and
  `backend/app/routers/evidence_banks.py` (endpoint shape)
- `backend/app/schemas.py` (`MasterResumeCreate`,
  `EvidenceBankCreate`)
- `agent_tasks/009-frontend-shell.md` and
  `agent_tasks/010-frontend-job-capture-flow.md` (existing frontend
  conventions, API client style)
- `frontend/src/api/index.ts` (existing API client)

## Scope

Within `frontend/src/`:

- Add API client functions for creating master resumes and evidence
  banks (`createMasterResume`, `createEvidenceBank`) in
  `frontend/src/api/index.ts`. Match the existing `apiRequest` /
  `ApiError` patterns.
- Replace `frontend/src/pages/SettingsPage.tsx` with two stacked
  sections:
  - **Master resumes**: a list of existing master resumes (name,
    created_at, source_path if present), plus a small form to create
    a new one (name + `content_markdown` textarea + optional
    `source_path`).
  - **Evidence banks**: same shape for `EvidenceBank`.
- After a successful create, refresh the relevant list and clear the
  form. Surface server validation errors via `ApiError.message` or
  the response body, consistent with `CaptureDetailPage`.
- Add minimal styles to `frontend/src/styles.css` if needed (no new
  CSS dependency, no design system).
- Add a vitest test for the settings page that covers the happy path
  for creating a master resume and an evidence bank with a mocked
  API, and confirms the new entry shows up in the list after
  submission.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/**`
- `frontend/package.json` and `frontend/package-lock.json` (only if
  unavoidable — prefer no new dependencies)
- `agent_tasks/queue.yaml` (status updates only if explicitly
  instructed)

## Forbidden files

- `backend/**`
- `extension/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/**`
- Other `agent_tasks/*.md`
- Frontend files outside the allowed list (in particular,
  `frontend/src/App.tsx`, layout, and other pages — leave them alone)

## Out of scope

- Editing or deleting existing master resumes / evidence banks.
- Importing markdown files from disk via the browser (a later task
  could add a server-side import endpoint; not now).
- Any approval / review flow.
- Authentication or multi-user concerns.

## Acceptance criteria

- The user can open `/settings` and create a master resume and an
  evidence bank, then see them listed.
- Validation errors from the backend surface as a visible message in
  the relevant form.
- `npm test` and `npm run build` pass from `frontend/`.
- No backend, extension, or doc files are touched.

## Verification

Run from `frontend/`:

```bash
npm test
npm run build
```

## Git instructions

Commit message:

```text
Add settings page for master resumes and evidence banks
```

Do not push.
