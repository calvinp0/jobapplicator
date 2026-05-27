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
