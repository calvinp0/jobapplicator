# Install

Full setup lives in [`docs/install.md`](docs/install.md) — backend,
frontend, Claude Code, and the optional Office Word MCP. This file is
a short quick-reference for the pieces users most often re-install on
a new machine.

For the browser extension specifically, see
[`docs/browser_extension.md`](docs/browser_extension.md).

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:8000 npm run dev -- --host localhost --port 5173
```

## Browser extension

```bash
cd extension
npm install
npm run build
```

This writes two loadable variants:

```text
extension/dist/chrome/    Chrome / Chromium / Edge / Brave (MV3)
extension/dist/firefox/   Firefox temporary add-on (MV2)
```

### Chrome

1. Open `chrome://extensions`.
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and choose `extension/dist/chrome/`.

### Firefox (temporary add-on)

1. Open Firefox.
2. Go to `about:debugging`.
3. Click **This Firefox**.
4. Click **Load Temporary Add-on**.
5. Select `extension/dist/firefox/manifest.json`.

Temporary add-ons disappear when Firefox restarts. After every
restart, repeat steps 2–5.

### Troubleshooting

#### "background.service_worker is currently disabled. Add background.scripts."

Firefox is reading the Chrome MV3 manifest by mistake. The Firefox
variant uses MV2 with `background.scripts`. Re-select the built
Firefox manifest at `extension/dist/firefox/manifest.json` (not
`extension/manifest.json`, which is Chrome's). Rebuild first with
`cd extension && npm run build` if the `dist/` folder is missing.

#### Firefox capture only fills the URL

Reload the LinkedIn job page, wait for the right pane to render, and
capture again — the content script retries with a small backoff. If a
field is still missing, the Review Capture page in the cockpit
prefills the description from the page-text fallback, shows a warning,
and exposes a "Raw captured text preview" section. You can also
highlight text on the LinkedIn page before clicking Capture; the
selection is sent through and used as the description fallback.

See [`docs/browser_extension.md`](docs/browser_extension.md) for the
full troubleshooting list (backend health, CORS, content-script
access).

### Captured URL vs canonical URL

The backend canonicalizes captured URLs deterministically. A LinkedIn
collections URL like

```text
https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750&origin=…
```

is normalized to

```text
https://www.linkedin.com/jobs/view/4415730750
```

and the original (`source_url`) is kept alongside for debugging. This is
plain string surgery, not a link shortener — there is no external
service call and no LLM. See `docs/browser_extension.md` and
`docs/contracts/browser_extension_capture.md` for the rules.
