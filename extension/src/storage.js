// Persistent extension settings.
//
// The only setting today is the backend base URL. Defaults to the
// local backend on http://localhost:8000 but the user can override it
// from the options page if they run uvicorn on a non-standard host/port.

import { browserApi } from "./browser_api.js";

export const DEFAULT_BACKEND_BASE_URL = "http://localhost:8000";
export const STORAGE_KEY_BACKEND_BASE_URL = "backend_base_url";

/**
 * Read the configured backend base URL from extension storage.
 * Falls back to DEFAULT_BACKEND_BASE_URL if no value is set, if the
 * storage API is unavailable, or if the stored value is invalid.
 *
 * @returns {Promise<string>}
 */
export async function getBackendBaseUrl() {
  try {
    const result = await browserApi.storage.local.get(
      STORAGE_KEY_BACKEND_BASE_URL,
    );
    const value = result?.[STORAGE_KEY_BACKEND_BASE_URL];
    if (typeof value === "string" && value.trim().length > 0) {
      return normalizeBaseUrl(value);
    }
  } catch {
    // storage API not available (e.g. tests) — fall through to default
  }
  return DEFAULT_BACKEND_BASE_URL;
}

/**
 * Persist the backend base URL.
 *
 * @param {string} value
 * @returns {Promise<void>}
 */
export async function setBackendBaseUrl(value) {
  const normalized = normalizeBaseUrl(value);
  await browserApi.storage.local.set({
    [STORAGE_KEY_BACKEND_BASE_URL]: normalized,
  });
}

/**
 * Strip trailing slashes so we can safely concatenate paths.
 * @param {string} value
 * @returns {string}
 */
export function normalizeBaseUrl(value) {
  return String(value).trim().replace(/\/+$/, "");
}
