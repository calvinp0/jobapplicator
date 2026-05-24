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
