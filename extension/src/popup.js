// Popup UI for current-page capture.
//
// The extension does no work until the user opens this popup AND clicks
// "Capture this job page". This file is the only place we trigger DOM
// scraping (via the content script) and the only place we contact the
// local backend.

import { browserApi, injectContentScript } from "./browser_api.js";
import {
  captureEndpoint,
  checkBackendHealth,
  DEFAULT_FRONTEND_BASE,
  jobWorkspaceUrl,
  postCapture,
} from "./api.js";
import { getBackendBaseUrl } from "./storage.js";
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
  hideJobLink();
}

function hideJobLink() {
  const el = $("job-link");
  if (!el) return;
  el.hidden = true;
  el.removeAttribute("href");
}

function showJobLink(jobId) {
  const el = $("job-link");
  if (!el) return;
  el.hidden = false;
  el.href = jobWorkspaceUrl(jobId);
  el.textContent = "Open job workspace";
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
  const [tab] = await browserApi.tabs.query({
    active: true,
    currentWindow: true,
  });
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
    await injectContentScript(tab.id, "content.js");
  } catch (err) {
    setStatus(`Could not inject content script: ${err.message}`, "err");
    return;
  }

  let response;
  try {
    response = await browserApi.tabs.sendMessage(tab.id, {
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
  const endpoint = await captureEndpoint();
  setStatus(`Sending to ${endpoint}…`, "ok");
  try {
    const { status, body } = await postCapture(lastPayload, endpoint);
    if (status >= 200 && status < 300) {
      renderSendResult(body);
    } else {
      const safeError = typeof body?.detail === "string" ? body.detail : `HTTP ${status}`;
      setStatus(`Capture failed: ${safeError}`, "err");
      $("send-btn").disabled = false;
    }
  } catch (err) {
    setStatus(`Capture failed: ${err.message}`, "err");
    $("send-btn").disabled = false;
  }
}

function renderSendResult(body) {
  const jobId = body?.job_id ?? null;
  const autoConfirmed = body?.auto_confirmed === true;
  if (autoConfirmed && jobId) {
    const reused = body?.job_reused === true;
    setStatus(
      reused
        ? "Captured. Job already exists in JobApplicator."
        : "Captured. Open in JobApplicator.",
      "ok",
    );
    showJobLink(jobId);
  } else {
    setStatus("Captured. Review in Captures.", "ok");
  }
}

async function refreshBackendStatus() {
  const base = await getBackendBaseUrl();
  $("backend-url").textContent = base;
  $("frontend-link").href = DEFAULT_FRONTEND_BASE;
  const healthEl = $("backend-health");
  healthEl.textContent = "checking…";
  healthEl.className = "health";
  const result = await checkBackendHealth(base);
  if (result.ok) {
    healthEl.textContent = "Connected to backend";
    healthEl.className = "health ok";
  } else {
    healthEl.textContent = `Could not reach backend at ${result.base}`;
    healthEl.className = "health err";
  }
}

function openOptionsPage(event) {
  event.preventDefault();
  if (typeof browserApi.runtime.openOptionsPage === "function") {
    browserApi.runtime.openOptionsPage();
  } else {
    // Older browsers: open the options page in a new tab as a fallback.
    const url = browserApi.runtime.getURL("options.html");
    browserApi.tabs.create({ url });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("capture-btn").addEventListener("click", runCapture);
  $("send-btn").addEventListener("click", sendToBackend);
  $("options-link").addEventListener("click", openOptionsPage);
  refreshBackendStatus();
});
