# Browser Extension (Chrome and Firefox)

The current-page capture extension is built from a single codebase
under `extension/src/` and produces two loadable variants — one for
Chromium-based browsers and one for Firefox — under
`extension/dist/chrome/` and `extension/dist/firefox/`.

For the deeper behavioral contract (permissions, payload shape,
forbidden behaviors) see
[`docs/contracts/browser_extension_capture.md`](contracts/browser_extension_capture.md).

## Build

```bash
cd extension
npm install
npm run build
```

This produces:

```text
extension/dist/chrome/    Loadable in Chrome / Chromium / Edge / Brave.
extension/dist/firefox/   Loadable as a temporary add-on in Firefox.
```

Both variants share the same JavaScript source. Only the manifest
differs:

- `extension/manifest.json` — Chrome MV3 with a service worker.
- `extension/manifest.firefox.json` — Firefox MV2 with a
  `background.scripts` array, `browser_action` for the toolbar button,
  host patterns folded into `permissions`, and a
  `browser_specific_settings.gecko.id`. MV2 is the most reliable shape
  for Firefox temporary add-ons — Firefox's MV3 background story has
  historically rejected `service_worker` manifests, and the MV2 form
  loads cleanly across Firefox 109+.

The runtime code uses a small compatibility wrapper
(`extension/src/browser_api.js`) that resolves
`globalThis.browser ?? globalThis.chrome` and exposes
`injectContentScript(tabId, file)`, which feature-detects
`scripting.executeScript` (Chrome MV3) and falls back to
`tabs.executeScript` (Firefox MV2). The popup uses that single helper
so there are no per-browser code paths in the popup, content, or
options scripts.

## Chrome setup

1. Open `chrome://extensions`.
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and choose `extension/dist/chrome/`.
4. Pin the extension's action button for convenience.

## Firefox setup (temporary add-on)

Firefox can load an unsigned extension as a *temporary add-on*. This
is the right path for local development; signing/distribution is not
needed.

1. Open Firefox.
2. Go to `about:debugging`.
3. Click **This Firefox**.
4. Click **Load Temporary Add-on**.
5. Select `extension/dist/firefox/manifest.json`.
6. Open a LinkedIn job posting page.
7. Click the extension's action button.
8. Click **Capture this job page**.

Firefox removes temporary add-ons every time the browser restarts.
After a restart, repeat steps 2–5.

If you want a persistent install for personal use, you can package the
extension and sign it via Mozilla's
[Add-on Developer Hub](https://addons.mozilla.org/) or use the unbranded
`web-ext` tooling locally:

```bash
cd extension
npm run lint:firefox       # runs web-ext lint via npx --yes
```

## Backend URL configuration

The extension talks to the local backend at `http://localhost:8000` by
default. To override, open the extension's **Options** page
(`Capture this job page` popup → **Configure** link, or
`about:addons` → **Extension options** in Firefox / `chrome://extensions`
→ **Details** → **Extension options** in Chrome) and set:

```text
Backend API base URL: http://localhost:8000
```

The page exposes:

- **Save** — persists the value via the extension's
  `storage.local` API.
- **Reset to default** — restores `http://localhost:8000`.
- **Test connection** — probes `GET <base>/health` to confirm the
  backend is reachable.

The capture popup itself shows the configured backend URL and a
"Connected to backend" / "Could not reach backend at \<url\>" status
on open, so most users never need to touch the options page.

## Capture workflow

1. Start the backend (`uvicorn app.main:app --reload`).
2. Open the JobApplicator frontend at `http://localhost:5173`.
3. Open a LinkedIn job posting in the browser.
4. Click the extension's action button.
5. The popup shows the configured backend URL and whether it is
   reachable.
6. Click **Capture this job page**. The popup parses the page in place
   and surfaces the extracted fields.
7. Review the preview.
8. Click **Send to backend**.
9. On success, the popup shows "Captured. Open in JobApplicator." and
   offers a link to the job's workspace.
10. On failure, the popup shows "Capture failed: \<safe error\>".

## Privacy and safety

- The extension captures **only when the user clicks Capture this job
  page**. It is a no-op until then — no background polling, no page
  scraping on navigation, no autostart on Firefox / Chrome launch.
- The extension sends captured page data **only** to the configured
  local JobApplicator backend. It does not contact any third-party
  service.
- The extension does **not** submit job applications.
- The extension does **not** click apply buttons.
- The extension does **not** read Gmail.
- Captured page text is held in popup memory only until the user
  clicks Send to backend, and is discarded when the popup closes.

## Troubleshooting

### "Could not reach backend at http://localhost:8000"

The popup's health check failed. Common causes:

- The backend is not running. Start it with
  `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
- The backend is running on a different port. Open the extension's
  **Options** page and update the Backend API base URL.
- A firewall blocks loopback connections.

### Capture failed: CORS / extension origin issue

Firefox extension origins look like `moz-extension://<uuid>` and
Chrome extension origins like `chrome-extension://<id>`. The backend
allows both via a narrow CORS regex
(`^(moz|chrome)-extension://...$` — see `backend/app/main.py`). If
you have customized CORS locally, make sure that regex still matches
your browser's origin.

### Firefox temporary add-on disappeared after restart

This is expected. Temporary add-ons are removed every time Firefox
restarts. Reload from `about:debugging → This Firefox → Load
Temporary Add-on`.

### Firefox says "background.service_worker is currently disabled. Add background.scripts."

The Firefox manifest is being read as MV3 service-worker syntax,
which Firefox's temporary add-on loader rejects. Make sure you are
loading the *built* Firefox variant, not the Chrome manifest at the
source root:

```text
extension/dist/firefox/manifest.json    ✅ Firefox MV2 with background.scripts
extension/manifest.json                  ❌ Chrome MV3, has background.service_worker
```

Rebuild if needed (`cd extension && npm run build`) and re-select
`extension/dist/firefox/manifest.json` from
`about:debugging → This Firefox → Load Temporary Add-on`. The Firefox
manifest uses `background.scripts`; if you ever see this error from a
Firefox-targeted manifest, it has reverted to MV3 service-worker
syntax and needs to go back to the MV2 form documented above.

### Page blocks content-script access

A small number of LinkedIn job pages render behind layouts that prevent
the parser from finding the description container. The popup will say
"Description missing". The page may need to be scrolled or "Show more"
expanded so LinkedIn fully hydrates the description; click Capture
again.

### Wrong backend URL stored

Open the extension's **Options** page and click **Reset to default**.
This restores `http://localhost:8000`.

## Chrome vs Firefox notes

| Concern | Chrome | Firefox |
| --- | --- | --- |
| Manifest version | MV3 | MV2 |
| Background form | `service_worker` (`type: module`) | `background.scripts` (`persistent: false`) |
| Action key | `action` | `browser_action` |
| Host patterns | `host_permissions` | merged into `permissions` |
| Script injection | `chrome.scripting.executeScript` | `browser.tabs.executeScript` |
| Add-on ID | implicit | `browser_specific_settings.gecko.id` required |
| Install | `chrome://extensions` → Load unpacked | `about:debugging` → Load Temporary Add-on |
| Survives restart | Yes | No (temporary add-on) |
| Storage API | `chrome.storage.local` | `browser.storage.local` |

The shared source uses the `browser_api.js` wrapper —
`browserApi` resolves to whichever global the host browser exposes,
and `injectContentScript()` smooths over the MV3/MV2 script-injection
difference — so neither popup, content, options, nor background code
branches on the host browser.

## Out of scope

- Submitting job applications.
- Auto-clicking Easy Apply or external Apply buttons.
- Background polling or batch scraping of search results.
- Profile / contact harvesting.
- Capture providers other than the current-page LinkedIn parser.
