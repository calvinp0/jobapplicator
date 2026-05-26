// Cross-browser WebExtension API wrapper.
//
// Firefox exposes the standardized `browser` namespace (Promise-returning).
// Chrome exposes `chrome` (callback-based historically, Promise-based on
// MV3 for most APIs). The same source bundles for both; this wrapper just
// resolves whichever global the host browser provides at runtime.

export const browserApi = globalThis.browser ?? globalThis.chrome;

// Inject a content script into the active tab.
//
// Chrome (MV3) exposes `scripting.executeScript({ target, files })`.
// Firefox is shipped as an MV2 temporary add-on (see
// `extension/manifest.firefox.json`) and only exposes the older
// `tabs.executeScript(tabId, { file })`. Feature-detect the MV3 API and
// fall back to the MV2 form, so popup.js can call a single helper without
// branching on host browser.
export async function injectContentScript(tabId, file) {
  if (
    browserApi.scripting &&
    typeof browserApi.scripting.executeScript === "function"
  ) {
    return browserApi.scripting.executeScript({
      target: { tabId },
      files: [file],
    });
  }
  return browserApi.tabs.executeScript(tabId, { file });
}
