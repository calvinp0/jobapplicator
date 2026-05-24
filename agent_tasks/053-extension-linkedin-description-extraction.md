# Task 053: Improve LinkedIn Job Description Extraction

## Goal

Improve the browser extension so it reliably captures the job description from LinkedIn job pages.

Current observed behavior:

```text
TITLE captured
COMPANY captured
LOCATION captured
URL captured
DESCRIPTION missing
```

The extension popup shows the job metadata, but the description is empty even though the LinkedIn page visibly contains a job description.

The extension should extract the visible LinkedIn job description using stable selectors and fallback logic.

Do not implement LinkedIn Easy Apply automation.
Do not implement Gmail.
Do not change backend behavior unless absolutely necessary.

## Background

Inspect:

```text
extension/**
backend/app/routers/captures.py
backend/app/schemas.py
frontend/src/pages/CapturesPage.tsx
frontend/src/pages/CaptureDetailPage.tsx
docs/product_requirements.md
```

Observed page structure from a LinkedIn job page:

```css
#job-details
#job-details > div > p
```

An absolute XPath was observed:

```text
/html/body/div[6]/div[3]/div[4]/div/div/main/div/div[2]/div[2]/div/div[2]/div/div[2]/div[1]/div/div[4]/article/div/div[1]/div/p
```

Do not use the absolute XPath as the primary strategy. It is too brittle.

Prefer stable selectors such as:

```css
#job-details
.jobs-description__content
.jobs-box__html-content
.jobs-description-content__text
[data-test-job-description]
```

## Scope

Update:

```text
extension/**
```

Optionally update extension tests if present.

Do not edit backend unless an existing capture payload field is clearly incompatible.

Do not edit frontend unless needed to display the already-captured description.

## Required Behavior

### 1. Add robust LinkedIn description extraction

The extension should attempt a ranked list of selectors.

Preferred behavior:

```js
const selectors = [
  "#job-details",
  ".jobs-description__content",
  ".jobs-box__html-content",
  ".jobs-description-content__text",
  "[data-test-job-description]"
];
```

For each selector:

```text
- query the element
- read visible text using innerText
- trim whitespace
- normalize repeated whitespace
- accept the first result that looks like a real job description
```

A result should generally be considered valid if:

```text
- it is non-empty
- it is longer than a small threshold, e.g. 100 characters
```

Do not require an exact heading like `About the job`, because LinkedIn varies by locale/layout.

### 2. Avoid brittle absolute XPath

Do not use the observed absolute XPath as the primary extraction method.

If an XPath fallback is added at all, it must be a last resort and should target semantic anchors rather than absolute wrapper indexes.

### 3. Preserve existing metadata capture

Do not regress capture of:

```text
title
company
location
url
apply_url
source
```

### 4. Improve popup feedback

The extension popup should make it clear whether description was captured.

Acceptable UI examples:

```text
DESCRIPTION captured — 4,218 chars
```

or:

```text
DESCRIPTION missing
```

If feasible, show a short preview:

```text
DESCRIPTION preview
Are you a software engineer passionate about...
```

Keep the popup compact.

### 5. Send captured description to backend

When the user clicks the send/capture button, the backend payload should include the captured description text.

If the description is missing, keep the existing missing-field behavior.

## Suggested Implementation Shape

Use helper functions similar to:

```js
function normalizeText(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function textFromSelector(selector) {
  const element = document.querySelector(selector);
  return normalizeText(element?.innerText || "");
}

function extractDescription() {
  const selectors = [
    "#job-details",
    ".jobs-description__content",
    ".jobs-box__html-content",
    ".jobs-description-content__text",
    "[data-test-job-description]",
  ];

  for (const selector of selectors) {
    const text = textFromSelector(selector);
    if (text.length > 100) {
      return text;
    }
  }

  return "";
}
```

Adjust to match the extension’s current code style.

## Manual Browser Verification

On a LinkedIn job page, open DevTools and verify:

```js
document.querySelector("#job-details")?.innerText
```

returns the visible job description.

Also test:

```js
[
  "#job-details",
  ".jobs-description__content",
  ".jobs-box__html-content",
  ".jobs-description-content__text",
  "[data-test-job-description]"
].map((selector) => [
  selector,
  document.querySelector(selector)?.innerText?.slice(0, 200)
]);
```

Then load the extension and confirm:

```text
DESCRIPTION captured
```

or a non-empty preview appears in the popup.

## Acceptance Criteria

- LinkedIn job description is captured from `#job-details` when present.
- Extension uses a ranked selector fallback list.
- Existing title/company/location/url capture still works.
- Popup clearly shows description captured/missing state.
- Capture payload sends non-empty description to backend for the tested LinkedIn job page.
- Absolute XPath is not used as the primary strategy.
- Extension tests pass if present.
- Extension build passes.

## Verification

Run:

```bash
cd extension && npm install
cd extension && npm test
cd extension && npm run build
```

If the extension has no test script, run:

```bash
cd extension && npm run build
```

Manual verification:

1. Start backend.
2. Load unpacked extension in Chrome.
3. Open a LinkedIn job page.
4. Click capture.
5. Confirm popup says description was captured.
6. Click send to backend.
7. Confirm frontend Captures page shows the captured description.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Improve LinkedIn job description extraction
```

Do not push.
