import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import type { BusinessEmailDelivery, BusinessEmailPart } from "@/lib/business-email";
import { bandejaEmails, inboxCount, problemCount, readingCount } from "@/components/business-app/inbox-count";

const part = (overrides: Partial<BusinessEmailPart> = {}): BusinessEmailPart => ({ id: "1.2", filename: "factura.pdf", media_type: "application/pdf", state: "captured", document_id: "rcpt-1", error_code: null, ...overrides });
const email = (overrides: Partial<BusinessEmailDelivery> = {}): BusinessEmailDelivery => ({
  id: "email-1", state: "captured", received_at: "2026-10-13T17:14:00Z", updated_at: "2026-10-13T17:14:00Z", original_document_id: null, retryable: false,
  subject: "Factura", sender: "ventas@example.test", sent_at: null, error_code: null, parts: [part()], standing: null, ...overrides,
});

describe("where an email stands in the Bandeja is the server's word", () => {
  test("an email is a row only when the server gives it a standing, whatever its state and parts say", () => {
    const rows = bandejaEmails([
      email({ id: "rejected-no-row", state: "rejected", parts: [], standing: null }),
      email({ id: "captured-problem", state: "captured", standing: "no_receipt" }),
      email({ id: "reading", state: "captured", standing: "reading" }),
      email({ id: "saved", standing: null }),
    ]);
    assert.deepEqual(rows.map((row) => [row.delivery.id, row.standing]), [["captured-problem", "no_receipt"], ["reading", "reading"]]);
  });
});

describe("the Bandeja counts are the server's", () => {
  const activity = { reading_count: 3, unread_count: 0, presentation: "working" as const, pending_review_count: 40, needs_attention_count: 7, ready_to_review_count: 30 };

  test("past one page of rows, every number is the server's, emails and notes included", () => {
    assert.equal(inboxCount({ receiptActivity: activity }), 30);
    assert.equal(problemCount({ receiptActivity: activity }), 7);
    assert.equal(readingCount({ receiptActivity: activity }), 3);
  });

  test("without the server's answer a number is unknown, never 0", () => {
    for (const records of [{}, { receiptActivity: null }]) {
      assert.equal(inboxCount(records), null);
      assert.equal(problemCount(records), null);
      assert.equal(readingCount(records), null);
    }
  });
});
