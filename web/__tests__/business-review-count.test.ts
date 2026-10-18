import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { countPorRevisar, countStillReading, countUnreadable, type ReviewCountItem } from "@/lib/business-review-count";

const review = (overrides: ReviewCountItem = {}): ReviewCountItem => ({ status: "review_ready", attention: null, ...overrides });

describe("countPorRevisar", () => {
  test("counts receipts waiting for a person, and nothing else", () => {
    const items: ReviewCountItem[] = [
      review(),
      review({ status: "needs_attention", attention: "duplicate" }),
      review({ status: "needs_attention", attention: "several_purchases" }),
      review({ status: "saved" }),
      review({ status: "needs_attention", attention: "unreadable" }),
      review({ status: "queued", read_pending: true }),
      review({ status: "preparing", activity: { state: "reading" } }),
      review({ status: "review_ready", activity: { state: "reading" } }),
      review({ status: "confirmed" }),
      review({ status: "dismissed" }),
      review({ email_original: true, status: "saved" }),
    ];
    assert.equal(countPorRevisar(items), 4);
    assert.equal(countStillReading(items), 3);
    assert.equal(countUnreadable(items), 1);
    assert.equal(countPorRevisar([]), 0);
  });

  test("a receipt that is still being read is not also unreadable", () => {
    const items = [review({ status: "queued", read_pending: true, attention: "unreadable" })];
    assert.equal(countPorRevisar(items), 0);
    assert.equal(countStillReading(items), 1);
    assert.equal(countUnreadable(items), 0);
  });
});
