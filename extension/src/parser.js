// Pure LinkedIn job-page parser.
//
// This module must not touch DOM globals (window, document) at import time.
// All callers pass in a parsed Document and the page URL. The content script
// in the extension wraps this with the real `document` global; tests run it
// against a jsdom-built Document so no headless browser is needed.
//
// Both Chrome MV3 and Firefox MV2 bundle this same module via build.mjs, so
// any behavior change here applies to both browsers. Do not branch on host
// browser inside this file — browser-specific code lives in browser_api.js.

const LINKEDIN_JOB_URL_RE =
  /^https?:\/\/(?:[a-z0-9-]+\.)*linkedin\.com\/jobs\//i;

// Containers that scope the *active* (right-hand) job detail pane on a
// two-pane collections/search page. The left-hand sidebar list is full of
// other jobs' titles and "Top job picks for you"-style headers; we must
// never extract from there.
const ACTIVE_PANE_SELECTORS = [
  ".jobs-search__job-details--container",
  ".jobs-details__main-content",
  ".job-view-layout",
  ".jobs-details",
  ".scaffold-layout__detail",
];

const TITLE_SELECTORS = [
  ".job-details-jobs-unified-top-card__job-title",
  ".jobs-unified-top-card__job-title",
  "h1.topcard__title",
];

const COMPANY_SELECTORS = [
  ".job-details-jobs-unified-top-card__company-name a",
  ".job-details-jobs-unified-top-card__company-name",
  ".jobs-unified-top-card__company-name a",
  ".jobs-unified-top-card__company-name",
  ".topcard__org-name-link",
  "[data-test-job-details-company-name]",
];

// Containers that hold the primary top-card metadata line, e.g.
//   "Haifa, Haifa District, Israel · Reposted 5 days ago · Over 10 people clicked apply"
// We read the whole container, split on the bullet, then pick the first
// segment that isn't recognised noise (see LOCATION_NOISE_PATTERNS).
const LOCATION_CONTAINER_SELECTORS = [
  ".job-details-jobs-unified-top-card__primary-description-container",
  ".jobs-unified-top-card__primary-description-container",
];

// Legacy/fallback location selectors — only consulted when the container
// approach above finds nothing usable.
const LOCATION_FALLBACK_SELECTORS = [
  ".job-details-jobs-unified-top-card__bullet",
  ".jobs-unified-top-card__bullet",
  ".topcard__flavor--bullet",
  "[data-test-job-location]",
];

// Segments that look like timing/applicant chatter rather than a place.
// LinkedIn frequently reorders these around the location, so a strict
// allow-only approach (require a comma) would drop valid one-word locations
// like "Remote" or "Berlin". Denylist matches the task spec exactly.
const LOCATION_NOISE_PATTERNS = [
  /^reposted\b/i,
  /^posted\b/i,
  /^promoted$/i,
  /^over\s+\d+\s+(?:people|applicants|connections)/i,
  /\bago\b/i,
  /\bclicked apply\b/i,
  /^responses managed off linkedin/i,
  /^\d+\s+applicants?$/i,
];

// Ranked list of selectors used to locate the job description on LinkedIn.
// LinkedIn ships several layouts (logged-in two-pane, /jobs/view/ detail
// page, public-share fallback) and the markup drifts often. We try the
// outermost container first so we capture the whole "About the job" block
// even when the inner `#job-details` div is a stub. Absolute XPath is
// intentionally avoided — see task 053.
const DESCRIPTION_SELECTORS = [
  ".jobs-description__container",
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

// Hard cap on the description we store. The backend column is wide but the
// review UI starts to chug on multi-MB postings, and LinkedIn occasionally
// inlines the entire candidate-application JSON into the description block.
const DESCRIPTION_MAX_CHARS = 20000;

// Whitespace class includes non-breaking space ( ) because LinkedIn
// frequently injects NBSPs around bullets and inline icons.
const INLINE_WS_RE = /[ \t ]+/g;

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

function findActivePane(document) {
  for (const selector of ACTIVE_PANE_SELECTORS) {
    const node = document.querySelector(selector);
    if (node) return { node, selector };
  }
  return null;
}

function firstMatchingTextWithin(scope, selectors) {
  for (const selector of selectors) {
    const node = scope.querySelector(selector);
    if (!node) continue;
    const text = (node.textContent || "").replace(/\s+/g, " ").trim();
    if (text) return { text, selector };
  }
  return null;
}

function firstMatchingText(document, selectors) {
  const pane = findActivePane(document);
  if (pane) {
    const hit = firstMatchingTextWithin(pane.node, selectors);
    if (hit) return hit;
  }
  return firstMatchingTextWithin(document, selectors);
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
  // Scope the search to the active pane when we have one — otherwise the
  // sidebar "Save"/"Apply" affordances of other listings can leak in.
  const pane = findActivePane(document);
  const scope = pane ? pane.node : document;
  const candidates = scope.querySelectorAll(
    "button, a, span.artdeco-button__text",
  );
  for (const el of candidates) {
    const text = (el.textContent || "").trim().toLowerCase();
    if (!text) continue;
    if (text === "easy apply" || text.startsWith("easy apply")) {
      return "easy_apply";
    }
  }
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

function extractTitle(document) {
  // 1. Structured top-card selectors, scoped to the active pane first.
  const structured = firstMatchingText(document, TITLE_SELECTORS);
  if (structured) return structured;
  // 2. Active-pane h1, scoped so we don't grab the sidebar list's h1
  //    ("Top job picks for you", etc.).
  const pane = findActivePane(document);
  if (pane) {
    const h1 = pane.node.querySelector("h1");
    if (h1) {
      const text = (h1.textContent || "").replace(/\s+/g, " ").trim();
      if (text) return { text, selector: `${pane.selector} h1` };
    }
  }
  return null;
}

function extractCompany(document) {
  return firstMatchingText(document, COMPANY_SELECTORS);
}

function isLocationNoise(segment) {
  return LOCATION_NOISE_PATTERNS.some((re) => re.test(segment));
}

function extractLocation(document) {
  const pane = findActivePane(document);
  const scopes = pane ? [pane.node, document] : [document];
  for (const scope of scopes) {
    for (const selector of LOCATION_CONTAINER_SELECTORS) {
      const node = scope.querySelector(selector);
      if (!node) continue;
      const text = (node.textContent || "").replace(/\s+/g, " ").trim();
      if (!text) continue;
      const segments = text
        .split("·")
        .map((s) => s.replace(INLINE_WS_RE, " ").trim())
        .filter(Boolean);
      for (const seg of segments) {
        if (!isLocationNoise(seg)) {
          return { text: seg, selector };
        }
      }
    }
  }
  // Legacy single-value selectors as a last resort.
  return firstMatchingText(document, LOCATION_FALLBACK_SELECTORS);
}

function extractDescription(document) {
  // Walk the ranked selector list within the active pane first, then across
  // the document. Return the first match that clears the "real description"
  // length bar; otherwise return the longest shorter match so an unusually
  // terse posting still surfaces something useful.
  const pane = findActivePane(document);
  const scopes = pane ? [pane.node, document] : [document];

  let fallback = null;
  for (const scope of scopes) {
    for (const selector of DESCRIPTION_SELECTORS) {
      const node = scope.querySelector(selector);
      if (!node) continue;
      let text = normalizeMultiline(readVisibleText(node));
      if (!text) continue;
      if (text.length > DESCRIPTION_MAX_CHARS) {
        text = text.slice(0, DESCRIPTION_MAX_CHARS);
      }
      if (text.length >= DESCRIPTION_MIN_CHARS) {
        return { text, selector };
      }
      if (!fallback || text.length > fallback.text.length) {
        fallback = { text, selector };
      }
    }
    if (fallback) break; // don't widen scope past pane if we found anything
  }
  return fallback;
}

function extractRawText(document) {
  // Prefer the active job detail pane so we don't capture the surrounding
  // LinkedIn navigation chrome or the left-hand jobs list.
  const pane = findActivePane(document);
  const node = pane ? pane.node : document.querySelector("main") || document.body;
  if (!node) return null;
  const text = (node.textContent || "")
    .replace(INLINE_WS_RE, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return text || null;
}

/**
 * Capture a bounded plain-text excerpt of the page. Used as a last-resort
 * fallback so the backend/Review Capture page still has something to surface
 * when every structured selector misses. Prefers the active job detail pane
 * over the whole document so the left-hand sidebar list doesn't dominate
 * the excerpt on collections pages.
 *
 * @param {Document} document
 * @returns {string | null}
 */
export function extractPageText(document) {
  const pane = findActivePane(document);
  const node = pane ? pane.node : document.body;
  if (!node) return null;
  const raw = readVisibleText(node) || node.textContent || "";
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

  const pane = findActivePane(document);
  const titleHit = extractTitle(document);
  const companyHit = extractCompany(document);
  const locationHit = extractLocation(document);
  const descriptionHit = extractDescription(document);
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

  const structuredTitle = titleHit ? titleHit.text : null;
  const company = companyHit ? companyHit.text : null;
  const location = locationHit ? locationHit.text : null;
  const description = descriptionHit ? descriptionHit.text : null;

  // Pick the best title we have. Structured (active-pane-scoped) first,
  // then OG, then the <title> tag (which on LinkedIn typically reads
  // "<job> at <co> | LinkedIn" — strip the trailing " | LinkedIn" so we
  // don't store that suffix in the job title field). We intentionally do
  // NOT fall back to a bare document-wide `h1`, because on a collections
  // page the only h1 in DOM order is often the sidebar list header
  // ("Top job picks for you").
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
    active_pane_selector: pane ? pane.selector : null,
    selectors_matched: {
      title: Boolean(structuredTitle),
      company: Boolean(company),
      location: Boolean(location),
      description: Boolean(description),
    },
    matched_selectors: {
      title: titleHit ? titleHit.selector : null,
      company: companyHit ? companyHit.selector : null,
      location: locationHit ? locationHit.selector : null,
      description: descriptionHit ? descriptionHit.selector : null,
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
