import { expect, test } from "bun:test";
import type { ReceiptSummary } from "../lib/business-api";
import { receiptFileAccept, receiptFileWithType, receiptFormatLabels } from "../components/business-app/receipt-file";
import { ReceiptUploadQueue, composerUploadDisposition } from "../components/business-app/receipt-upload-queue";

const limits = { max_bytes: 20, media_types: ["text/plain", "application/pdf"] };
const file = (name: string, type = "text/plain", contents = "receipt") => new File([contents], name, { type });
const savedReceipt = (id: string): ReceiptSummary => ({
  id, channel: "web", filename: null, media_type: "text/plain", size_bytes: 7,
  received_at: "2026-10-09T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null,
});

test("mixed selection rejects invalid files independently and uploads valid files serially", async () => {
  const called: string[] = [];
  const reported: string[] = [];
  let active = 0;
  const queue = new ReceiptUploadQueue(async (candidate) => {
    expect(active++).toBe(0);
    called.push(candidate.name);
    await Promise.resolve();
    active--;
    return savedReceipt(candidate.name);
  }, (receipt) => reported.push(receipt.id));
  queue.add([file("one.txt"), file("bad.exe", "application/octet-stream"), file("large.txt", "text/plain", "x".repeat(21)), file("photo.heic", "image/heic"), file("two.pdf", "")], limits, "inbox");
  expect(queue.snapshot().map((item) => item.status)).toEqual(["queued", "rejected", "rejected", "rejected", "queued"]);
  await queue.save("inbox", false);
  expect(called).toEqual(["one.txt", "two.pdf"]);
  expect(reported).toEqual(called);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["saved", "rejected", "rejected", "rejected", "saved"]);
  expect(queue.unfinished).toBe(false);
});

test("partial failure keeps the original file, key, and consent on retry without resending saved files", async () => {
  const calls: Array<{ name: string; key: string; consent: boolean }> = [];
  const received: ReceiptSummary[] = [];
  let fail = true;
  const queue = new ReceiptUploadQueue(async (candidate, consent, key) => {
    calls.push({ name: candidate.name, consent, key });
    if (candidate.name === "retry.txt" && fail) throw new Error("connection lost");
    return savedReceipt(key);
  }, (receipt) => received.push(receipt));
  queue.add([file("saved.txt"), file("retry.txt"), file("later.txt")], limits, "inbox");
  const original = queue.snapshot()[1];
  await queue.save("inbox", false);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["saved", "failed", "saved"]);
  expect(queue.unfinished).toBe(true);
  expect(received).toHaveLength(2);
  fail = false;
  await queue.save("inbox", true);
  expect(calls).toHaveLength(4);
  expect(calls[3]).toEqual(calls[1]);
  expect(queue.snapshot()[1].file).toBe(original.file);
  expect(queue.snapshot()[1].key).toBe(original.key);
  expect(received).toHaveLength(3);
  expect(queue.unfinished).toBe(false);
});

test("closing the subscriber cannot drop a running queue or permit duplicate saves", async () => {
  let finish!: (receipt: ReceiptSummary) => void;
  let calls = 0;
  const queue = new ReceiptUploadQueue(() => { calls++; return new Promise((resolve) => { finish = resolve; }); }, () => undefined);
  const stopListening = queue.subscribe(() => undefined);
  queue.add([file("one.txt")], limits, "inbox");
  const running = queue.save("inbox", false);
  expect(queue.snapshot()[0].status).toBe("uploading");
  stopListening();
  await queue.save("inbox", true);
  queue.clear("inbox");
  queue.remove(queue.snapshot()[0].key);
  expect(queue.snapshot()).toHaveLength(1);
  finish(savedReceipt("server-id"));
  await running;
  expect(calls).toBe(1);
  expect(queue.uploading).toBe(false);
  expect(queue.snapshot()[0].status).toBe("saved");
});

test("composer accepts one file without replacing the inbox queue, and cancelling selection changes nothing", async () => {
  const reported: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => savedReceipt(candidate.name), (_receipt, origin) => reported.push(origin.target));
  queue.add([file("inbox.txt")], limits, "inbox");
  queue.add([file("composer.txt"), file("ignored.txt")], limits, "composer");
  queue.add([], limits, "composer");
  expect(queue.snapshot().map((item) => item.file.name)).toEqual(["inbox.txt", "composer.txt"]);
  await queue.save("composer", false);
  expect(reported).toEqual(["composer"]);
  expect(queue.snapshot()[0].status).toBe("queued");
  queue.clear("composer");
  expect(queue.snapshot()).toHaveLength(1);
});

test("a composer completion cannot attach to a different conversation after its dialog closes", async () => {
  let finish!: (receipt: ReceiptSummary) => void;
  let currentConversation = "origin-chat";
  const attachments: string[] = [];
  const queue = new ReceiptUploadQueue(() => new Promise((resolve) => { finish = resolve; }), (receipt, origin) => {
    if (composerUploadDisposition(origin, { conversationId: currentConversation, intakeTarget: null }) !== "inbox") attachments.push(receipt.id);
  });
  queue.add([file("receipt.txt")], limits, "composer", currentConversation);
  const running = queue.save("composer", false);
  currentConversation = "another-chat";
  finish(savedReceipt("saved-in-inbox"));
  await running;
  expect(attachments).toEqual([]);
  const saved = queue.snapshot()[0];
  expect(saved.status).toBe("saved");
  expect(composerUploadDisposition(saved, { conversationId: "origin-chat", intakeTarget: "composer" })).toBe("attach_and_close");
  expect(composerUploadDisposition(saved, { conversationId: "origin-chat", intakeTarget: "inbox" })).toBe("attach");
  expect(composerUploadDisposition(saved, { conversationId: null, intakeTarget: "inbox" })).toBe("inbox");
});

test("untyped files take their type from the extension only when the server accepts it", () => {
  const server = { max_bytes: 20, media_types: ["application/pdf", "text/csv", "message/rfc822"] };
  expect(receiptFormatLabels(server)).toEqual(["PDF", "CSV", "EML"]);
  expect(receiptFileAccept(server)).toBe("application/pdf,.pdf,text/csv,.csv,message/rfc822,.eml");
  expect(receiptFileWithType(file("gastos.csv", ""), server).type).toBe("text/csv");
  expect(receiptFileWithType(file("mail.eml", ""), server).type).toBe("message/rfc822");
  expect(receiptFileWithType(file("notes.txt", ""), server).type).toBe("");
  expect(receiptFileWithType(file("typed.csv", "text/plain"), server).type.startsWith("text/plain")).toBe(true);
});

test("an XML e-invoice is offered by the picker and typed from its extension when the server accepts XML", () => {
  const server = { max_bytes: 20, media_types: ["application/pdf", "text/xml", "application/xml"] };
  expect(receiptFormatLabels(server)).toEqual(["PDF", "XML"]);
  expect(receiptFileAccept(server)).toBe("application/pdf,.pdf,text/xml,.xml,application/xml");
  expect(receiptFileWithType(file("factura-E320000001234.xml", ""), server).type).toBe("text/xml");
  const withoutXml = { max_bytes: 20, media_types: ["application/pdf"] };
  expect(receiptFileWithType(file("factura.xml", ""), withoutXml).type).toBe("");
});

test("a file picked twice is listed once, and a file added during a save joins the tail", async () => {
  const pending: Array<(receipt: ReceiptSummary) => void> = [];
  const queue = new ReceiptUploadQueue(() => new Promise((resolve) => { pending.push(resolve); }), () => undefined);
  const twice = file("recibo.txt");
  expect(queue.add([twice, twice, file("otro.txt")], limits, "inbox")).toBe(true);
  expect(queue.add([new File(["receipt"], "recibo.txt", { type: "text/plain", lastModified: twice.lastModified })], limits, "inbox")).toBe(true);
  expect(queue.snapshot().map((item) => item.file.name)).toEqual(["recibo.txt", "otro.txt"]);
  const running = queue.save("inbox", false);
  expect(queue.add([file("tarde.txt")], limits, "inbox")).toBe(true);
  expect(queue.snapshot().map((item) => [item.file.name, item.status])).toEqual([
    ["recibo.txt", "uploading"],
    ["otro.txt", "queued"],
    ["tarde.txt", "queued"],
  ]);
  const release = async (index: number, id: string) => {
    for (let turn = 0; pending.length <= index && turn < 20; turn += 1) await Promise.resolve();
    pending[index](savedReceipt(id));
    await Promise.resolve();
  };
  await release(0, "one");
  await release(1, "two");
  await release(2, "three");
  await running;
  expect(queue.snapshot().map((item) => item.status)).toEqual(["saved", "saved", "saved"]);
});

test("closing forgets saved and rejected rows and keeps unfinished ones", async () => {
  let fail = true;
  const queue = new ReceiptUploadQueue(async (candidate) => {
    if (candidate.name === "falla.txt" && fail) throw new Error("offline");
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("ok.txt"), file("falla.txt"), file("bad.exe", "application/octet-stream")], limits, "inbox");
  await queue.save("inbox", false);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["saved", "failed", "rejected"]);
  queue.add([file("pendiente.txt")], limits, "inbox");
  queue.clearSettled("inbox");
  expect(queue.snapshot().map((item) => [item.file.name, item.status])).toEqual([["falla.txt", "failed"], ["pendiente.txt", "queued"]]);
  fail = false;
  await queue.save("inbox", false);
  expect(queue.unfinished).toBe(false);
});

test("a venta upload tells the server the document type", async () => {
  const seen: Array<"recibo" | "venta" | null> = [];
  const queue = new ReceiptUploadQueue(async (_file, _consent, _key, documentType) => {
    seen.push(documentType);
    return savedReceipt("venta");
  }, () => undefined);
  queue.add([file("factura.pdf", "application/pdf")], limits, "inbox", null, "venta");
  await queue.save("inbox", false);
  expect(seen).toEqual(["venta"]);
});

test("a file added without a picked type uploads with none, so the server detects it", async () => {
  const seen: Array<"recibo" | "venta" | null> = [];
  const queue = new ReceiptUploadQueue(async (_file, _consent, _key, documentType) => {
    seen.push(documentType);
    return savedReceipt("venta");
  }, () => undefined);
  queue.add([file("factura.pdf", "application/pdf")], limits, "inbox", null);
  queue.add([file("compra.pdf", "application/pdf")], limits, "inbox", null, "recibo");
  await queue.save("inbox", false);
  expect(seen).toEqual([null, "recibo"]);
});

test("a failed venta is retried as a venta", async () => {
  const seen: Array<"recibo" | "venta" | null> = [];
  let fail = true;
  const queue = new ReceiptUploadQueue(async (_file, _consent, _key, documentType) => {
    seen.push(documentType);
    if (fail) throw new Error("connection lost");
    return savedReceipt("venta");
  }, () => undefined);
  queue.add([file("factura.pdf", "application/pdf")], limits, "inbox", null, "venta");
  await queue.save("inbox", false);
  fail = false;
  const [failed] = queue.snapshot();
  queue.retry(failed.key);
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(seen).toEqual(["venta", "venta"]);
  expect(queue.snapshot()[0].status).toBe("saved");
});

test("one batch mixes receipts and sales: each file uploads with the type it was added with", async () => {
  const seen: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate, _consent, _key, documentType) => {
    seen.push(`${candidate.name}:${documentType}`);
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("compra.pdf", "application/pdf")], limits, "inbox", null, "recibo");
  queue.add([file("venta.pdf", "application/pdf")], limits, "inbox", null, "venta");
  await queue.save("inbox", false);
  expect(seen).toEqual(["compra.pdf:recibo", "venta.pdf:venta"]);
});

test("a retry tapped while another file uploads waits its turn and then goes", async () => {
  let release: () => void = () => undefined;
  const calls: string[] = [];
  let failFirst = true;
  const queue = new ReceiptUploadQueue(async (candidate) => {
    calls.push(candidate.name);
    if (candidate.name === "uno.pdf" && failFirst) {
      failFirst = false;
      throw new Error("connection lost");
    }
    if (candidate.name === "dos.pdf") await new Promise<void>((resolve) => { release = resolve; });
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("uno.pdf", "application/pdf")], limits, "inbox");
  await queue.save("inbox", false);
  queue.add([file("dos.pdf", "application/pdf")], limits, "inbox");
  const dos = queue.snapshot().find((item) => item.file.name === "dos.pdf")!;
  const running = queue.save("inbox", false, new Set([dos.key]));
  await new Promise((resolve) => setTimeout(resolve, 0));
  const failed = queue.snapshot().find((item) => item.status === "failed");
  queue.retry(failed!.key);
  expect(queue.retryWaiting(failed!.key)).toBe(true);
  release();
  await running;
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(calls).toEqual(["uno.pdf", "dos.pdf", "uno.pdf"]);
  expect(queue.snapshot().every((item) => item.status === "saved")).toBe(true);
});

test("a server type rejection asks for another file rather than resending it", async () => {
  let calls = 0;
  const queue = new ReceiptUploadQueue(async () => {
    calls++;
    throw Object.assign(new Error("private detail must never render"), { status: 415 });
  }, () => undefined);
  queue.add([file("receipt.txt")], limits, "inbox");
  await queue.save("inbox", true);
  expect(queue.snapshot()[0]).toMatchObject({ status: "rejected", reason: "unsupported" });
  await queue.save("inbox", true);
  expect(calls).toBe(1);
});
