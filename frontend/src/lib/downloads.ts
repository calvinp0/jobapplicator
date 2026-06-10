/**
 * Browser download helpers (task 122).
 *
 * The backend streams artifacts with a ``Content-Disposition: attachment``
 * header carrying the human-readable filename, so the client only needs to
 * turn the response body into a file the browser saves. Keeping this in its
 * own module (no ``api`` imports) makes it trivial to unit test and reuse.
 */

/** Save a blob to the user's machine under ``filename`` without navigating. */
export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Pull the filename out of a ``Content-Disposition`` header.
 *
 * Handles both the RFC 5987 ``filename*=UTF-8''...`` form and the plain
 * ``filename="..."`` form, returning ``null`` when neither is present so the
 * caller can fall back to a sensible default.
 */
export function parseContentDispositionFilename(
  header: string | null,
): string | null {
  if (!header) return null;
  const extended = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header);
  if (extended) {
    const raw = extended[1].trim().replace(/^"|"$/g, "");
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}
