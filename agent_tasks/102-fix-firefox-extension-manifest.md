# Task 102: Fix Firefox Extension Manifest Compatibility

## Goal

Fix the Firefox extension so it can be installed as a temporary add-on in Firefox.

Current Firefox error:

```text
background.service_worker is currently disabled. Add background.scripts.
```

This means the Firefox manifest is using Chrome Manifest V3 service worker syntax, but Firefox temporary add-on installation expects a Firefox-compatible background script configuration.

Do not remove Chrome support.  
Do not change backend capture behavior unless required.  
Do not implement LinkedIn automation.  
Do not change Gmail behavior.  
Do not change Claude tailoring behavior.

## Background

The user attempted to load the Firefox extension through:

```text
about:debugging → This Firefox → Load Temporary Add-on
```

Firefox rejected the extension with:

```text
background.service_worker is currently disabled. Add background.scripts.
```

The Firefox extension should be installable as a local temporary add-on without requiring hidden Firefox experimental settings.

## Inspect

Inspect:

```text
extensions/firefox/manifest.json
extensions/firefox/
extensions/shared/
extensions/chrome/
docs/browser_extension.md
README_INSTALL.md
```

Search:

```bash
rg "service_worker|background.scripts|manifest_version|host_permissions|browser_specific_settings" extensions docs README_INSTALL.md
```

## Required Behavior

The Firefox extension must use a Firefox-compatible manifest.

Preferred approach:

```text
Firefox extension uses Manifest V2 with background.scripts.
Chrome extension may keep Manifest V3 with background.service_worker.
Shared code should remain shared where possible.
```

Firefox manifest should use:

```json
{
  "manifest_version": 2,
  "background": {
    "scripts": ["background.js"],
    "persistent": false
  }
}
```

Do not use this in the Firefox manifest:

```json
{
  "background": {
    "service_worker": "background.js"
  }
}
```

## Permissions

If the Firefox manifest currently uses MV3 `host_permissions`, move localhost permissions into `permissions`.

Example Firefox MV2 style:

```json
{
  "permissions": [
    "activeTab",
    "storage",
    "http://localhost:8000/*",
    "http://127.0.0.1:8000/*"
  ]
}
```

Remove or avoid MV3-only keys from the Firefox manifest if Firefox rejects them.

## Firefox Browser Settings

Add Firefox extension settings if appropriate:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "jobapplicator@example.local",
    "strict_min_version": "109.0"
  }
}
```

Use a local/dev ID. Do not imply this is a signed production extension.

## API Compatibility

Ensure Firefox code uses WebExtension-compatible APIs.

If code uses `chrome.*`, add/use a wrapper:

```js
const browserApi = globalThis.browser ?? globalThis.chrome;
```

Handle callback-vs-Promise differences if needed.

## Documentation

Update:

```text
docs/browser_extension.md
README_INSTALL.md
```

Document Firefox temporary install:

```text
1. Open Firefox.
2. Go to about:debugging.
3. Click This Firefox.
4. Click Load Temporary Add-on.
5. Select extensions/firefox/manifest.json.
```

Add troubleshooting:

```text
If Firefox says background.service_worker is disabled, the Firefox manifest is using MV3 service_worker syntax. Use the Firefox MV2 manifest with background.scripts.
```

Document that temporary add-ons disappear when Firefox restarts.

## Tests / Validation

If `web-ext` is available, run:

```bash
cd extensions/firefox
npx web-ext lint
```

If `web-ext` is not installed, at least validate JSON:

```bash
python -m json.tool extensions/firefox/manifest.json
```

Run app verification:

```bash
pytest
cd frontend && npm run build
```

## Acceptance Criteria

- Firefox temporary add-on installs without `background.service_worker` error.
- Firefox manifest uses `background.scripts`.
- Firefox manifest does not rely on MV3 service worker support.
- Chrome support is not broken.
- Docs include troubleshooting for this exact error.
- Validation/build passes.

## Verification

Run:

```bash
python -m json.tool extensions/firefox/manifest.json
pytest
cd frontend && npm run build
```

Manual verification:

1. Open Firefox.
2. Go to:

```text
about:debugging
```

3. Click:

```text
This Firefox
```

4. Click:

```text
Load Temporary Add-on
```

5. Select:

```text
extensions/firefox/manifest.json
```

6. Confirm it loads without:

```text
background.service_worker is currently disabled
```

7. Open a job page.
8. Click the extension.
9. Capture the page.
10. Confirm the capture appears in JobApplicator.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix Firefox extension manifest
```

Do not push.
