import assert from "node:assert/strict";
import { test } from "bun:test";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { receptionAction, receptionMatches, receptionRows, receptionSearchText, receptionDocumentTitle, listoItem } from "@/components/business-app/recepcion/reception-model";

async function sample() {
  const source = createFixtureBusinessDataSource({ chatAvailable: true });
  const receipts = await source.receipts("all");
  const emails = await source.emailDeliveries();
  return { receipts, emails, rows: receptionRows(receipts, [], emails) };
}

test("Todos keeps approved arrivals, which sit in neither group", async () => {
  const { rows } = await sample();
  const approved = rows.find(row => row.kind === "receipt" && row.receipt.status === "confirmed");
  assert.ok(approved);
  assert.equal(receptionMatches(approved, "all"), true);
  assert.equal(receptionMatches(approved, "attention"), false);
  assert.equal(receptionMatches(approved, "listos"), false);
  assert.equal(receptionAction(approved, true), "action_detail");
});

test("a reading email needs attention, as the counts have it, and a captured email does not duplicate its attachment", async () => {
  const { rows, emails } = await sample();
  const reading = rows.find(row => row.kind === "email" && row.email.standing === "reading");
  assert.ok(reading);
  assert.equal(receptionMatches(reading, "attention"), true);
  assert.equal(receptionMatches(reading, "listos"), false);
  for (const email of emails.filter(item => item.standing === null)) {
    assert.equal(rows.some(row => row.kind === "email" && row.id === email.id), false);
  }
});

test("Resolver needs a supported repair and the caller's prepare capability", async () => {
  const { rows } = await sample();
  const issue = rows.find(row => row.kind === "receipt" && row.receipt.enterable && row.receipt.bandeja?.con_problema);
  assert.ok(issue);
  assert.equal(receptionAction(issue, true), "action_resolve");
  assert.equal(receptionAction(issue, false), "action_detail");
  const noRetry = rows.find(row => row.kind === "email" && row.email.standing === "no_receipt" && !row.email.delivery.retryable);
  assert.ok(noRetry);
  assert.equal(receptionAction(noRetry, true), "action_detail");
});

test("an arrival keeps source identity searchable without making its amount primary", async () => {
  const { rows } = await sample();
  const emailReceipt = rows.find(row => row.kind === "receipt" && row.sender);
  assert.ok(emailReceipt?.kind === "receipt");
  assert.ok(receptionSearchText(emailReceipt).includes(emailReceipt.sender!));
  assert.deepEqual(rows.map(row => row.receivedAt), [...rows].map(row => row.receivedAt).sort().reverse());
});


test("independent attachments keep distinct rows while their original email stays context", async () => {
  const { receipts, emails } = await sample();
  const delivery = { ...emails[0], id: "delivery-three", standing: null };
  const documents = ["a", "b", "c"].map(id => ({ ...receipts[0], id, email_delivery_ids: [delivery.id], filename: `${id}.pdf`, media_type: "application/pdf" }));
  const original = { ...receipts[0], id: "email-original", email_original: true };
  const rows = receptionRows([...documents, original], [], [delivery]);
  assert.equal(rows.length, 3);
  assert.deepEqual(new Set(rows.map(row => row.id)), new Set(["a", "b", "c"]));
  assert(rows.every(row => row.kind === "receipt" && row.sender === delivery.sender));
});

test("document identity uses captured facts and delivery exceptions retain their subject", async () => {
  const { rows } = await sample();
  const labels = { untitled: "Documento", pending: "Recepción en proceso", exception: "Llegada sin documento", text: "Entrada de texto" };
  const receipt = rows.find(row => row.kind === "receipt"); assert.ok(receipt?.kind === "receipt");
  assert.equal(receptionDocumentTitle({ ...receipt, receipt: { ...receipt.receipt, merchant: null, filename: "original.pdf" } }, labels), "original.pdf");
  assert.equal(receptionDocumentTitle({ ...receipt, receipt: { ...receipt.receipt, attention: "unreadable", filename: "unreadable.jpg" } }, labels), "unreadable.jpg");
  for (const row of rows.filter(row => row.kind === "email")) assert.equal(receptionDocumentTitle(row, labels), row.email.delivery.subject?.trim() || (row.email.standing === "reading" ? labels.pending : labels.exception));
});


test("a typed note keeps its text, needs attention, and claims no file or sender", () => {
  const text = "Pagué 800 en efectivo por transporte.\nFue el viaje para recoger materiales.";
  const [note] = receptionRows([], [{ draft_id: "note-1", version: 1, revision: 1, source_id: "source-1", text, received_at: "2026-10-27T12:00:00Z", review_state: "open" }], []);
  const labels = { untitled: "Contenido", pending: "En proceso", exception: "Sin documento", text: "Nota" };
  assert.equal(receptionDocumentTitle(note, labels), text.split("\n")[0]);
  assert.equal(receptionAction(note, true), "action_note");
  assert.equal(receptionAction(note, false), "action_note");
  assert.equal(receptionMatches(note, "attention"), true);
  assert.equal(receptionMatches(note, "listos"), false);
  assert.equal(receptionMatches(note, "all"), true);
  assert.equal(listoItem(note), null);
  assert.equal("receipt" in note, false);
});

test("only a Listos row names what an approval sends", async () => {
  const { rows } = await sample();
  const named = rows.flatMap(row => { const item = listoItem(row); return item ? [row] : []; });
  assert.ok(named.length > 0);
  assert.ok(named.every(row => receptionMatches(row, "listos")));
  assert.ok(rows.filter(row => receptionMatches(row, "attention")).every(row => listoItem(row) === null));
});

test("a document caption remains context and does not create another inbox item", async () => {
  const { receipts } = await sample();
  const receipt = { ...receipts[0], source_text: "Materiales para el negocio" };
  const rows = receptionRows([receipt], [], []);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].kind, "receipt");
});


test("delivery exception uses its sole filename when the subject is absent", async () => {
  const { rows } = await sample();
  const row = rows.find(row => row.kind === "email"); assert.ok(row?.kind === "email");
  const labels = { untitled: "Contenido", pending: "En proceso", exception: "Correo recibido", text: "Nota" };
  const delivery = { ...row.email.delivery, subject: null, parts: [{ id: "unsupported", filename: "pedido.zip", media_type: "application/zip", state: "rejected" as const, document_id: null, error_code: "unsupported" }] };
  assert.equal(receptionDocumentTitle({ ...row, email: { ...row.email, delivery } }, labels), "pedido.zip");
  assert.equal(receptionDocumentTitle({ ...row, email: { standing: "no_receipt", delivery: { ...delivery, parts: [] } } }, labels), "Correo recibido");
});
