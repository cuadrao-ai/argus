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
  const notes = new Set((await source.captures("", 50, "inbox")).items.map((note) => note.draft_id)).size;
  assert.equal(notes, 1, "the sample has one note awaiting review");
  assert.equal(page.activity?.ready_to_review_count, flagged("por_revisar") + notes);
  assert.equal(page.activity?.needs_attention_count, flagged("con_problema") + emails.filter((email) => email.standing === "no_receipt").length);
  assert.equal(page.activity?.reading_count, flagged("leyendo") + emails.filter((email) => email.standing === "reading").length);
  assert.equal(page.activity?.confirmed_count, all.filter((item) => item.status === "confirmed" && !item.email_original).length);
  assert.equal(page.activity?.dismissed_count, 0);
  assert.equal(page.activity?.bandeja_listo_count, page.items.filter((item) => item.bandeja_group?.group === "listo").length);
  assert.equal((page.activity?.bandeja_listo_count ?? 0) + (page.activity?.bandeja_attention_count ?? 0) + (page.activity?.reading_count ?? 0), page.activity?.pending_review_count, "the two tabs and what is still being read sum to every row");
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

test("every sample Listos row names what an approval sends, and an approval of many answers per item", async () => {
  const source = createFixtureBusinessDataSource();
  const listed = (await source.receiptPage!("inbox")).items.filter((item) => item.bandeja_group?.group === "listo");
  assert.ok(listed.length >= 4);
  assert.ok(listed.every((item) => item.bandeja_group?.draft_id && item.bandeja_group.version !== null));
  const items = listed.map((item) => ({ draft_id: item.bandeja_group!.draft_id!, version: item.bandeja_group!.version! }));
  const first = await source.approveListos(items, "key-1");
  assert.deepEqual(first.results.map((result) => result.outcome).sort(), ["applied", "applied", "applied", "outcome_unknown", "refused"]);
  const unsettled = first.results.filter((result) => result.outcome === "outcome_unknown").map(({ draft_id }) => items.find((item) => item.draft_id === draft_id)!);
  assert.deepEqual((await source.approveListos(unsettled, "key-1")).results.map((result) => result.outcome), ["applied"], "the same key settles it");
  const after = await source.receiptPage!("inbox");
  assert.equal(after.activity?.bandeja_listo_count, 1, "the refused receipt stays in Listos");
});

test("a receipt sent for reading is leyendo, and one queued that nothing reads is not", async () => {
  const source = createFixtureBusinessDataSource();
  const file = new File(["x"], "recibo.jpg", { type: "image/jpeg" });
  const saved = await source.uploadReceipt(file, false, "upload-saved");
  assert.deepEqual(saved.bandeja, { por_revisar: true, con_problema: false, leyendo: false });
  assert.deepEqual(saved.bandeja_group, { group: "attention", reason: "not_read", draft_id: null, version: null });
  assert.equal(saved.activity?.state, "saved_unread");
  const prepared = await source.prepareReceipt(saved.id);
  assert.deepEqual(prepared.bandeja, { por_revisar: false, con_problema: false, leyendo: true });
});
