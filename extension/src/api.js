// Tiny helper used by the popup to POST captures to the local backend.
// Kept separate from the parser so the parser stays free of fetch/chrome deps.

import {
  DEFAULT_BACKEND_BASE_URL,
  getBackendBaseUrl,
  normalizeBaseUrl,
} from "./storage.js";

// Frontend lives on Vite's default dev port.
export const DEFAULT_FRONTEND_BASE = "http://localhost:5173";

// Default capture endpoint, derived from DEFAULT_BACKEND_BASE_URL. Exposed
// for tests / docs; runtime code should prefer captureEndpoint() which
// honors the user's configured backend base URL.
export const DEFAULT_CAPTURE_ENDPOINT = `${DEFAULT_BACKEND_BASE_URL}/captures`;

/**
 * Build the frontend URL for a job workspace.
 *
 * @param {string} jobId
 * @param {string} [base=DEFAULT_FRONTEND_BASE]
 * @returns {string}
 */
export function jobWorkspaceUrl(jobId, base = DEFAULT_FRONTEND_BASE) {
  return `${base}/jobs/${jobId}`;
}

/**
 * Resolve the capture endpoint from the configured backend base URL.
 *
 * @returns {Promise<string>}
 */
export async function captureEndpoint() {
  const base = await getBackendBaseUrl();
  return `${normalizeBaseUrl(base)}/captures`;
}

/**
 * Health-probe the configured backend so the popup can tell the user
 * whether the local cockpit is reachable before they attempt a capture.
 *
 * @param {string} [base] Override the configured base URL (used by the
 *   options page to test a value the user hasn't saved yet).
 * @returns {Promise<{ ok: boolean, status?: number, error?: string, base: string }>}
 */
export async function checkBackendHealth(base) {
  const resolved = normalizeBaseUrl(base ?? (await getBackendBaseUrl()));
  try {
    const response = await fetch(`${resolved}/health`, { method: "GET" });
    return { ok: response.ok, status: response.status, base: resolved };
  } catch (err) {
    return {
      ok: false,
      error: err && err.message ? err.message : String(err),
      base: resolved,
    };
  }
}

/**
 * POST a normalized capture payload to the local backend.
 *
 * @param {object} payload  Normalized capture payload (see parser.js).
 * @param {string} [endpoint]  Optional override; defaults to the
 *   configured backend base URL + "/captures".
 * @returns {Promise<{ status: number, body: any }>}
 */
export async function postCapture(payload, endpoint) {
  const target = endpoint ?? (await captureEndpoint());
  const response = await fetch(target, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      captured_at: new Date().toISOString(),
    }),
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return { status: response.status, body };
}
