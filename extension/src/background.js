// Background script.
//
// MV3 service workers (Chrome) and MV3 event pages (Firefox) are
// event-driven and short-lived. This worker does no autonomous work:
// it only logs install/activation and acts as the extension's lifecycle
// anchor. The actual capture flow is driven by the popup (popup.js),
// which the user opens by clicking the action button.

import { browserApi } from "./browser_api.js";

browserApi.runtime.onInstalled.addListener(() => {
  console.log("[jobapply] extension installed");
});
