import assert from "node:assert/strict";
import { test } from "bun:test";
import { intakeWork, type IntakeQueue } from "@/components/business-app/intake-work";
import { ReceiptUploadQueue } from "@/components/business-app/receipt-upload-queue";

// One reader answers "is anything still being sent" for every intake queue, so a guard wired to it cannot miss a queue.
const limits = { max_bytes: 1_000_000, media_types: ["image/png"] };
const neverUpload = async () => { throw new Error("unused"); };

/** A second queue as the guard sees one: it says whether it has unfinished work and tells its listeners. */
function otherQueue() {
  const listeners = new Set<() => void>();
  const queue = {
    unfinished: false,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    set(unfinished: boolean) { queue.unfinished = unfinished; listeners.forEach((listener) => listener()); },
  };
  return queue satisfies IntakeQueue;
}

test("a queued file is unfinished work", () => {
  const uploads = new ReceiptUploadQueue(neverUpload, () => undefined);
  const work = intakeWork([uploads]);
  assert.equal(work.unfinished(), false);
  uploads.add([new File(["recibo"], "factura.png", { type: "image/png" })], limits, "inbox");
  assert.equal(work.unfinished(), true);
});

test("any one queue with unfinished work keeps the work unfinished", () => {
  const other = otherQueue();
  const work = intakeWork([new ReceiptUploadQueue(neverUpload, () => undefined), other]);
  assert.equal(work.unfinished(), false);
  other.set(true);
  assert.equal(work.unfinished(), true);
  other.set(false);
  assert.equal(work.unfinished(), false);
});

test("a listener hears every queue change, and hears nothing once unsubscribed", () => {
  const uploads = new ReceiptUploadQueue(neverUpload, () => undefined);
  const other = otherQueue();
  const work = intakeWork([uploads, other]);
  let heard = 0;
  const stop = work.subscribe(() => { heard += 1; });
  uploads.add([new File(["recibo"], "factura.png", { type: "image/png" })], limits, "inbox");
  assert.equal(heard, 1, "the upload queue's change reached the listener");
  other.set(true);
  assert.equal(heard, 2, "the other queue's change reached the listener");
  stop();
  uploads.add([new File(["otro"], "otra.png", { type: "image/png" })], limits, "inbox");
  assert.equal(heard, 2, "an unsubscribed listener hears nothing");
});
