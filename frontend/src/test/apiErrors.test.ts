import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import { extractApiDetail } from "../lib/api-errors";

const FALLBACK = "Something went wrong. Try again.";

describe("extractApiDetail", () => {
  it("returns a string detail from an ApiError response body", () => {
    const err = new ApiError("ignored", 400, { detail: "Run is not ready" });
    expect(extractApiDetail(err)).toBe("Run is not ready");
  });

  it("returns the msg of the first item when detail is a FastAPI validation array", () => {
    const err = new ApiError("ignored", 422, {
      detail: [
        { loc: ["body", "name"], msg: "value cannot be blank", type: "x" },
      ],
    });
    expect(extractApiDetail(err)).toBe("value cannot be blank");
  });

  it("returns the message of an object detail when present", () => {
    const err = new ApiError("ignored", 400, {
      detail: { message: "nope", code: 7 },
    });
    expect(extractApiDetail(err)).toBe("nope");
  });

  it("returns the friendly fallback when the response body has no detail", () => {
    const err = new ApiError("Request to /x failed with status 500", 500, null);
    expect(extractApiDetail(err)).toBe(FALLBACK);
  });

  it("returns the friendly fallback for an ApiError whose body lacks usable shape", () => {
    const err = new ApiError("ignored", 500, { other: "field" });
    expect(extractApiDetail(err)).toBe(FALLBACK);
  });

  it("returns the message of a plain Error", () => {
    expect(extractApiDetail(new Error("network unreachable"))).toBe(
      "network unreachable",
    );
  });

  it("strips the raw 'Request to ... failed with status N' message from a plain Error", () => {
    const err = new Error("Request to /runs/abc/import failed with status 400");
    expect(extractApiDetail(err)).toBe(FALLBACK);
  });

  it("returns the friendly fallback for unknown values", () => {
    expect(extractApiDetail(undefined)).toBe(FALLBACK);
    expect(extractApiDetail(null)).toBe(FALLBACK);
    expect(extractApiDetail(42)).toBe(FALLBACK);
    expect(extractApiDetail({})).toBe(FALLBACK);
  });

  it("returns a non-empty string value as-is", () => {
    expect(extractApiDetail("oh no")).toBe("oh no");
  });
});
