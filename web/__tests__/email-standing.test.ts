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

describe("the Bandeja counts with emails", () => {
  const inbox = [{ status: "review_ready" }, { status: "needs_attention", attention: "unreadable" }, { status: "queued", read_pending: true }];
  const emails = [email({ id: "a", state: "rejected", parts: [] }), email({ id: "b", state: "processing", parts: [] }), email({ id: "c" }), email({ id: "d", parts: [part({ repeat_of_upload: true })] })];

  test("an email that brought nothing is a problem, an email being read is reading, and Por revisar stays receipts and notes", () => {
    assert.equal(problemCount({ inbox, emails }), 2);
    assert.equal(readingCount({ inbox, emails }), 2);
    assert.equal(inboxCount({ inbox, emails, notes: [] }), 1);
  });

  test("a count is absent until both lists are known, never 0, and an email outage counts the receipts alone", () => {
    assert.equal(problemCount({ inbox, emails: null }), null);
    assert.equal(problemCount({ inbox: null, emails }), null);
    assert.equal(readingCount({ inbox, emails: null }), null);
    assert.equal(problemCount({ inbox, emails: null, emailsError: true }), 1);
  });
});
