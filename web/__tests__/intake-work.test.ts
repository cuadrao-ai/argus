import assert from "node:assert/strict";
import { test } from "bun:test";
import { intakeWork } from "@/components/business-app/intake-work";
import { ReceiptUploadQueue } from "@/components/business-app/receipt-upload-queue";
import { TypedNoteQueue } from "@/components/business-app/typed-note-queue";

// One reader answers "is anything still being sent" for every intake queue, so a guard wired to it cannot miss a queue.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
const limits = { max_bytes: 1_000_000, media_types: ["image/png"] };
const neverUpload = async () => { throw new Error("unused"); };

test("a note still saving is unfinished work, and a confirmed save is not", async () => {
  const notes = new TypedNoteQueue(() => undefined);
  const work = intakeWork([new ReceiptUploadQueue(neverUpload, () => undefined), notes]);
  let release = () => undefined;
  const saving = notes.add({ grant: null, text: "Compré gasoil", documentType: "recibo" }, () => new Promise((resolve) => { release = () => resolve(undefined); }));
  assert.equal(work.unfinished(), true, "a save in flight keeps the work unfinished");
  release();
  await saving;
  assert.equal(work.unfinished(), false, "a confirmed save finishes it");
});

test("an unconfirmed note is unfinished until its retry lands; a refused note is finished", async () => {
  const notes = new TypedNoteQueue(() => undefined);
  const work = intakeWork([notes]);
  await notes.add({ grant: null, text: "Vendí cemento", documentType: "venta" }, async () => { throw new TypeError("Failed to fetch"); });
  assert.equal(notes.snapshot()[0].status, "uncertain");
  assert.equal(work.unfinished(), true, "an unconfirmed note waits for its retry");
  await notes.retry(notes.snapshot()[0].key, async () => undefined);
  await flush();
  assert.equal(work.unfinished(), false);

  await notes.add({ grant: null, text: "Compré gasoil", documentType: "recibo" }, async () => {
    throw Object.assign(new Error("refused"), { status: 422, code: "validation_failed" });
  });
  assert.equal(notes.snapshot()[0].status, "refused");
  assert.equal(work.unfinished(), false, "a refused note has nothing left to send");
});

test("a queued file is unfinished work with no notes at all", () => {
  const uploads = new ReceiptUploadQueue(neverUpload, () => undefined);
  const work = intakeWork([uploads, new TypedNoteQueue(() => undefined)]);
  assert.equal(work.unfinished(), false);
  uploads.add([new File(["recibo"], "factura.png", { type: "image/png" })], limits, "inbox");
  assert.equal(work.unfinished(), true);
});

test("a listener hears every queue change, and hears nothing once unsubscribed", async () => {
  const uploads = new ReceiptUploadQueue(neverUpload, () => undefined);
  const notes = new TypedNoteQueue(() => undefined);
  const work = intakeWork([uploads, notes]);
  let heard = 0;
  const stop = work.subscribe(() => { heard += 1; });
  uploads.add([new File(["recibo"], "factura.png", { type: "image/png" })], limits, "inbox");
  assert.equal(heard, 1, "the upload queue's change reached the listener");
  await notes.add({ grant: null, text: "Compré gasoil", documentType: "recibo" }, async () => undefined);
  assert.ok(heard >= 2, "the note queue's changes reached the listener");
  stop();
  const before = heard;
  uploads.add([new File(["otro"], "otra.png", { type: "image/png" })], limits, "inbox");
  assert.equal(heard, before, "an unsubscribed listener hears nothing");
});
