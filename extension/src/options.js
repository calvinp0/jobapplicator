// Options page logic. Persists the backend base URL in extension
// storage and offers a one-click "Test connection" probe against the
// backend's /health endpoint.

import { checkBackendHealth } from "./api.js";
import {
  DEFAULT_BACKEND_BASE_URL,
  getBackendBaseUrl,
  normalizeBaseUrl,
  setBackendBaseUrl,
} from "./storage.js";

function $(id) {
  return document.getElementById(id);
}

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text;
  el.className = `status ${kind}`;
  el.hidden = false;
}

async function loadCurrent() {
  const current = await getBackendBaseUrl();
  $("backend-url").value = current;
}

async function save() {
  const raw = $("backend-url").value;
  if (!raw || !raw.trim()) {
    setStatus("Backend URL is required.", "err");
    return;
  }
  const normalized = normalizeBaseUrl(raw);
  try {
    new URL(normalized);
  } catch {
    setStatus(`Not a valid URL: ${normalized}`, "err");
    return;
  }
  await setBackendBaseUrl(normalized);
  $("backend-url").value = normalized;
  setStatus(`Saved. Backend URL: ${normalized}`, "ok");
}

async function resetToDefault() {
  await setBackendBaseUrl(DEFAULT_BACKEND_BASE_URL);
  $("backend-url").value = DEFAULT_BACKEND_BASE_URL;
  setStatus(`Reset to default: ${DEFAULT_BACKEND_BASE_URL}`, "ok");
}

async function testConnection() {
  const value = $("backend-url").value || DEFAULT_BACKEND_BASE_URL;
  const normalized = normalizeBaseUrl(value);
  setStatus(`Testing ${normalized}/health…`, "ok");
  const result = await checkBackendHealth(normalized);
  if (result.ok) {
    setStatus(`Connected to backend at ${result.base}`, "ok");
  } else {
    const reason = result.error ?? `HTTP ${result.status}`;
    setStatus(`Could not reach backend at ${result.base}: ${reason}`, "err");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadCurrent();
  $("save-btn").addEventListener("click", save);
  $("reset-btn").addEventListener("click", resetToDefault);
  $("test-btn").addEventListener("click", testConnection);
});
