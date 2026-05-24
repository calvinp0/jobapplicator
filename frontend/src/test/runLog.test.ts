import { describe, expect, it } from "vitest";
import { sanitizeRunLogLines } from "../pages/RunDetailPage";

describe("sanitizeRunLogLines", () => {
  it("strips the jobapply: prefix for display", () => {
    const out = sanitizeRunLogLines([
      "jobapply: preparing tailoring inputs",
      "jobapply: launching Claude Code",
    ]);
    expect(out).toEqual([
      "preparing tailoring inputs",
      "launching Claude Code",
    ]);
  });

  it("drops blank and whitespace-only lines", () => {
    const out = sanitizeRunLogLines(["first", "", "   ", "second"]);
    expect(out).toEqual(["first", "second"]);
  });

  it("collapses adjacent duplicate lines", () => {
    const out = sanitizeRunLogLines([
      "jobapply: validating output files",
      "jobapply: validating output files",
      "jobapply: marking run failed",
    ]);
    expect(out).toEqual([
      "validating output files",
      "marking run failed",
    ]);
  });

  it("strips ANSI escape codes", () => {
    const out = sanitizeRunLogLines([
      "\x1b[31mclaude: reading job description\x1b[0m",
    ]);
    expect(out).toEqual(["claude: reading job description"]);
  });

  it("keeps the last N lines when over the cap", () => {
    const lines = Array.from({ length: 20 }, (_, i) => `line ${i}`);
    const out = sanitizeRunLogLines(lines, 5);
    expect(out).toEqual([
      "line 15",
      "line 16",
      "line 17",
      "line 18",
      "line 19",
    ]);
  });

  it("preserves the missing-output milestones intact for the failure UI", () => {
    const out = sanitizeRunLogLines([
      "jobapply: Claude Code process exited with code 0",
      "jobapply: validating output files",
      "jobapply: missing expected output file: output/tailored_resume.docx",
      "jobapply: marking run failed",
    ]);
    expect(out).toEqual([
      "Claude Code process exited with code 0",
      "validating output files",
      "missing expected output file: output/tailored_resume.docx",
      "marking run failed",
    ]);
  });
});
