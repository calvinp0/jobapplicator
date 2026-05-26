// Cross-browser WebExtension API wrapper.
//
// Firefox exposes the standardized `browser` namespace (Promise-returning).
// Chrome exposes `chrome` (callback-based historically, Promise-based on
// MV3 for most APIs). The same source bundles for both; this wrapper just
// resolves whichever global the host browser provides at runtime.

export const browserApi = globalThis.browser ?? globalThis.chrome;

// `chrome.tabs.sendMessage` and `chrome.scripting.executeScript` return
// Promises in MV3 (Chrome 99+) and in Firefox via `browser.*`. We only
// rely on these APIs from popup contexts, where the Promise form is
// universally available.
