import { describe, expect, test } from "bun:test";
import { countPorRevisar, countReviewBucket, reviewBucket } from "../lib/business-review-count";

const row = (status: string, attention: string | null = null, state: string | null = null) => ({
  status,
  attention,
  activity: state ? { state } : null,
});

describe("countPorRevisar", () => {
  test("counts receipts waiting for review and leaves reading and unreadable on other lines", () => {
    const items = [
      row("review_ready"),
      row("review_ready"),
      row("needs_attention", "unreadable"),
      row("needs_attention", "several_purchases"),
      row("review_ready", null, "reading"),
      row("confirmed"),
    ];
    expect(countPorRevisar(items)).toBe(2);
    expect(countReviewBucket(items, "reading")).toBe(1);
    expect(countReviewBucket(items, "unreadable")).toBe(2);
    expect(reviewBucket(row("saved"))).toBeNull();
    expect(countPorRevisar([])).toBe(0);
  });
});
