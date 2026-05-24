// Popup UI for current-page capture.
//
// The extension does no work until the user opens this popup AND clicks
// "Capture current page". This file is the only place we trigger DOM
// scraping (via the content script) and the only place we contact the
// local backend.

import { postCapture, DEFAULT_CAPTURE_ENDPOINT } from "./api.js";
import { isLinkedInJobUrl } from "./parser.js";

let lastPayload = null;

function $(id) {
  return document.getElementById(id);
}

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${kind}`;
  el.hidden = false;
}

function formatChars(n) {
  return n.toLocaleString("en-US");
}

function showPreview(payload) {
  $("preview").hidden = false;
  $("f-title").textContent = payload.title ?? "(missing)";
  $("f-company").textContent = payload.company ?? "(missing)";
  $("f-location").textContent = payload.location ?? "(missing)";
  $("f-apply").textContent = payload.application_method ?? "(unknown)";
  $("f-url").textContent = payload.external_url ?? "";

  const desc = payload.description_text || "";
  const descLabel = $("f-desc-label");
  const descPreview = $("f-desc");
  if (desc.length > 0) {
    descLabel.textContent = `Description captured — ${formatChars(desc.length)} chars`;
    descLabel.className = "label ok";
    descPreview.hidden = false;
    descPreview.textContent =
      desc.length > 600 ? desc.slice(0, 600) + "…" : desc;
  } else {
    descLabel.textContent = "Description missing";
    descLabel.className = "label err";
    descPreview.hidden = true;
    descPreview.textContent = "";
  }
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab ?? null;
}

async function runCapture() {
  $("send-btn").disabled = true;
  $("preview").hidden = true;
  lastPayload = null;

  const tab = await getActiveTab();
  if (!tab || !tab.url) {
    setStatus("No active tab.", "err");
    return;
  }
  if (!isLinkedInJobUrl(tab.url)) {
    setStatus("This page is not a LinkedIn job posting.", "err");
    return;
  }

  // Inject the content script on demand (activeTab grant only applies after
  // the user-initiated action that opened this popup). This makes the
  // extension a true no-op until the user explicitly clicks Capture.
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (err) {
    setStatus(`Could not inject content script: ${err.message}`, "err");
    return;
  }

  let response;
  try {
    response = await chrome.tabs.sendMessage(tab.id, {
      type: "CAPTURE_CURRENT_PAGE",
    });
  } catch (err) {
    setStatus(`Content script did not respond: ${err.message}`, "err");
    return;
  }
  if (!response || !response.ok) {
    setStatus(`Capture failed: ${response?.error ?? "unknown error"}`, "err");
    return;
  }

  lastPayload = response.payload;
  showPreview(lastPayload);
  setStatus("Captured. Review fields, then send.", "ok");
  $("send-btn").disabled = false;
}

async function sendToBackend() {
  if (!lastPayload) return;
  $("send-btn").disabled = true;
  setStatus(`Sending to ${DEFAULT_CAPTURE_ENDPOINT}…`, "ok");
  try {
    const { status, body } = await postCapture(lastPayload);
    if (status >= 200 && status < 300) {
      setStatus(`Saved capture ${body?.id ?? ""}`.trim(), "ok");
    } else {
      setStatus(`Backend rejected capture (HTTP ${status}).`, "err");
      $("send-btn").disabled = false;
    }
  } catch (err) {
    setStatus(`Network error: ${err.message}`, "err");
    $("send-btn").disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("capture-btn").addEventListener("click", runCapture);
  $("send-btn").addEventListener("click", sendToBackend);
});
