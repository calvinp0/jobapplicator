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

// Newer LinkedIn renders the job detail pane as Server-Driven UI (SDUI). The
// classic `.jobs-description__*` / `#job-details` nodes are gone; the only
// stable handles are *semantic data attributes* the SDUI runtime emits. The
// surrounding class names are content-hashed atomic CSS (e.g. `._107b9f77`)
// and rotate on every deploy, so we anchor on the attributes instead and try
// them after the classic selectors above. See task 053 (no hashed classes /
// no absolute XPath).
const SDUI_DESCRIPTION_SELECTORS = [
  '[data-sdui-component*="aboutTheJob"]',
  '[data-testid="expandable-text-box"]',
  '[data-testid*="expandable"]',
  '[data-testid*="description"]',
];

// Ranked list tried first: classic markup, then SDUI semantic attributes.
const RANKED_DESCRIPTION_SELECTORS = [
  ...DESCRIPTION_SELECTORS,
  ...SDUI_DESCRIPTION_SELECTORS,
];

// Headings/phrases that signal a real job description. Used by the SDUI
// scoring fallback (below) to tell a description container apart from
// navigation, recommendations, or premium-upsell blocks.
const JOB_HEADING_KEYWORDS = [
  "description",
  "about the role",
  "about the job",
  "about the team",
  "about the company",
  "about us",
  "about the ai division",
  "responsibilities",
  "what you'll do",
  "what you will do",
  "requirements",
  "qualifications",
  "minimum qualifications",
  "preferred qualifications",
  "basic qualifications",
  "who you are",
  "your impact",
  "benefits",
  "what we offer",
];

// Whole-line control affordances LinkedIn injects in/around the description
// (buttons, back links, the Premium pill). Matched against a node's *entire*
// trimmed text so we strip "Apply" but never the word inside a sentence.
const CONTROL_LINE_RE =
  /^(back to careers|see more jobs|see less|show more|show less|premium|try premium|apply|easy apply|apply now|save|saved|report this job)$/i;

// Markers (id / class / data-* / role) that disqualify a scored candidate
// outright: site chrome, recommendations, premium upsell. We deliberately do
// NOT inspect hashed atomic classes here — they carry no signal either way, so
// a container is never chosen or rejected because of them.
const DESCRIPTION_NEGATIVE_RE =
  /(^|[\s_-])(nav|navigation|footer|sidebar|aside|breadcrumb|recommended|recommendation|similar-?jobs|people-also-viewed|premium|upsell|signin|login)([\s_-]|$)/i;

// Body text that marks a block as recommendations/upsell rather than the role.
const UPSELL_TEXT_RE =
  /(try premium|retry premium|premium to see|unlock with premium|people also viewed|similar jobs|more jobs for you|jobs you may be interested)/i;

// Length past which extra characters stop improving a candidate's score, so a
// giant wrapper can't beat a focused description on raw length alone.
const DESCRIPTION_SCORE_LENGTH_CAP = 4000;

// Block-level tags after which we insert a newline when serializing a cloned
// container. Lets us recover paragraph structure without depending on the
// browser's innerText (which jsdom does not implement) and without reading a
// detached clone's layout (which yields "" for innerText in a real browser).
const BLOCK_TAGS = new Set([
  "P",
  "DIV",
  "SECTION",
  "ARTICLE",
  "LI",
  "UL",
  "OL",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "TR",
  "BLOCKQUOTE",
]);

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

// Serialize an element to plain text, inserting newlines at block
// boundaries. Works identically under jsdom (tests) and a real browser, and
// is safe on a detached clone — unlike innerText, which needs layout.
function collectBlockText(node, out) {
  for (const child of node.childNodes) {
    if (child.nodeType === 3) {
      out.push(child.textContent || "");
    } else if (child.nodeType === 1) {
      const tag = child.tagName;
      if (tag === "BR") {
        out.push("\n");
        continue;
      }
      collectBlockText(child, out);
      if (BLOCK_TAGS.has(tag)) out.push("\n");
    }
  }
}

// Normalize multi-line text and drop standalone control-affordance lines
// ("Apply", "Save", "Show more", the Premium pill, …) that survive as their
// own line after block serialization.
function cleanDescriptionText(raw) {
  const normalized = normalizeMultiline(raw);
  if (!normalized) return "";
  return normalized
    .split("\n")
    .filter((line) => !CONTROL_LINE_RE.test(line.trim()))
    .join("\n")
    .trim();
}

// Read a description container's visible text. We clone the node so we can
// prune control elements (Apply/Save buttons, "Back to careers" / "See more
// jobs" links) without mutating the live page, then serialize to clean text.
function readContainerText(node) {
  if (!node || typeof node.cloneNode !== "function") {
    return cleanDescriptionText(readVisibleText(node));
  }
  const clone = node.cloneNode(true);
  if (typeof clone.querySelectorAll === "function") {
    clone.querySelectorAll("button, [role='button']").forEach((el) => el.remove());
    clone.querySelectorAll("a, span, div, li").forEach((el) => {
      const t = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (t && CONTROL_LINE_RE.test(t)) el.remove();
    });
  }
  const out = [];
  collectBlockText(clone, out);
  return cleanDescriptionText(out.join(""));
}

// Describe a scored candidate with a *stable* selector for diagnostics —
// never a hashed atomic class. Prefer SDUI/test attributes, then a semantic
// id, then the bare tag name.
function describeCandidateSelector(node) {
  const sdui = node.getAttribute("data-sdui-component");
  if (sdui) return `[data-sdui-component="${sdui}"]`;
  const testid = node.getAttribute("data-testid");
  if (testid) return `[data-testid="${testid}"]`;
  const tag = (node.tagName || "div").toLowerCase();
  const id = node.id;
  if (id && /^[a-z][\w-]*$/i.test(id) && !/^_?[0-9a-f]{6,}$/i.test(id)) {
    return `${tag}#${id}`;
  }
  return tag;
}

// Score a single container as a job-description candidate. Returns null when
// the node is site chrome / recommendations / upsell or too short to be real.
function scoreDescriptionCandidate(node) {
  if (!node || typeof node.querySelectorAll !== "function") return null;
  if (typeof node.closest === "function" && node.closest("nav, footer, header, aside")) {
    return null;
  }
  const role = (node.getAttribute("role") || "").toLowerCase();
  if (["navigation", "banner", "contentinfo", "complementary", "search"].includes(role)) {
    return null;
  }

  const marker = [
    node.id || "",
    typeof node.className === "string" ? node.className : "",
    node.getAttribute("data-testid") || "",
    node.getAttribute("data-sdui-component") || "",
  ].join(" ");
  if (DESCRIPTION_NEGATIVE_RE.test(marker)) return null;

  const text = readContainerText(node);
  if (!text || text.length < DESCRIPTION_MIN_CHARS) return null;
  // A short block that is purely upsell/recommendation chatter is noise.
  if (UPSELL_TEXT_RE.test(text) && text.length < 600) return null;

  const lower = text.toLowerCase();
  let keywordHits = 0;
  for (const keyword of JOB_HEADING_KEYWORDS) {
    if (lower.includes(keyword)) keywordHits += 1;
  }

  const lengthScore =
    Math.min(text.length, DESCRIPTION_SCORE_LENGTH_CAP) / DESCRIPTION_SCORE_LENGTH_CAP;
  let score = keywordHits * 3 + lengthScore * 2;

  const sdui = (node.getAttribute("data-sdui-component") || "").toLowerCase();
  const testid = (node.getAttribute("data-testid") || "").toLowerCase();
  if (sdui.includes("aboutthejob")) score += 4;
  if (/(expandable|description|about-the-job)/.test(testid)) score += 3;
  if (UPSELL_TEXT_RE.test(text)) score -= 3;

  // Require some positive job signal: either a heading keyword or a strong
  // attribute hint that already lifted the score.
  if (keywordHits === 0 && score < 3) return null;

  return { text, score, selector: describeCandidateSelector(node) };
}

// SDUI scoring fallback: when neither the classic selectors nor the SDUI
// attribute selectors resolve a description, score visible candidate
// containers and return the best one. Anchors on semantics (attributes,
// headings) and never on hashed classes.
function scoreSduiDescription(document) {
  const seen = new Set();
  const candidates = [];
  const add = (node) => {
    if (node && node.nodeType === 1 && !seen.has(node)) {
      seen.add(node);
      candidates.push(node);
    }
  };

  document
    .querySelectorAll("[data-sdui-component], [data-testid], main, article, section")
    .forEach(add);
  // Containers anchored by a recognizable job heading.
  document.querySelectorAll("h1, h2, h3, h4").forEach((heading) => {
    const text = (heading.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
    if (!text) return;
    const isJobHeading = JOB_HEADING_KEYWORDS.some(
      (keyword) => text === keyword || text.startsWith(keyword),
    );
    if (!isJobHeading) return;
    if (typeof heading.closest !== "function") return;
    const block = heading.closest(
      "[data-sdui-component], [data-testid], section, article, main, div",
    );
    add(block);
    if (block) add(block.parentElement);
  });

  let best = null;
  for (const node of candidates) {
    const scored = scoreDescriptionCandidate(node);
    if (scored && (!best || scored.score > best.score)) best = scored;
  }
  if (!best) return null;
  return { text: best.text, selector: best.selector };
}

function extractDescription(document) {
  // 1. Ranked selectors (classic markup first, then SDUI semantic attributes)
  //    within the active pane, then across the document. Return the first
  //    match that clears the "real description" length bar; otherwise keep the
  //    longest shorter match so a terse posting still surfaces something.
  const pane = findActivePane(document);
  const scopes = pane ? [pane.node, document] : [document];

  let fallback = null;
  for (const scope of scopes) {
    for (const selector of RANKED_DESCRIPTION_SELECTORS) {
      const node = scope.querySelector(selector);
      if (!node) continue;
      let text = readContainerText(node);
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

  // 2. SDUI scoring fallback: no known selector resolved a full description,
  //    so score candidate containers by length + job-heading keywords while
  //    excluding nav/footer/recommendation/premium blocks.
  const scored = scoreSduiDescription(document);
  if (scored) {
    let text = scored.text;
    if (text.length > DESCRIPTION_MAX_CHARS) {
      text = text.slice(0, DESCRIPTION_MAX_CHARS);
    }
    if (
      text.length >= DESCRIPTION_MIN_CHARS &&
      (!fallback || text.length > fallback.text.length)
    ) {
      return { text, selector: scored.selector };
    }
    if (!fallback || text.length > fallback.text.length) {
      fallback = { text, selector: scored.selector };
    }
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
