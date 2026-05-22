// Tiny helper used by the popup to POST captures to the local backend.
// Kept separate from the parser so the parser stays free of fetch/chrome deps.

export const DEFAULT_CAPTURE_ENDPOINT = "http://127.0.0.1:8000/captures";

/**
 * POST a normalized capture payload to the local backend.
 *
 * @param {object} payload  Normalized capture payload (see parser.js).
 * @param {string} [endpoint=DEFAULT_CAPTURE_ENDPOINT]
 * @returns {Promise<{ status: number, body: any }>}
 */
export async function postCapture(payload, endpoint = DEFAULT_CAPTURE_ENDPOINT) {
  const response = await fetch(endpoint, {
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
