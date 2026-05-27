// Content script shim.
//
// Runs in the page's isolated world after explicit user action (the user
// clicks the action button → popup → popup messages this script via
// browser.scripting.executeScript / browser.tabs.sendMessage).
//
// All parsing logic lives in parser.js, which is a pure module — this file
// is the only place we touch DOM globals or extension APIs.

import { browserApi } from "./browser_api.js";
import { parseLinkedInJob, isLinkedInJobUrl } from "./parser.js";

// LinkedIn renders job content asynchronously after the popup click — the
// description container can take a beat to hydrate. Retry the parse a couple
// of times with a small backoff so we don't fall back to page_text when the
// structured selectors were simply not ready yet. Capped so the popup never
// hangs.
const RETRY_DELAYS_MS = [0, 500, 1000];

function readSelectedText() {
  try {
    const sel = window.getSelection ? window.getSelection() : null;
    return sel ? String(sel.toString() || "") : "";
  } catch {
    return "";
  }
}

function hasStructuredFields(payload) {
  const matched = payload.diagnostics?.selectors_matched ?? {};
  // We consider the parse "good enough to stop retrying" once at least the
  // title or the description container resolved. Company/location often lag.
  return Boolean(matched.title) || Boolean(matched.description);
}

function sleep(ms) {
  if (!ms) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function safeParseWithRetry() {
  const url = window.location.href;
  if (!isLinkedInJobUrl(url)) {
    return { ok: false, error: "Not a LinkedIn job page" };
  }
  let lastPayload = null;
  let lastError = null;
  for (const delay of RETRY_DELAYS_MS) {
    if (delay) await sleep(delay);
    try {
      const selectedText = readSelectedText();
      const payload = parseLinkedInJob({ document, url, selectedText });
      lastPayload = payload;
      if (hasStructuredFields(payload)) {
        return { ok: true, payload };
      }
    } catch (err) {
      lastError = err && err.message ? err.message : String(err);
    }
  }
  if (lastPayload) {
    // Structured selectors never matched, but we still have URL + page_text
    // + diagnostics for the backend/Review Capture page to recover from.
    return { ok: true, payload: lastPayload };
  }
  return { ok: false, error: lastError || "Failed to parse page" };
}

browserApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "CAPTURE_CURRENT_PAGE") {
    safeParseWithRetry().then(sendResponse);
    return true;
  }
  return false;
});
