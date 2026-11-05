import { expect, test } from "bun:test";
import type { ReceiptLimits, ReceiptSummary } from "../lib/business-api";
import { ReceiptUploadQueue, type IntakeTarget } from "../components/business-app/receipt-upload-queue";

const limits: ReceiptLimits = { max_bytes: 20, media_types: ["text/plain"] };
const file = (name: string) => new File(["receipt"], name, { type: "text/plain" });
const savedReceipt = (id: string): ReceiptSummary => ({
  id, channel: "web", filename: null, media_type: "text/plain", size_bytes: 7,
  received_at: "2026-10-09T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null,
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/** What the intake sheet does with a pick: add the files, then start the new ones. */
function choose(queue: ReceiptUploadQueue, files: File[], target: IntakeTarget) {
  const before = new Set(queue.snapshot().map((item) => item.key));
  queue.add(files, limits, target, target === "composer" ? "chat" : null);
  const fresh = queue.snapshot().filter((item) => !before.has(item.key) && item.status === "queued").map((item) => item.key);
  if (fresh.length) void queue.save(target, false, new Set(fresh));
}

function heldUploads() {
  const held = new Map<string, () => void>();
  const sent: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    sent.push(candidate.name);
    if (candidate.name.startsWith("held")) await new Promise<void>((resolve) => { held.set(candidate.name, resolve); });
    return savedReceipt(candidate.name);
  }, () => undefined);
  const status = () => Object.fromEntries(queue.snapshot().map((item) => [item.file.name, item.status]));
  return { queue, sent, status, release: (name: string) => held.get(name)?.() };
}

test("a file picked in Agregar while a composer upload runs uploads once that one ends", async () => {
  const { queue, sent, status, release } = heldUploads();
  choose(queue, [file("held-chat.txt")], "composer");
  await settle();
  choose(queue, [file("factura.txt")], "inbox");
  expect(status()["factura.txt"]).toBe("queued");
  release("held-chat.txt");
  await settle();
  expect(sent).toEqual(["held-chat.txt", "factura.txt"]);
  expect(status()).toEqual({ "held-chat.txt": "saved", "factura.txt": "saved" });
  expect(queue.uploading).toBe(false);
});

test("a later pick in Agregar does not leave an earlier waiting file behind", async () => {
  const { queue, sent, status, release } = heldUploads();
  choose(queue, [file("held-chat.txt")], "composer");
  await settle();
  choose(queue, [file("primera.txt")], "inbox");
  release("held-chat.txt");
  await settle();
  choose(queue, [file("segunda.txt")], "inbox");
  await settle();
  expect(sent).toEqual(["held-chat.txt", "primera.txt", "segunda.txt"]);
  expect(Object.values(status()).every((value) => value === "saved")).toBe(true);
});

test("a retry tapped in Agregar while a composer upload runs goes once that one ends", async () => {
  let failOnce = true;
  const held = new Map<string, () => void>();
  const sent: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    sent.push(candidate.name);
    if (candidate.name === "falla.txt" && failOnce) { failOnce = false; throw new Error("connection lost"); }
    if (candidate.name.startsWith("held")) await new Promise<void>((resolve) => { held.set(candidate.name, resolve); });
    return savedReceipt(candidate.name);
  }, () => undefined);
  choose(queue, [file("falla.txt")], "inbox");
  await settle();
  choose(queue, [file("held-chat.txt")], "composer");
  await settle();
  const failed = queue.snapshot().find((item) => item.status === "failed")!;
  queue.retry(failed.key);
  expect(queue.retryWaiting(failed.key)).toBe(true);
  held.get("held-chat.txt")?.();
  await settle();
  expect(sent).toEqual(["falla.txt", "held-chat.txt", "falla.txt"]);
  expect(queue.snapshot().every((item) => item.status === "saved")).toBe(true);
});

test("a failed file waits for its retry and is not resent by the next pick", async () => {
  let failOnce = true;
  const sent: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    sent.push(candidate.name);
    if (candidate.name === "falla.txt" && failOnce) { failOnce = false; throw new Error("connection lost"); }
    return savedReceipt(candidate.name);
  }, () => undefined);
  choose(queue, [file("falla.txt")], "inbox");
  await settle();
  choose(queue, [file("otra.txt")], "inbox");
  await settle();
  expect(sent).toEqual(["falla.txt", "otra.txt"]);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["failed", "saved"]);
});
