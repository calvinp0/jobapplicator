---
task_id: "085-add-gmail-evidence-to-applications-ui"
verdict: "REQUEST_CHANGES"
reviewed_at: "2026-05-25T20:10:00Z"
reviewer: "claude-code"
---

# Review: 085-add-gmail-evidence-to-applications-ui

## Verdict

REQUEST_CHANGES

## Required fixes

- Fix the failing frontend test
  `src/test/gmailEvidence.test.tsx > GmailEvidence > shows Connect Gmail
  action when not connected`. The assertion
  `expect(screen.getByTestId("gmail-status-line")).toHaveTextContent(/not connected/i)`
  runs synchronously, but `describeStatusLine` only returns
  `"Gmail: Not connected"` after `getGmailStatus` resolves and `status`
  flips from `null` to `{ connected: false }`. On the first render the
  status line falls through to `"Gmail: Not checked"`, so the test
  fails. Either wrap the assertion in `waitFor`, or change
  `describeStatusLine` / status state so the "Not connected" copy is
  shown as soon as the unconnected response has been observed. The task
  acceptance criteria explicitly require `Frontend build/tests pass`,
  and the documented verification command
  `cd frontend && npm test -- --run` reports `1 failed | 188 passed`.

## Optional notes

- `searchApplicationGmail` always sends `extra_terms: []` even when the
  caller does not provide it. The backend schema accepts this, but
  passing the field unconditionally adds noise; consider only including
  it when the caller supplies it.
- The classify endpoint in the backend supports both `candidate` and
  `message_id` (the latter currently 400s). The frontend always sends
  the full candidate, which is correct, but the task mentions a future
  `classify_top_candidate` option — leaving a TODO or short comment in
  `classifyApplicationGmail` would make the contract drift easier to
  spot later. Not blocking.
- `frontend/src/lib/workflow.ts` grew shared `emailStatusLabel` and
  `classificationLabel` helpers; nothing else in this diff uses them
  outside `GmailEvidence.tsx`, so this is fine but worth keeping in
  mind to avoid premature abstraction if no second caller appears.

## Evidence checked

- Inspected commit `97951ff Add Gmail evidence to applications UI`
  (only commit on branch beyond `main`).
- Reviewed diff: 10 files / 1345 insertions (frontend component, API
  client/types, workflow helpers, styles, two test files, two pages,
  and `docs/contracts/gmail_integration.md`).
- Read `frontend/src/components/GmailEvidence.tsx`,
  `frontend/src/api/index.ts`, and matched payloads against
  `backend/app/routers/applications.py` (`GmailClassifyRequest`,
  `GmailSearchCandidate`, etc.).
- Ran `cd frontend && npm run build` → succeeded.
- Ran `cd frontend && npm test -- --run` → **1 failed, 188 passed**
  (`gmailEvidence.test.tsx` — "shows Connect Gmail action when not
  connected").
- Ran `mamba run -n job_env pytest -q` → 314 passed.
- `git status` → working tree clean.

## Scope / allowed-path check

All changed files lie within the task's `allowed_paths`:
`frontend/**`, `backend/app/**`, `backend/tests/**`,
`docs/contracts/gmail_integration.md`, `docs/install.md`,
`README_INSTALL.md`, the task file, and `agent_tasks/queue.yaml`. No
backend code, ADRs, or unrelated files were touched. The
implementation respected the read-only Gmail constraints — no send /
delete / archive / label actions were added, and only
snippets/metadata/evidence are displayed. The privacy note required
by the task is present in `GmailEvidence.tsx`.

## Verification status

The task branch has exactly one commit (`97951ff`) beyond `main` and
the worktree is clean. Of the two verification commands listed in
`queue.yaml`:

- `cd frontend && npm run build` → green.
- `pytest` → green (314 passed).

The task body additionally specifies `cd frontend && npm test -- --run`
"if frontend tests exist". Tests exist (and were added in this commit)
and they currently fail (1 of 189). Because the acceptance criteria
require frontend tests to pass and one of the author's own tests is
red, this is REQUEST_CHANGES rather than APPROVE_WITH_NOTES.
