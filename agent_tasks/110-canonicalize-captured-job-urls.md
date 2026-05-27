# Task 110: Canonicalize Captured Job URLs

## Goal

Normalize messy captured job URLs into clean canonical URLs.

Captured LinkedIn URLs can look like:

```text
https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750&origin=...
```

The app should derive and display a clean canonical URL:

```text
https://www.linkedin.com/jobs/view/4415730750
```

Do not implement a link shortener.  
Do not call an LLM for URL cleanup.  
Do not change Gmail behavior.  
Do not change Claude tailoring behavior.  
Do not implement LinkedIn automation or application submission.

## Background

Browser extension captures currently preserve the full current browser URL.

This is useful for debugging but ugly for the user and unstable for job tracking.

The backend should store:

```text
raw/source URL
canonical URL
external job ID
source platform
```

Example:

```json
{
  "source_url": "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750&origin=...",
  "canonical_url": "https://www.linkedin.com/jobs/view/4415730750",
  "external_job_id": "4415730750",
  "source_platform": "linkedin"
}
```

## Inspect

Inspect:

```text
extension/
backend/app/routers/captures.py
backend/app/models.py
backend/app/schemas.py
backend/tests/test_captures.py
frontend/src/pages/
frontend/src/api/types.ts
docs/browser_extension.md
README_INSTALL.md
```

Search:

```bash
rg "source_url|url|currentJobId|canonical|external_job_id|linkedin|capture" extension backend frontend docs
```

Use existing project conventions.

## Required Behavior

Add deterministic URL normalization.

Create helper such as:

```text
backend/app/url_canonicalizer.py
```

or equivalent.

It should expose a function like:

```python
canonicalize_job_url(url: str) -> CanonicalJobUrl
```

Return fields:

```json
{
  "source_url": "...",
  "canonical_url": "...",
  "external_job_id": "...",
  "source_platform": "linkedin"
}
```

## LinkedIn Rules

Support at least:

### Rule 1: currentJobId query param

Input:

```text
https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750&origin=...
```

Output:

```text
https://www.linkedin.com/jobs/view/4415730750
```

Fields:

```text
external_job_id = 4415730750
source_platform = linkedin
```

### Rule 2: already canonical jobs view URL

Input:

```text
https://www.linkedin.com/jobs/view/4415730750/?trackingId=abc
```

Output:

```text
https://www.linkedin.com/jobs/view/4415730750
```

### Rule 3: LinkedIn job search URL with currentJobId

Input:

```text
https://www.linkedin.com/jobs/search/?currentJobId=4415730750&keywords=...
```

Output:

```text
https://www.linkedin.com/jobs/view/4415730750
```

### Rule 4: Unknown URL

Input:

```text
https://example.com/jobs/foo?utm_source=bar
```

Output:

```text
canonical_url = input URL with common tracking params removed if safe
external_job_id = null
source_platform = inferred domain or "unknown"
```

Do not break non-LinkedIn captures.

## Tracking Parameter Cleanup

For unknown/general URLs, remove common tracking params when safe:

```text
utm_source
utm_medium
utm_campaign
utm_term
utm_content
fbclid
gclid
mc_cid
mc_eid
```

Do not remove meaningful job query params unless platform-specific logic supports it.

## Backend Storage Requirements

If models currently only store one URL field, add fields where appropriate:

```text
source_url
canonical_url
external_job_id
source_platform
```

If adding migrations is too large, at least compute canonical URL in API response and store source URL unchanged.

Preferred:

```text
store both source_url and canonical_url
```

Existing records should remain backwards compatible.

## Capture Endpoint Requirements

When a browser capture is created:

```text
1. Accept raw URL from extension.
2. Canonicalize it.
3. Store raw source URL.
4. Store canonical URL.
5. Store external job ID/platform if available.
```

The Review Capture page should display:

```text
Canonical URL
```

with a smaller expandable/copyable:

```text
Original captured URL
```

## Frontend Requirements

Update Review Capture and job/application display.

Show:

```text
URL: https://www.linkedin.com/jobs/view/4415730750
```

not the messy collection/search URL.

If the user wants to inspect the original:

```text
Original captured URL
```

can be shown in small text or details element.

Use canonical URL for:

```text
Open source job
copy link
display in tables
```

Do not lose original URL.

## Extension Requirements

If Task 109 already extracts `external_job_id`, pass it to backend.

But backend must still canonicalize independently.

Do not rely only on extension-side parsing.

## Tests

Add/update backend tests:

1. LinkedIn `currentJobId` URL canonicalizes to `/jobs/view/<id>`.
2. LinkedIn `/jobs/view/<id>` URL strips tracking params.
3. LinkedIn `/jobs/search/?currentJobId=<id>` canonicalizes.
4. Unknown URL preserves meaningful path.
5. Unknown URL strips common tracking params.
6. Invalid/empty URL is handled safely.
7. Capture endpoint stores source URL.
8. Capture endpoint stores canonical URL.
9. Capture endpoint stores external job ID.
10. Existing capture tests still pass.

Add/update frontend tests if infrastructure exists:

1. Review Capture displays canonical URL.
2. Original captured URL is still available.
3. Open source job uses canonical URL.

## Documentation

Update:

```text
docs/browser_extension.md
README_INSTALL.md
docs/contracts/
```

Document:

```text
raw URL vs canonical URL
LinkedIn currentJobId normalization
why this is not a link shortener
```

## Acceptance Criteria

- Messy LinkedIn capture URLs are normalized to clean `/jobs/view/<id>` URLs.
- Raw/original URL is preserved.
- Canonical URL is displayed to the user.
- External LinkedIn job ID is stored or exposed.
- Non-LinkedIn captures still work.
- No LLM is used for URL normalization.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_captures.py
pytest
cd frontend && npm run build
```

Manual verification:

1. Capture a LinkedIn URL like:

```text
https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750&origin=...
```

2. Open Review Capture.
3. Confirm displayed URL is:

```text
https://www.linkedin.com/jobs/view/4415730750
```

4. Confirm original captured URL is still available somewhere.
5. Confirm confirming the capture creates/updates job using the canonical URL.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Canonicalize captured job URLs
```

Do not push.
