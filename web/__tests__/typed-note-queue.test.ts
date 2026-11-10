import assert from "node:assert/strict";
import { test } from "bun:test";
import { TypedNoteQueue } from "@/components/business-app/typed-note-queue";

// The queue keeps one key per note and decides which notes a retry may send; the panel only renders what it holds.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a refused note is never resent, so Reintentar cannot loop on a note the server will refuse again", async () => {
  const sent: string[] = [];
  const queue = new TypedNoteQueue(() => undefined);
  await queue.add({ grant: null, text: "Compré gasoil", documentType: "recibo" }, async (_input, key) => {
    sent.push(key);
    throw Object.assign(new Error("refused"), { status: 422, code: "validation_failed" });
  });
  assert.equal(queue.snapshot()[0].status, "refused");
  await queue.retry(queue.snapshot()[0].key, async (_input, key) => { sent.push(key); return undefined; });
  await flush();
  assert.equal(sent.length, 1, "the retry sent nothing");
  assert.equal(queue.snapshot()[0].status, "refused");
});

test("a note reloads the Bandeja once, when its save is confirmed, and a retry repeats its key", async () => {
  let reloads = 0;
  const sent: string[] = [];
  const queue = new TypedNoteQueue(() => { reloads += 1; });
  await queue.add({ grant: "grant-own", text: "Vendí cemento", documentType: "venta" }, async (_input, key) => {
    sent.push(key);
    throw new TypeError("Failed to fetch");
  });
  assert.equal(queue.snapshot()[0].status, "uncertain");
  assert.equal(reloads, 0, "an unconfirmed note reloads nothing");
  await queue.retry(queue.snapshot()[0].key, async (input, key) => {
    sent.push(key);
    assert.deepEqual(input, { text: "Vendí cemento", document_type: "venta" });
    return undefined;
  });
  assert.deepEqual(sent, [sent[0], sent[0]], "the retry repeats the one key");
  assert.equal(queue.snapshot()[0].status, "saved");
  assert.equal(reloads, 1, "the confirmed save reloads once");
});

test("two notes typed one after the other never share a key", async () => {
  const queue = new TypedNoteQueue(() => undefined);
  const capture = async () => undefined;
  await Promise.all([
    queue.add({ grant: null, text: "Primera", documentType: "recibo" }, capture),
    queue.add({ grant: null, text: "Segunda", documentType: "recibo" }, capture),
  ]);
  const keys = queue.snapshot().map((note) => note.key);
  assert.equal(new Set(keys).size, 2);
});
