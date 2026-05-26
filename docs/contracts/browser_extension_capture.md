# Contract: Browser Extension Current-Page Capture

This document is the contract for the browser extension capture provider
that lives under `extension/`. It is one of several capture providers
described in `docs/architecture.md` and ADR-007. It exists to give the user
a smoother LinkedIn intake than manual copy/paste while preserving the
human-in-the-loop posture required by ADR-005.

## Browser variants

The same source bundles to two Manifest V3 variants:

- `extension/manifest.json` — Chrome / Chromium / Edge / Brave.
  Background runs as a `service_worker` (`type: module`).
- `extension/manifest.firefox.json` — Firefox.
  Background runs as a `background.scripts` array (Firefox's preferred
  MV3 background form) and declares a
  `browser_specific_settings.gecko.id`. The build produces a loadable
  `dist/firefox/` folder; users load it as a *temporary add-on* via
  `about:debugging`.

Runtime code resolves WebExtension APIs through a small wrapper
(`extension/src/browser_api.js`) that uses
`globalThis.browser ?? globalThis.chrome` — no per-browser code paths
in the popup / content / background / options scripts.

## Permissions

Both manifests request the same minimum permissions:

| Permission | Why it is needed |
| --- | --- |
| `activeTab` | Allows the extension to access the *currently focused tab only*, and only after the user explicitly clicks the action button. |
| `scripting` | Allows the popup to inject the content script on demand after the user clicks Capture. |
| `storage` | Persists the user-configurable Backend API base URL via `storage.local`. No page content is ever stored here. |

Host permissions are scoped to:

- `https://www.linkedin.com/jobs/*` — the only origin/path the parser
  supports.
- `http://127.0.0.1:8000/*` and `http://localhost:8000/*` — the local
  backend endpoint the popup posts to. Both forms are listed because
  some browsers normalize one form to the other when matching host
  permissions.

The extension does **not** request `<all_urls>`, `tabs`, `webNavigation`,
`history`, or `cookies`. The user can override the backend host via the
options page; the manifest's host permissions still constrain which
origins the popup is *allowed* to talk to.

## Allowed behaviors

- Extract structured fields from the *currently loaded* LinkedIn job page
  after an explicit user click on the action button.
- Show the extracted preview in the popup so the user can review before
  sending.
- POST the normalized payload to `POST http://127.0.0.1:8000/captures`
  when the user clicks "Send to backend".
- Refuse to parse pages whose URL is not a LinkedIn job page.

## Forbidden behaviors

In line with `docs/product_requirements.md`, `docs/architecture.md`, and
ADR-005:

- No autonomous browsing.
- No background crawling, polling, or scheduled scraping.
- No batch scraping of job search results.
- No profile or contact harvesting.
- No auto-clicking Easy Apply.
- No auto-attaching files, auto-filling forms, or auto-submitting
  applications.
- No recruiter messaging automation.
- No telemetry beyond the explicit POST to the local backend the user
  triggered.

The background service worker does not run on a timer, does not listen for
navigation events, and does not inject content scripts on page load. The
content script is injected on demand by the popup *after* the user clicks
Capture; until that click, the extension is a no-op.

## Payload shape

The payload posted to the backend mirrors `JobCaptureCreate` in
`backend/app/schemas.py`:

```json
{
  "source_platform": "linkedin",
  "capture_method": "browser_extension_current_page",
  "external_url": "https://www.linkedin.com/jobs/view/4012345678/",
  "external_job_id": "4012345678",
  "company": "Example Corp",
  "title": "Senior Machine Learning Engineer",
  "location": "Berlin, Germany",
  "description_text": "About the role: ...",
  "application_method": "easy_apply",
  "raw_text": "...visible text of the job container...",
  "captured_at": "2026-05-22T12:00:00.000Z"
}
```

Field rules:

- `source_platform` is always `"linkedin"` for this provider.
- `capture_method` is always `"browser_extension_current_page"`.
- `external_url` is the page URL at capture time.
- `external_job_id` is parsed from `/jobs/view/<id>` or the `currentJobId`
  query parameter; `null` if neither is present.
- `company`, `title`, `location` may be `null` if the page does not expose
  them. The backend's `POST /captures/{id}/confirm` step is what enforces
  required-field validation.
- `description_text` is the visible text of the job description container;
  may be the empty string if not found.
- `application_method` is `"easy_apply"` if a visible Easy Apply button is
  detected, `"external"` if a visible "Apply" / "Apply on company site"
  button is detected, otherwise `null`.
- `raw_text` is the visible text of the job container (top card +
  description), scoped to avoid LinkedIn-wide navigation chrome.
- `captured_at` is set by the popup (the sender), not by the parser.

The backend treats this payload as untrusted input (ADR-005). The user
must still confirm the capture via `POST /captures/{id}/confirm` before it
becomes a `Job`.

## Loading the extension locally

```bash
cd extension
npm install
npm run build
```

This writes two loadable variants:

- `extension/dist/chrome/` — for Chrome / Chromium / Edge / Brave.
- `extension/dist/firefox/` — for Firefox (temporary add-on).

In Chrome / Chromium / Edge:

1. Open `chrome://extensions`.
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and choose `extension/dist/chrome/`.
4. Pin the extension's action button for convenience.

In Firefox:

1. Open `about:debugging`.
2. Click **This Firefox**.
3. Click **Load Temporary Add-on**.
4. Select `extension/dist/firefox/manifest.json`.

Temporary add-ons are removed when Firefox restarts; reload from
`about:debugging` after each restart.

To use, in either browser:

1. Open a LinkedIn job posting (`https://www.linkedin.com/jobs/view/...`).
2. Click the action button.
3. The popup shows the configured backend URL and whether the backend
   is reachable. Click **Configure** to change the backend URL.
4. Click **Capture this job page** in the popup and review the preview.
5. Make sure the local backend is running (`uvicorn` at
   `http://127.0.0.1:8000`), then click **Send to backend**.

## Out of scope

- Confirming captures into Jobs (that happens server-side via
  `POST /captures/{id}/confirm`).
- Reviewing captures in a UI (that is the frontend's job — task 010).
- Capture providers other than LinkedIn current-page (manual paste,
  clipboard, selected-text).
