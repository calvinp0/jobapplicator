# Task 097: Add Firefox Extension Support

## Goal

Add Firefox extension support for JobApplicator because the user primarily uses Firefox, not Chrome.

The extension should support the same capture/application workflow as the Chrome extension or existing browser capture flow.

Do not remove Chrome support.  
Do not implement LinkedIn automation beyond existing safe capture behavior.  
Do not submit job applications automatically.  
Do not scrape behind authentication in ways that violate site terms.  
Do not change Gmail behavior.  
Do not change Claude tailoring behavior.

## Background

The project currently appears to have browser capture concepts in the UI:

```text
Advanced
Captures
```

The user wants Firefox support because Firefox is their usual browser.

The goal is to support capturing job posting data from Firefox and sending it to the local JobApplicator backend.

Expected local backend:

```text
http://localhost:8000
```

Expected frontend:

```text
http://localhost:5173
```

## Inspect

Inspect:

```text
extension/
browser_extension/
chrome_extension/
frontend/
backend/app/
backend/tests/
docs/
README_INSTALL.md
```

Search:

```bash
rg "extension|chrome|firefox|browser|capture|manifest|content_scripts|localhost|captures" .
```

Use the existing project structure. If there is already a Chrome extension, extend it. If not, create a browser extension folder with shared code where practical.

## Required Behavior

Create or update browser extension support so Firefox can:

```text
1. Run as a temporary/debug extension during local development.
2. Capture the current job page title, URL, selected text, and page text where allowed.
3. Send captured data to the local backend capture endpoint.
4. Show clear success/error feedback.
5. Allow configuring backend URL, defaulting to http://localhost:8000.
```

Do not submit forms automatically.

Do not click apply buttons automatically.

Do not store sensitive page content longer than needed.

## Extension Architecture

Prefer a browser-compatible structure:

```text
extensions/
  shared/
    capture.js
    api.js
  firefox/
    manifest.json
    background.js
    content.js
    popup.html
    popup.js
    options.html
    options.js
  chrome/
    ...
```

If the project already has a Chrome extension folder, preserve its structure and add Firefox support with minimal duplication.

Use WebExtension-compatible APIs where possible.

If Chrome uses `chrome.*`, add a small compatibility wrapper:

```js
const browserApi = globalThis.browser ?? globalThis.chrome;
```

Use Promise wrappers where needed.

## Firefox Manifest Requirements

Add a Firefox-compatible manifest.

Use Manifest V3 if existing code already supports it and Firefox compatibility is acceptable.

If Manifest V2 is simpler/required for the existing extension, document the choice.

Manifest should include only necessary permissions, such as:

```json
{
  "permissions": [
    "activeTab",
    "storage"
  ],
  "host_permissions": [
    "http://localhost:8000/*",
    "http://127.0.0.1:8000/*"
  ]
}
```

If content scripts need page access, define them carefully.

Do not request broad host permissions like `<all_urls>` unless necessary. If `<all_urls>` is necessary for job page capture, document why.

## Backend Capture Endpoint

Inspect existing capture endpoints.

If missing, add or document an endpoint like:

```text
POST /api/captures/browser
```

Payload:

```json
{
  "source": "firefox_extension",
  "url": "https://example.com/job/123",
  "title": "Graduate Software Engineer",
  "selected_text": "...",
  "page_text": "...",
  "captured_at": "...",
  "browser": "firefox"
}
```

Response:

```json
{
  "capture_id": "...",
  "status": "created",
  "message": "Captured job page"
}
```

If an existing endpoint already exists, use it.

## Popup UI Requirements

Firefox popup should include:

```text
Capture this job page
Backend URL
Status message
Open JobApplicator
```

The popup should show:

```text
Connected to backend
```

or:

```text
Could not reach backend at http://localhost:8000
```

When capture succeeds:

```text
Captured. Open in JobApplicator.
```

When capture fails:

```text
Capture failed: <safe error>
```

## Options UI Requirements

Add an options page or simple storage setting for:

```text
Backend API base URL
```

Default:

```text
http://localhost:8000
```

Persist using extension storage.

## Local Development Instructions

Document Firefox temporary extension install:

```text
1. Open Firefox.
2. Go to about:debugging.
3. Click This Firefox.
4. Click Load Temporary Add-on.
5. Select extensions/firefox/manifest.json.
6. Open a job posting page.
7. Click the extension.
8. Click Capture this job page.
```

Document that temporary extensions are removed when Firefox restarts.

If packaging is added, document:

```bash
web-ext lint
web-ext build
```

or the chosen packaging tool.

## CORS Requirements

Ensure backend allows requests from Firefox extension origins if needed.

Firefox extension origins may look like:

```text
moz-extension://...
```

If CORS middleware needs adjustment, add only what is needed.

Do not open CORS unnecessarily to all origins unless this is already local-development-only and documented.

## Tests

Add backend tests if capture endpoint changes:

1. Firefox extension capture payload creates a capture.
2. Capture includes source `firefox_extension`.
3. URL/title/page text are stored.
4. Missing URL returns validation error.
5. Backend does not require Chrome-specific fields.

Add frontend/extension tests if infrastructure exists.

At minimum, add a lightweight validation script or documentation for:

```bash
web-ext lint
```

if `web-ext` is used.

## Documentation

Update:

```text
README_INSTALL.md
docs/install.md
docs/browser_extension.md
```

Add sections:

```text
Firefox extension setup
Firefox temporary install
Backend URL configuration
Capture workflow
Troubleshooting
Chrome vs Firefox notes
```

Troubleshooting should include:

```text
Backend not running
Wrong backend URL
CORS/extension origin issue
Temporary add-on disappeared after Firefox restart
Page blocks content script access
```

## Privacy and Safety Requirements

Document:

```text
The extension captures only when the user clicks Capture.
The extension sends captured page data only to the configured local JobApplicator backend.
The extension does not submit applications.
The extension does not click apply buttons.
The extension does not read Gmail.
The extension does not send data to third-party services directly.
```

## Acceptance Criteria

- Firefox extension can be loaded as a temporary add-on.
- User can configure backend URL.
- User can capture a job page from Firefox.
- Capture is sent to local backend.
- Success/error feedback appears in popup.
- Chrome support is not broken.
- Docs explain Firefox setup.
- Backend tests pass if backend changed.

## Verification

Run:

```bash
pytest
cd frontend && npm run build
```

If extension linting exists:

```bash
cd extensions/firefox
npx web-ext lint
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Open Firefox.
4. Go to:

```text
about:debugging
```

5. Load temporary add-on from:

```text
extensions/firefox/manifest.json
```

6. Open a job posting page.
7. Click the extension.
8. Confirm backend URL is:

```text
http://localhost:8000
```

9. Click Capture this job page.
10. Confirm popup says captured.
11. Open JobApplicator Captures page.
12. Confirm the captured job appears.
13. Confirm Chrome extension/build still works if present.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Firefox extension support
```

Do not push.
