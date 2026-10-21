import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { emailStanding, type BusinessEmailDelivery, type BusinessEmailPart } from "@/lib/business-email";
import { inboxCount, problemCount, readingCount } from "@/components/business-app/inbox-count";

const part = (overrides: Partial<BusinessEmailPart> = {}): BusinessEmailPart => ({ id: "1.2", filename: "factura.pdf", media_type: "application/pdf", state: "captured", document_id: "rcpt-1", error_code: null, ...overrides });
const email = (overrides: Partial<BusinessEmailDelivery> = {}): BusinessEmailDelivery => ({
  id: "email-1", state: "captured", received_at: "2026-10-13T17:14:00Z", updated_at: "2026-10-13T17:14:00Z", original_document_id: null, retryable: false,
  subject: "Factura", sender: "ventas@example.test", sent_at: null, error_code: null, parts: [part()], ...overrides,
});

describe("where an email stands in the Bandeja", () => {
  test("a file it saved is a receipt row of its own, so the email is no row", () => {
    assert.equal(emailStanding(email()), null);
    assert.equal(emailStanding(email({ state: "partial", parts: [part(), part({ id: "1.3", state: "rejected", document_id: null, error_code: "too_large" })] })), null);
  });

  test("still moving with nothing saved yet, it is being read", () => {
    assert.equal(emailStanding(email({ state: "received", parts: [] })), "reading");
    assert.equal(emailStanding(email({ state: "processing", parts: [part({ state: "pending", document_id: null })] })), "reading");
    assert.equal(emailStanding(email({ state: "partial", parts: [part({ state: "pending", document_id: null }), part({ id: "1.3", state: "rejected", document_id: null })] })), "reading");
    assert.equal(emailStanding(email({ state: "received", parts: [], waiting: { reason: "daily_budget", retry_at: "2026-10-15T00:00:00Z" } })), "reading");
  });

  test("finished with no receipt, it is a problem: rejected, every part rejected, or no attachment", () => {
    assert.equal(emailStanding(email({ state: "rejected", error_code: "email_route_unavailable", parts: [] })), "no_receipt");
    assert.equal(emailStanding(email({ state: "partial", parts: [part({ state: "rejected", document_id: null, error_code: "unsupported_media_type" })] })), "no_receipt");
    assert.equal(emailStanding(email({ state: "captured", parts: [] })), "no_receipt");
    assert.equal(emailStanding(email({ state: "partial", parts: [part({ repeat_of_delivery_id: "email-0" }), part({ id: "1.3", state: "rejected", document_id: null })] })), "no_receipt", "a rejected file beside a repeat still brought nothing new");
  });

  test("a repeat of a file already saved is not a problem and not a row", () => {
    assert.equal(emailStanding(email({ parts: [part({ repeat_of_delivery_id: "email-0" })] })), null);
    assert.equal(emailStanding(email({ parts: [part({ repeat_of_upload: true })] })), null);
  });
});

describe("the server's standing, when it sends one", () => {
  test("the server's word wins over the browser's rule, including an email whose own text was saved", () => {
    assert.equal(emailStanding(email({ standing: null, original_document_id: "rcpt-text", parts: [] })), null, "its text is already a receipt row");
    assert.equal(emailStanding(email({ standing: "reading" })), "reading");
    assert.equal(emailStanding(email({ standing: "no_receipt", state: "captured" })), "no_receipt");
  });

  test("an older server that sends no standing still gets the browser's rule", () => {
    assert.equal(emailStanding(email({ state: "rejected", parts: [] })), "no_receipt");
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
