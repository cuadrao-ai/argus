import assert from "node:assert/strict";
import { test } from "bun:test";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";

// The preview answers in the server's shape, so its numbers equal the rows it flags (receipt_activity.py).
test("the sample's Bandeja counts equal the receipts it flags plus the emails that are rows", async () => {
  const source = createFixtureBusinessDataSource();
  const page = await source.receiptPage!("inbox");
  const emails = await source.emailDeliveries();
  const all = await source.receipts("all");
  const flagged = (bucket: "por_revisar" | "con_problema" | "leyendo") => page.items.filter((item) => item.bandeja?.[bucket]).length;
  assert.ok(page.items.every((item) => item.bandeja), "every receipt carries its flags");
  assert.equal(page.activity?.ready_to_review_count, flagged("por_revisar"));
  assert.equal(page.activity?.needs_attention_count, flagged("con_problema") + emails.filter((email) => email.standing === "no_receipt").length);
  assert.equal(page.activity?.reading_count, flagged("leyendo") + emails.filter((email) => email.standing === "reading").length);
  assert.equal(page.activity?.confirmed_count, all.filter((item) => item.status === "confirmed" && !item.email_original).length);
  assert.equal(page.activity?.dismissed_count, 0);
  assert.ok(all.filter((item) => item.email_original || item.status === "confirmed").every((item) => !item.bandeja?.por_revisar && !item.bandeja?.con_problema && !item.bandeja?.leyendo), "a closed receipt and an email original sit in no bucket");
});

test("the sample's emails say what they saved and why they brought nothing, by the server's rule", async () => {
  const emails = await createFixtureBusinessDataSource().emailDeliveries();
  const byId = Object.fromEntries(emails.map((email) => [email.id, email]));
  assert.deepEqual([byId["email-boletin"].standing, byId["email-boletin"].no_receipt_reason], ["no_receipt", "unsupported_media_type"], "the first refused file's code, past the email's own parts code");
  assert.deepEqual([byId["email-farmacia"].standing, byId["email-farmacia"].no_receipt_reason], ["no_receipt", "email_route_unavailable"]);
  assert.deepEqual([byId["email-ferreteria"].standing, byId["email-ferreteria"].saved_receipt_count, byId["email-ferreteria"].no_receipt_reason], [null, 1, null]);
  assert.deepEqual([byId["email-estacion"].standing, byId["email-estacion"].no_receipt_reason], ["reading", null]);
});

test("a receipt sent for reading is leyendo, and one queued that nothing reads is not", async () => {
  const source = createFixtureBusinessDataSource();
  const file = new File(["x"], "recibo.jpg", { type: "image/jpeg" });
  const saved = await source.uploadReceipt(file, false, "upload-saved");
  assert.deepEqual(saved.bandeja, { por_revisar: true, con_problema: false, leyendo: false });
  assert.equal(saved.activity?.state, "saved_unread");
  const prepared = await source.prepareReceipt(saved.id);
  assert.deepEqual(prepared.bandeja, { por_revisar: false, con_problema: false, leyendo: true });
});
