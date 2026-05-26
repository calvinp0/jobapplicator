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

function safeParse() {
  const url = window.location.href;
  if (!isLinkedInJobUrl(url)) {
    return { ok: false, error: "Not a LinkedIn job page" };
  }
  try {
    const payload = parseLinkedInJob({ document, url });
    return { ok: true, payload };
  } catch (err) {
    return { ok: false, error: err && err.message ? err.message : String(err) };
  }
}

browserApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "CAPTURE_CURRENT_PAGE") {
    sendResponse(safeParse());
    return true;
  }
  return false;
});
