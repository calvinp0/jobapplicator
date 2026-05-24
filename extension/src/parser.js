// Pure LinkedIn job-page parser.
//
// This module must not touch DOM globals (window, document) at import time.
// All callers pass in a parsed Document and the page URL. The content script
// in the extension wraps this with the real `document` global; tests run it
// against a jsdom-built Document so no headless browser is needed.

const LINKEDIN_JOB_URL_RE =
  /^https?:\/\/(?:[a-z0-9-]+\.)*linkedin\.com\/jobs\//i;

const TITLE_SELECTORS = [
  ".job-details-jobs-unified-top-card__job-title",
  ".jobs-unified-top-card__job-title",
  "h1.topcard__title",
  "h1",
];

const COMPANY_SELECTORS = [
  ".job-details-jobs-unified-top-card__company-name a",
  ".job-details-jobs-unified-top-card__company-name",
  ".jobs-unified-top-card__company-name a",
  ".jobs-unified-top-card__company-name",
  ".topcard__org-name-link",
];

const LOCATION_SELECTORS = [
  ".job-details-jobs-unified-top-card__primary-description-container .tvm__text--low-emphasis",
  ".job-details-jobs-unified-top-card__bullet",
  ".jobs-unified-top-card__bullet",
  ".topcard__flavor--bullet",
];

// Ranked list of selectors used to locate the job description on LinkedIn.
// LinkedIn ships several layouts (logged-in two-pane, /jobs/view/ detail page,
// public-share fallback) and the markup drifts often. We try the most specific
// id first, then the layout-level wrappers, then a couple of legacy/test-id
// selectors. Absolute XPath is intentionally avoided — see task 053.
const DESCRIPTION_SELECTORS = [
  "#job-details",
  ".jobs-description__content",
  ".jobs-box__html-content",
  ".jobs-description-content__text",
  "[data-test-job-description]",
  ".description__text",
];

// A non-empty match shorter than this is treated as suspect (e.g. a not-yet-
// hydrated skeleton). We still keep it as a fallback in case no selector
// returns a "real" description.
const DESCRIPTION_MIN_CHARS = 100;

// Whitespace class includes non-breaking space ( ) because LinkedIn
// frequently injects NBSPs around bullets and inline icons.
const INLINE_WS_RE = /[ \t ]+/g;

/**
 * Determine whether a URL looks like a LinkedIn job page.
 * @param {string} url
 * @returns {boolean}
 */
export function isLinkedInJobUrl(url) {
  if (typeof url !== "string" || url.length === 0) return false;
  return LINKEDIN_JOB_URL_RE.test(url);
}

/**
 * Extract LinkedIn's external job id from a URL, if present.
 *
 * Handles:
 *   - /jobs/view/4012345678/
 *   - /jobs/view/4012345678
 *   - ?currentJobId=4012345678
 *
 * @param {string} url
 * @returns {string | null}
 */
export function extractExternalJobId(url) {
  if (typeof url !== "string") return null;
  const viewMatch = url.match(/\/jobs\/view\/(\d+)/i);
  if (viewMatch) return viewMatch[1];
  try {
    const parsed = new URL(url);
    const queryId = parsed.searchParams.get("currentJobId");
    if (queryId && /^\d+$/.test(queryId)) return queryId;
  } catch {
    // not a parseable absolute URL; fall through
  }
  return null;
}

function firstMatchingText(document, selectors) {
  for (const selector of selectors) {
    const node = document.querySelector(selector);
    if (!node) continue;
    const text = (node.textContent || "").replace(/\s+/g, " ").trim();
    if (text) return text;
  }
  return null;
}

function firstMatchingNode(document, selectors) {
  for (const selector of selectors) {
    const node = document.querySelector(selector);
    if (node) return node;
  }
  return null;
}

function detectApplicationMethod(document) {
  const candidates = document.querySelectorAll(
    "button, a, span.artdeco-button__text",
  );
  for (const el of candidates) {
    const text = (el.textContent || "").trim().toLowerCase();
    if (!text) continue;
    if (text === "easy apply" || text.startsWith("easy apply")) {
      return "easy_apply";
    }
  }
  // Some job pages have an "Apply" button that opens an external site.
  for (const el of candidates) {
    const text = (el.textContent || "").trim().toLowerCase();
    if (text === "apply" || text.startsWith("apply on")) {
      return "external";
    }
  }
  return null;
}

function readVisibleText(node) {
  // Prefer innerText in a real browser — it respects CSS visibility (LinkedIn
  // sometimes hides parts of the description behind a "Show more" affordance)
  // and inserts line breaks at block boundaries. jsdom does not implement
  // innerText faithfully, so fall back to textContent for tests.
  if (!node) return "";
  const fromInner = typeof node.innerText === "string" ? node.innerText : "";
  if (fromInner) return fromInner;
  return node.textContent || "";
}

function normalizeMultiline(raw) {
  if (!raw) return "";
  return raw
    .split(/\n+/)
    .map((line) => line.replace(INLINE_WS_RE, " ").trim())
    .filter((line) => line.length > 0)
    .join("\n");
}

function extractDescriptionText(document) {
  // Walk the ranked selector list. Return the first match that clears the
  // "real description" length bar; otherwise return the longest shorter match
  // so an unusually terse posting still surfaces something useful.
  let fallback = "";
  for (const selector of DESCRIPTION_SELECTORS) {
    const node = document.querySelector(selector);
    if (!node) continue;
    const text = normalizeMultiline(readVisibleText(node));
    if (!text) continue;
    if (text.length >= DESCRIPTION_MIN_CHARS) return text;
    if (text.length > fallback.length) fallback = text;
  }
  return fallback || null;
}

function extractRawText(document) {
  // Prefer the top-card + description container so we do not capture the
  // surrounding LinkedIn navigation chrome. Falls back to <main> or <body>.
  const containerSelectors = [
    ".jobs-search__job-details--container",
    ".job-view-layout",
    "main",
    "body",
  ];
  const node = firstMatchingNode(document, containerSelectors);
  if (!node) return null;
  const text = (node.textContent || "")
    .replace(INLINE_WS_RE, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return text || null;
}

/**
 * Parse a LinkedIn job page.
 *
 * @param {{ document: Document, url: string }} input
 * @returns {{
 *   source_platform: string,
 *   capture_method: string,
 *   external_url: string,
 *   external_job_id: string | null,
 *   company: string | null,
 *   title: string | null,
 *   location: string | null,
 *   description_text: string,
 *   application_method: string | null,
 *   raw_text: string | null
 * }}
 * @throws {Error} if `url` is not a LinkedIn job page URL.
 */
export function parseLinkedInJob({ document, url }) {
  if (!isLinkedInJobUrl(url)) {
    throw new Error("Not a LinkedIn job page");
  }
  if (!document || typeof document.querySelector !== "function") {
    throw new Error("parseLinkedInJob requires a Document with querySelector");
  }

  const title = firstMatchingText(document, TITLE_SELECTORS);
  const company = firstMatchingText(document, COMPANY_SELECTORS);
  const location = firstMatchingText(document, LOCATION_SELECTORS);
  const description_text = extractDescriptionText(document) || "";
  const application_method = detectApplicationMethod(document);
  const raw_text = extractRawText(document);
  const external_job_id = extractExternalJobId(url);

  return {
    source_platform: "linkedin",
    capture_method: "browser_extension_current_page",
    external_url: url,
    external_job_id,
    company,
    title,
    location,
    description_text,
    application_method,
    raw_text,
  };
}
