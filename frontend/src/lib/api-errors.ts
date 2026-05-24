import { ApiError } from "../api";

const FALLBACK_MESSAGE = "Something went wrong. Try again.";
const RAW_REQUEST_PATTERN = /^Request to .+ failed with status \d+$/;

/**
 * Extract a user-facing message from an error thrown by the API layer.
 *
 * Resolution order:
 *   1. If the error is an {@link ApiError} whose response body has a `detail`
 *      field, return a string derived from it. Supported `detail` shapes:
 *        - `string`                            → returned as-is
 *        - `{ message: string }`               → returns `message`
 *        - FastAPI validation array `[{ msg }]` → returns the first `msg`
 *   2. If the error is a plain `Error` with a non-empty message that is NOT a
 *      raw `Request to /... failed with status N` string, return that message.
 *   3. Otherwise return a short, friendly fallback. Never returns a raw
 *      request/status string.
 */
export function extractApiDetail(err: unknown): string {
  if (err instanceof ApiError) {
    return extractFromBody(err.body) ?? FALLBACK_MESSAGE;
  }
  if (err instanceof Error) {
    if (!err.message || RAW_REQUEST_PATTERN.test(err.message)) {
      return FALLBACK_MESSAGE;
    }
    return err.message;
  }
  if (typeof err === "string" && err.trim()) return err.trim();
  return FALLBACK_MESSAGE;
}

function extractFromBody(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  if (!("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (
      first &&
      typeof first === "object" &&
      "msg" in first &&
      typeof (first as { msg: unknown }).msg === "string"
    ) {
      return (first as { msg: string }).msg;
    }
    return null;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return null;
}
