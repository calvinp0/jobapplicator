import { describe, it, expect, beforeAll } from "vitest";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

import {
  parseLinkedInJob,
  isLinkedInJobUrl,
  extractExternalJobId,
} from "../src/parser.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, "..", "fixtures");

async function loadFixtureDocument(name) {
  const html = await readFile(resolve(fixturesDir, name), "utf8");
  const dom = new JSDOM(html);
  return dom.window.document;
}

describe("isLinkedInJobUrl", () => {
  it("accepts canonical job URLs", () => {
    expect(
      isLinkedInJobUrl("https://www.linkedin.com/jobs/view/4012345678/"),
    ).toBe(true);
    expect(
      isLinkedInJobUrl(
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678",
      ),
    ).toBe(true);
  });

  it("rejects non-LinkedIn URLs", () => {
    expect(isLinkedInJobUrl("https://example.com/jobs/view/1")).toBe(false);
    expect(isLinkedInJobUrl("https://www.linkedin.com/feed/")).toBe(false);
    expect(isLinkedInJobUrl("")).toBe(false);
    expect(isLinkedInJobUrl(null)).toBe(false);
  });
});

describe("extractExternalJobId", () => {
  it("pulls the numeric id from /jobs/view/", () => {
    expect(
      extractExternalJobId("https://www.linkedin.com/jobs/view/4012345678/"),
    ).toBe("4012345678");
  });

  it("falls back to currentJobId query param", () => {
    expect(
      extractExternalJobId(
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4099887766",
      ),
    ).toBe("4099887766");
  });

  it("returns null when no id is present", () => {
    expect(extractExternalJobId("https://www.linkedin.com/jobs/")).toBeNull();
  });
});

describe("parseLinkedInJob — full fixture", () => {
  const url = "https://www.linkedin.com/jobs/view/4012345678/";
  let payload;

  beforeAll(async () => {
    const document = await loadFixtureDocument("linkedin_job_full.html");
    payload = parseLinkedInJob({ document, url });
  });

  it("returns the normalized capture shape", () => {
    expect(payload).toMatchObject({
      source_platform: "linkedin",
      capture_method: "browser_extension_current_page",
      external_url: url,
      external_job_id: "4012345678",
    });
  });

  it("extracts company, title, and location", () => {
    expect(payload.title).toBe("Senior Machine Learning Engineer");
    expect(payload.company).toBe("Example Corp");
    expect(payload.location).toBe("Berlin, Germany");
  });

  it("detects Easy Apply", () => {
    expect(payload.application_method).toBe("easy_apply");
  });

  it("extracts a description that includes role and requirements", () => {
    expect(payload.description_text).toContain("Senior Machine Learning Engineer");
    expect(payload.description_text).toContain("Requirements");
    expect(payload.description_text).toContain("PyTorch or TensorFlow");
  });

  it("captures raw_text scoped to the job container, not site chrome", () => {
    expect(payload.raw_text).toBeTruthy();
    expect(payload.raw_text).toContain("Senior Machine Learning Engineer");
    expect(payload.raw_text).not.toContain("Top nav stuff");
    expect(payload.raw_text).not.toContain("LinkedIn footer");
  });

  it("matches the keys the backend schema expects", () => {
    // Mirrors JobCaptureCreate (backend/app/schemas.py): the popup adds
    // captured_at at send time; everything else must be present here.
    const expectedKeys = [
      "source_platform",
      "capture_method",
      "external_url",
      "external_job_id",
      "company",
      "title",
      "location",
      "description_text",
      "application_method",
      "raw_text",
    ];
    for (const key of expectedKeys) {
      expect(payload).toHaveProperty(key);
    }
  });
});

describe("parseLinkedInJob — two-pane collections page", () => {
  // Reproduces the bug where the popup showed "(1) Top job picks for you"
  // as the title and missed company/description because the parser was
  // reading the sidebar list / document title instead of the active job
  // detail pane on /jobs/collections/recommended/?currentJobId=…
  const url =
    "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678";
  let payload;

  beforeAll(async () => {
    const document = await loadFixtureDocument("linkedin_job_collections.html");
    payload = parseLinkedInJob({ document, url });
  });

  it("extracts the active-pane title, not the sidebar h1 or document title", () => {
    expect(payload.title).toBe(
      "Software Development Engineer, AWS Agentic AI",
    );
    expect(payload.title).not.toContain("Top job picks for you");
    expect(payload.diagnostics.fallbacks_used.document_title).toBe(false);
    expect(payload.diagnostics.fallbacks_used.og_title).toBe(false);
  });

  it("extracts the active-pane company", () => {
    expect(payload.company).toBe("Amazon Web Services (AWS)");
  });

  it("parses location as the first non-noise segment before `·`", () => {
    expect(payload.location).toBe("Haifa, Haifa District, Israel");
    expect(payload.location).not.toMatch(/reposted/i);
    expect(payload.location).not.toMatch(/clicked apply/i);
  });

  it("extracts a description from .jobs-description__container", () => {
    expect(payload.description_text).toContain("AWS Agentic AI team");
    expect(payload.description_text).toContain("Basic qualifications");
    expect(payload.description_text.length).toBeLessThanOrEqual(20000);
  });

  it("records which selectors matched in diagnostics", () => {
    expect(payload.diagnostics.active_pane_selector).toBe(
      ".jobs-search__job-details--container",
    );
    expect(payload.diagnostics.matched_selectors.title).toBe(
      ".job-details-jobs-unified-top-card__job-title",
    );
    expect(payload.diagnostics.matched_selectors.company).toBe(
      ".job-details-jobs-unified-top-card__company-name a",
    );
    expect(payload.diagnostics.matched_selectors.location).toBe(
      ".job-details-jobs-unified-top-card__primary-description-container",
    );
    expect(payload.diagnostics.matched_selectors.description).toBe(
      ".jobs-description__container",
    );
  });

  it("scopes raw_text and page_text to the active pane, dropping the sidebar list", () => {
    expect(payload.raw_text).toContain("AWS Agentic AI");
    expect(payload.raw_text).not.toContain("Top job picks for you");
    expect(payload.raw_text).not.toContain("SomeOtherCo");
    expect(payload.page_text).toContain("AWS Agentic AI");
    expect(payload.page_text).not.toContain("Top job picks for you");
  });
});

describe("parseLinkedInJob — location noise filtering", () => {
  const url = "https://www.linkedin.com/jobs/view/4012345678/";

  function buildDoc(bodyHtml) {
    const dom = new JSDOM(
      `<!doctype html><html><body>${bodyHtml}</body></html>`,
    );
    return dom.window.document;
  }

  it("skips a leading 'Reposted' segment and returns the real location", () => {
    const document = buildDoc(`
      <section class="jobs-search__job-details--container">
        <h1 class="job-details-jobs-unified-top-card__job-title">X</h1>
        <div class="job-details-jobs-unified-top-card__primary-description-container">
          Reposted 5 days ago · Haifa, Haifa District, Israel · Over 10 people clicked apply
        </div>
      </section>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.location).toBe("Haifa, Haifa District, Israel");
  });

  it("skips 'Promoted' and '42 applicants' style noise", () => {
    const document = buildDoc(`
      <section class="jobs-search__job-details--container">
        <h1 class="job-details-jobs-unified-top-card__job-title">X</h1>
        <div class="job-details-jobs-unified-top-card__primary-description-container">
          Promoted · 42 applicants · Remote
        </div>
      </section>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.location).toBe("Remote");
  });

  it("returns null when every segment is noise", () => {
    const document = buildDoc(`
      <section class="jobs-search__job-details--container">
        <h1 class="job-details-jobs-unified-top-card__job-title">X</h1>
        <div class="job-details-jobs-unified-top-card__primary-description-container">
          Reposted 5 days ago · Over 10 people clicked apply
        </div>
      </section>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.location).toBeNull();
  });
});

describe("parseLinkedInJob — missing location", () => {
  it("returns null for location instead of throwing", async () => {
    const url = "https://www.linkedin.com/jobs/view/4099887766/";
    const document = await loadFixtureDocument("linkedin_job_no_location.html");
    const payload = parseLinkedInJob({ document, url });
    expect(payload.title).toBe("Data Scientist");
    expect(payload.company).toBe("TinyCo");
    expect(payload.location).toBeNull();
    expect(payload.application_method).toBe("external");
    expect(payload.description_text).toContain("future of analytics");
  });
});

describe("parseLinkedInJob — description selector fallback", () => {
  const url = "https://www.linkedin.com/jobs/view/4012345678/";

  function buildDoc(bodyHtml) {
    const dom = new JSDOM(
      `<!doctype html><html><body>${bodyHtml}</body></html>`,
    );
    return dom.window.document;
  }

  it("uses #job-details first when present", () => {
    const long = "Lorem ipsum ".repeat(20);
    const document = buildDoc(`
      <div id="job-details"><p>${long}</p></div>
      <div class="jobs-box__html-content"><p>SHOULD NOT WIN</p></div>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toContain("Lorem ipsum");
    expect(payload.description_text).not.toContain("SHOULD NOT WIN");
  });

  it("falls back to .jobs-box__html-content when #job-details is absent", () => {
    const long = "Responsibilities and requirements ".repeat(10);
    const document = buildDoc(`
      <div class="jobs-box__html-content"><p>${long}</p></div>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toContain("Responsibilities and requirements");
  });

  it("falls back to [data-test-job-description] as a last resort", () => {
    const long = "We are hiring talented engineers to build great products. ".repeat(4);
    const document = buildDoc(`
      <section data-test-job-description><p>${long}</p></section>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toContain("We are hiring");
  });

  it("prefers a longer match over a short skeleton match earlier in the list", () => {
    // #job-details exists but is empty / skeleton; the real text sits in a
    // later selector. We should still return the longer description.
    const long = "Detailed job description that easily exceeds the threshold. ".repeat(5);
    const document = buildDoc(`
      <div id="job-details"></div>
      <div class="jobs-description__content"><p>${long}</p></div>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toContain("Detailed job description");
  });

  it("still surfaces short descriptions when nothing clears the threshold", () => {
    const document = buildDoc(`
      <div id="job-details"><p>Tiny posting.</p></div>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toBe("Tiny posting.");
  });
});

describe("parseLinkedInJob — fallback fields and diagnostics", () => {
  const url =
    "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4415730750";

  function buildDoc(headHtml, bodyHtml) {
    const dom = new JSDOM(
      `<!doctype html><html><head>${headHtml}</head><body>${bodyHtml}</body></html>`,
    );
    return dom.window.document;
  }

  it("includes page_title and page_text on every parse", async () => {
    const document = await loadFixtureDocument("linkedin_job_full.html");
    const payload = parseLinkedInJob({
      document,
      url: "https://www.linkedin.com/jobs/view/4012345678/",
    });
    expect(payload.page_title).toContain("Senior Machine Learning Engineer");
    expect(payload.page_text).toBeTruthy();
    expect(payload.page_text.length).toBeGreaterThan(20);
    expect(payload.page_text.length).toBeLessThanOrEqual(20000);
  });

  it("bounds page_text to 20000 chars", () => {
    const huge = "x".repeat(50000);
    const document = buildDoc("<title>t</title>", `<p>${huge}</p>`);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.page_text.length).toBe(20000);
  });

  it("falls back to og:title when structured title is missing", () => {
    const document = buildDoc(
      `<title>Doc Title at Example Co | LinkedIn</title>
       <meta property="og:title" content="OG Captured Title" />`,
      `<div>no top card at all</div>`,
    );
    const payload = parseLinkedInJob({ document, url });
    expect(payload.title).toBe("OG Captured Title");
    expect(payload.diagnostics.selectors_matched.title).toBe(false);
    expect(payload.diagnostics.fallbacks_used.og_title).toBe(true);
  });

  it("falls back to document.title (stripping the LinkedIn suffix) when og:title is also missing", () => {
    const document = buildDoc(
      `<title>Senior ML Engineer at Example Co | LinkedIn</title>`,
      `<div>no top card at all</div>`,
    );
    const payload = parseLinkedInJob({ document, url });
    expect(payload.title).toBe("Senior ML Engineer at Example Co");
    expect(payload.diagnostics.fallbacks_used.document_title).toBe(true);
  });

  it("falls back to meta description when no description container resolves", () => {
    const document = buildDoc(
      `<title>t</title>
       <meta name="description" content="Meta-level job description text from LinkedIn." />`,
      `<div>only nav chrome here, no #job-details</div>`,
    );
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toContain("Meta-level job description");
    expect(payload.diagnostics.selectors_matched.description).toBe(false);
    expect(payload.diagnostics.fallbacks_used.meta_description).toBe(true);
  });

  it("reports url_has_current_job_id and external_job_id together", () => {
    const document = buildDoc("<title>t</title>", "<div>x</div>");
    const payload = parseLinkedInJob({ document, url });
    expect(payload.external_job_id).toBe("4415730750");
    expect(payload.diagnostics.url_has_current_job_id).toBe(true);
  });

  it("captures selected_text when the caller provides one", () => {
    const document = buildDoc("<title>t</title>", "<div>x</div>");
    const payload = parseLinkedInJob({
      document,
      url,
      selectedText: "  user selected this  ",
    });
    expect(payload.selected_text).toBe("user selected this");
    expect(payload.diagnostics.has_selected_text).toBe(true);
  });

  it("emits diagnostics with extractor=linkedin and selectors_matched flags", () => {
    const document = buildDoc("<title>t</title>", "<div>x</div>");
    const payload = parseLinkedInJob({ document, url });
    expect(payload.diagnostics.extractor).toBe("linkedin");
    expect(payload.diagnostics.selectors_matched).toEqual({
      title: false,
      company: false,
      location: false,
      description: false,
    });
  });
});

describe("parseLinkedInJob — LinkedIn SDUI layout", () => {
  const url = "https://www.linkedin.com/jobs/view/4012345678/";
  let payload;
  let document;

  beforeAll(async () => {
    document = await loadFixtureDocument("linkedin_job_sdui.html");
    payload = parseLinkedInJob({ document, url });
  });

  it("extracts the description from the SDUI about-the-job region", () => {
    expect(payload.description_text).toContain("Description");
    expect(payload.description_text).toContain("About the AI Division");
    expect(payload.description_text).toContain("About the Role");
    expect(payload.description_text).toContain("Responsibilities");
    expect(payload.description_text).toContain("Requirements");
    expect(payload.description_text).toContain("Qualifications");
    expect(payload.description_text).toContain("PyTorch or TensorFlow");
    expect(payload.diagnostics.selectors_matched.description).toBe(true);
  });

  it("anchors on a stable attribute selector, never a hashed atomic class", () => {
    const selector = payload.diagnostics.matched_selectors.description;
    expect(selector).toMatch(/data-sdui-component|data-testid/);
    // The hashed wrappers from the page must never appear as the selector.
    expect(selector).not.toMatch(/_107b9f77|_437b6ccc|aaf70612/);
  });

  it("strips control affordances and never captures Apply/Save/Show more", () => {
    const lines = payload.description_text.split("\n").map((l) => l.trim());
    for (const noise of [
      "Apply",
      "Save",
      "Show more",
      "Back to careers",
      "Premium",
    ]) {
      expect(lines).not.toContain(noise);
    }
  });

  it("excludes the recommendations rail and premium upsell", () => {
    expect(payload.description_text).not.toMatch(/People also viewed/i);
    expect(payload.description_text).not.toMatch(/Try Premium/i);
    expect(payload.description_text).not.toMatch(/See more jobs/i);
  });

  it("still resolves a title via fallbacks on the SDUI layout", () => {
    expect(payload.title).toBe("Senior AI Engineer");
  });

  it("does not depend on hashed class names (extraction survives class removal)", async () => {
    // Re-parse the same DOM with EVERY class attribute stripped. If extraction
    // leaned on hashed classes this would now miss; it must still resolve the
    // description from the SDUI data attributes alone.
    const stripped = await loadFixtureDocument("linkedin_job_sdui.html");
    stripped.querySelectorAll("*").forEach((el) => el.removeAttribute("class"));
    const reparsed = parseLinkedInJob({ document: stripped, url });
    expect(reparsed.description_text).toContain("Requirements");
    expect(reparsed.description_text).toContain("PyTorch or TensorFlow");
    expect(reparsed.diagnostics.matched_selectors.description).toMatch(
      /data-sdui-component|data-testid/,
    );
  });

  it("still only runs for LinkedIn URLs — rejects an SDUI DOM on a non-LinkedIn URL", () => {
    expect(() =>
      parseLinkedInJob({ document, url: "https://example.com/jobs/view/1" }),
    ).toThrow(/Not a LinkedIn job page/);
  });
});

describe("parseLinkedInJob — SDUI scoring fallback (no known selectors)", () => {
  const url = "https://www.linkedin.com/jobs/view/4012345678/";

  function buildDoc(bodyHtml) {
    const dom = new JSDOM(
      `<!doctype html><html><body>${bodyHtml}</body></html>`,
    );
    return dom.window.document;
  }

  it("scores the description container over nav/recommendations/upsell", () => {
    // No #job-details, no .jobs-description__*, no data-sdui-component, and no
    // data-testid — only job headings inside a div with hashed classes. The
    // scoring fallback must still find it and exclude the chrome around it.
    const document = buildDoc(`
      <nav class="_nav123"><a>Home</a><a>Jobs</a><button>Premium</button></nav>
      <div class="_aaa111 _bbb222">
        <h2>About the Role</h2>
        <p>You will design distributed training pipelines and partner with
           researchers to take experiments from notebook to scaled run.</p>
        <h2>Responsibilities</h2>
        <ul>
          <li>Build and operate large-scale training infrastructure.</li>
          <li>Improve throughput and reliability of training runs.</li>
        </ul>
        <h2>Requirements</h2>
        <p>Strong experience with PyTorch or TensorFlow and distributed systems.</p>
      </div>
      <div class="premium-upsell premium">
        <p>Try Premium to see how you compare to other applicants.</p>
      </div>
      <aside class="recommended">
        <h2>People also viewed</h2>
        <a href="/jobs/view/2/">More jobs for you</a>
      </aside>
    `);
    const payload = parseLinkedInJob({ document, url });
    expect(payload.description_text).toContain("Responsibilities");
    expect(payload.description_text).toContain("PyTorch or TensorFlow");
    expect(payload.description_text).not.toMatch(/Try Premium/i);
    expect(payload.description_text).not.toMatch(/People also viewed/i);
    expect(payload.diagnostics.selectors_matched.description).toBe(true);
  });
});

describe("parseLinkedInJob — non-LinkedIn page rejection", () => {
  it("throws when the URL is not a LinkedIn job page", async () => {
    const document = await loadFixtureDocument("non_linkedin_page.html");
    expect(() =>
      parseLinkedInJob({ document, url: "https://example.com/random" }),
    ).toThrow(/Not a LinkedIn job page/);
  });

  it("throws even for linkedin.com URLs that are not /jobs/", async () => {
    const document = await loadFixtureDocument("non_linkedin_page.html");
    expect(() =>
      parseLinkedInJob({
        document,
        url: "https://www.linkedin.com/feed/",
      }),
    ).toThrow(/Not a LinkedIn job page/);
  });
});
