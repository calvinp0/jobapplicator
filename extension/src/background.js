// Background service worker.
//
// MV3 service workers are event-driven and short-lived. This worker does
// no autonomous work: it only logs install/activation and acts as the
// extension's lifecycle anchor. The actual capture flow is driven by the
// popup (popup.js), which the user opens by clicking the action button.

chrome.runtime.onInstalled.addListener(() => {
  console.log("[jobapply] extension installed");
});
