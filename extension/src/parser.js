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
  "[data-test-job-details-company-name]",
];

const LOCATION_SELECTORS = [
  ".job-details-jobs-unified-top-card__primary-description-container .tvm__text--low-emphasis",
  ".job-details-jobs-unified-top-card__bullet",
  ".jobs-unified-top-card__bullet",
  ".topcard__flavor--bullet",
  "[data-test-job-location]",
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

// Whitespace class includes non-breaking space ( ) because LinkedIn
// frequently injects NBSPs around bullets and inline icons.
const INLINE_WS_RE = /[ \t ]+/g;

// Upper bound on the body-text fallback we send to the backend. Captures
// enough to recover title/description from a stale-selector page without
// blowing up the request body when LinkedIn injects huge SSR payloads.
const PAGE_TEXT_MAX_CHARS = 20000;

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

function metaContent(document, selector) {
  const node = document.querySelector(selector);
  if (!node) return null;
  const value = node.getAttribute ? node.getAttribute("content") : null;
  if (!value) return null;
  const trimmed = value.replace(/\s+/g, " ").trim();
  return trimmed || null;
}

function documentTitle(document) {
  const raw = typeof document.title === "string" ? document.title : "";
  const trimmed = raw.replace(/\s+/g, " ").trim();
  return trimmed || null;
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
 * Capture a bounded plain-text excerpt of the page body. Used as a last-
 * resort fallback so the backend/Review Capture page still has something
 * to surface when every structured selector misses.
 *
 * @param {Document} document
 * @returns {string | null}
 */
export function extractPageText(document) {
  const body = document.body;
  if (!body) return null;
  const raw = readVisibleText(body) || body.textContent || "";
  if (!raw) return null;
  const normalized = raw
    .replace(INLINE_WS_RE, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!normalized) return null;
  return normalized.length > PAGE_TEXT_MAX_CHARS
    ? normalized.slice(0, PAGE_TEXT_MAX_CHARS)
    : normalized;
}

/**
 * Parse a LinkedIn job page.
 *
 * @param {{ document: Document, url: string, selectedText?: string }} input
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
 *   raw_text: string | null,
 *   page_title: string | null,
 *   page_text: string | null,
 *   selected_text: string | null,
 *   diagnostics: object
 * }}
 * @throws {Error} if `url` is not a LinkedIn job page URL.
 */
export function parseLinkedInJob({ document, url, selectedText } = {}) {
  if (!isLinkedInJobUrl(url)) {
    throw new Error("Not a LinkedIn job page");
  }
  if (!document || typeof document.querySelector !== "function") {
    throw new Error("parseLinkedInJob requires a Document with querySelector");
  }

  const structuredTitle = firstMatchingText(document, TITLE_SELECTORS);
  const company = firstMatchingText(document, COMPANY_SELECTORS);
  const location = firstMatchingText(document, LOCATION_SELECTORS);
  const description = extractDescriptionText(document);
  const application_method = detectApplicationMethod(document);
  const raw_text = extractRawText(document);
  const external_job_id = extractExternalJobId(url);

  const og_title = metaContent(document, 'meta[property="og:title"]');
  const meta_description = metaContent(document, 'meta[name="description"]');
  const page_title = documentTitle(document);
  const page_text = extractPageText(document);
  const selected_text =
    typeof selectedText === "string" && selectedText.trim().length > 0
      ? selectedText.trim().slice(0, PAGE_TEXT_MAX_CHARS)
      : null;

  // Pick the best title we have. Structured first, then OG, then the
  // <title> tag (which on LinkedIn typically reads "<job> at <co> | LinkedIn"
  // — strip the trailing " | LinkedIn" so we don't store that suffix in the
  // job title field).
  let title = structuredTitle;
  if (!title && og_title) title = og_title;
  if (!title && page_title) title = stripLinkedInTitleSuffix(page_title);

  // If structured description missed, fall back to the meta description
  // tag (LinkedIn sets it to a useful summary on /jobs/view/<id> pages).
  let description_text = description || "";
  if (!description_text && meta_description) {
    description_text = meta_description;
  }

  const diagnostics = {
    extractor: "linkedin",
    selectors_matched: {
      title: Boolean(structuredTitle),
      company: Boolean(company),
      location: Boolean(location),
      description: Boolean(description),
    },
    fallbacks_used: {
      og_title: Boolean(!structuredTitle && og_title),
      document_title: Boolean(!structuredTitle && !og_title && page_title),
      meta_description: Boolean(!description && meta_description),
    },
    document_title: page_title,
    body_text_length: page_text ? page_text.length : 0,
    url_has_current_job_id: /[?&]currentJobId=\d+/.test(url),
    has_selected_text: Boolean(selected_text),
  };

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
    page_title,
    page_text,
    selected_text,
    diagnostics,
  };
}

// LinkedIn's <title> on job pages typically ends with " | LinkedIn". When we
// fall back to that, peel the suffix so the title field reads naturally.
function stripLinkedInTitleSuffix(title) {
  return title.replace(/\s*[|·]\s*LinkedIn\s*$/i, "").trim() || title;
}
