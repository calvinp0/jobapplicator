# Task 109: Fix Firefox LinkedIn Capture Extraction

## Goal

Fix the Firefox extension capture flow so LinkedIn job captures include job title, company, location, application method, and description, not only the URL.

Current observed issue:

```text
Review Capture
Company: empty
Title: empty
Location: empty
URL: https://www.linkedin.com/jobs/collections/recommended/?currentJobId=...
Application method: empty
Description: empty
```

The Firefox extension is reaching the backend and creating a capture, but the content extraction is incomplete.

Do not implement automatic job application submission.  
Do not click apply buttons automatically.  
Do not scrape hidden/private data.  
Do not change Gmail behavior.  
Do not change Claude tailoring behavior.

## Background

Firefox extension support was added, and the extension can capture the current page URL.

However, on LinkedIn jobs pages, most useful fields are blank.

LinkedIn job pages often render job content dynamically and may use URLs like:

```text
https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750&...
```

The actual job title/company/description may be in the loaded DOM rather than in the URL.

The extension needs robust content-script extraction and diagnostics.

## Inspect

Inspect:

```text
extension/
extension/src/
extension/manifest.firefox.json
extension/manifest.json
extension/tests/
backend/app/routers/captures.py
backend/app/models.py
backend/tests/test_captures.py
frontend/src/pages/
frontend/src/api/
docs/browser_extension.md
README_INSTALL.md
```

Search:

```bash
rg "capture|linkedin|currentJobId|content script|executeScript|tabs.executeScript|scripting.executeScript|selected_text|page_text|description|company|title|location" extension backend frontend docs
```

Use the actual repo structure. The repo uses:

```text
extension/
```

not:

```text
extensions/
```

## Required Behavior

The Firefox extension capture should extract, when visible on the page:

```text
job title
company
location
application method if visible/detectable
job description text
current URL
selected text if present
page text fallback
captured_at
browser/source = firefox extension
```

If structured extraction fails, the extension should still send:

```text
page_title
selected_text
visible_page_text
url
diagnostics
```

so the backend/frontend can help the user recover.

## Content Script Requirements

Improve the LinkedIn extraction logic.

The content script should try multiple strategies:

### Strategy 1: LinkedIn-specific selectors

Try selectors for current LinkedIn job pages, such as likely title/company/location/description containers.

Do not rely on one selector only.

Use defensive selector lists like:

```js
const titleSelectors = [
  ".job-details-jobs-unified-top-card__job-title",
  ".jobs-unified-top-card__job-title",
  "h1"
];

const companySelectors = [
  ".job-details-jobs-unified-top-card__company-name",
  ".jobs-unified-top-card__company-name",
  "[data-test-job-details-company-name]"
];

const locationSelectors = [
  ".job-details-jobs-unified-top-card__primary-description-container",
  ".jobs-unified-top-card__bullet",
  "[data-test-job-location]"
];

const descriptionSelectors = [
  ".jobs-description__content",
  ".jobs-box__html-content",
  "#job-details",
  ".jobs-description-content__text"
];
```

Use the selectors that work in the actual codebase; do not break existing Chrome behavior.

### Strategy 2: OpenGraph/meta/title fallback

If DOM selectors fail, fallback to:

```text
document.title
meta[property="og:title"]
meta[name="description"]
```

### Strategy 3: Visible text fallback

If structured fields are still missing, capture a bounded visible text excerpt.

Example:

```text
document.body.innerText.slice(0, 20000)
```

Do not send unlimited page text.

### Strategy 4: currentJobId extraction

If URL includes:

```text
currentJobId=<id>
```

include:

```json
{
  "external_job_id": "4415730750",
  "source_url": "...",
  "source_platform": "linkedin"
}
```

Do not rely on currentJobId to fetch LinkedIn separately.

## Render Timing

LinkedIn content may load after the popup click.

The content script should wait briefly for content.

Implement a small retry/wait helper:

```text
try extraction immediately
wait 500ms
try again
wait 1000ms
try again
```

or use a bounded MutationObserver.

Do not hang indefinitely.

## Diagnostics Requirements

When fields are empty, include diagnostics in the capture payload.

Example:

```json
{
  "diagnostics": {
    "extractor": "linkedin",
    "browser": "firefox",
    "selectors_matched": {
      "title": false,
      "company": false,
      "location": false,
      "description": false
    },
    "document_title": "...",
    "body_text_length": 12345,
    "url_has_current_job_id": true
  }
}
```

Do not include sensitive cookies/tokens.

## Backend Requirements

Ensure the backend capture endpoint accepts and stores enough raw fallback data:

```text
page_title
selected_text
page_text
diagnostics
external_job_id
source_platform
```

If backend already supports these, do not duplicate.

The Review Capture page should use fallback values if structured fields are empty.

For example:

```text
Title field defaults to captured title or document title if job title is empty.
Description field defaults to selected_text or page_text excerpt if description is empty.
```

Do not force empty fields when fallback data exists.

## Frontend Review Capture Requirements

On the Review Capture page:

If title/company/description are empty but fallback text exists, show a warning:

```text
Structured LinkedIn fields were not detected. We filled what we could from page text.
Please review before confirming.
```

Provide a section:

```text
Raw captured text preview
```

or:

```text
Use captured page text as description
```

At minimum, the description textarea should not be empty if `page_text` or selected text exists.

## Extension Popup Requirements

After capture, show a useful result:

```text
Captured job page
Title detected: yes/no
Company detected: yes/no
Description detected: yes/no
```

If fields are missing:

```text
Some fields were not detected. Review and edit in JobApplicator.
```

## Firefox MV2 Compatibility

Ensure the Firefox path still works with:

```text
manifest.firefox.json
background.scripts
tabs.executeScript
```

Do not reintroduce:

```text
background.service_worker
```

in Firefox manifest.

## Tests

Add/update extension tests if infrastructure exists.

Tests should cover:

1. LinkedIn extractor finds title from LinkedIn selector.
2. Extractor finds company from LinkedIn selector.
3. Extractor finds description from LinkedIn selector.
4. Extractor falls back to document.title/meta when selectors fail.
5. Extractor captures bounded body text when structured fields fail.
6. Extractor includes currentJobId from URL.
7. Extractor includes diagnostics when fields are missing.
8. Firefox injection path still uses `tabs.executeScript`.
9. Chrome injection path still uses `scripting.executeScript` if available.

Add/update backend tests:

1. Capture endpoint accepts page_text fallback.
2. Capture endpoint accepts diagnostics.
3. Review capture response includes fallback page text.
4. Empty structured fields do not discard fallback description text.

Add/update frontend tests if infrastructure exists:

1. Review Capture page fills description from fallback page_text.
2. Review Capture page shows warning when structured extraction failed.
3. Raw captured text preview appears when available.

## Documentation

Update:

```text
docs/browser_extension.md
README_INSTALL.md
```

Add troubleshooting:

```text
If Firefox capture only fills URL:
- reload the LinkedIn job page
- wait for job details to render
- capture again
- use selected text fallback
- check extension diagnostics
```

Document that LinkedIn DOM changes may require selector updates.

## Acceptance Criteria

- Firefox LinkedIn capture fills title/company/location/description when visible.
- If structured extraction fails, page text fallback is captured.
- Review Capture page is not blank when fallback text exists.
- Diagnostics identify which selectors failed.
- Firefox manifest remains compatible.
- Chrome behavior is not broken.
- Tests/build pass.

## Verification

Run:

```bash
cd extension && npm test -- --run
pytest backend/tests/test_captures.py
pytest
cd frontend && npm run build
```

If extension has no tests:

```bash
cd extension && npm run build
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Load Firefox temporary add-on:

```text
about:debugging → This Firefox → Load Temporary Add-on → extension/manifest.firefox.json
```

4. Open a LinkedIn job page.
5. Wait for job details to render.
6. Click extension.
7. Capture current page.
8. Open JobApplicator Review Capture.
9. Confirm:
   - title is filled
   - company is filled when visible
   - location is filled when visible
   - description is filled or fallback page text appears
   - URL is filled
10. If a field is missing, confirm diagnostics/warning appears.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix Firefox LinkedIn capture extraction
```

Do not push.
