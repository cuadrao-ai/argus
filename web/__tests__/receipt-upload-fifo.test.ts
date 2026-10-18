import { expect, test } from "bun:test";
import type { ReceiptSummary } from "../lib/business-api";
import { ReceiptUploadQueue } from "../components/business-app/receipt-upload-queue";

const limits = { max_bytes: 20, media_types: ["text/plain", "application/pdf"] };
const file = (name: string, type = "text/plain", contents = "receipt") => new File([contents], name, { type });
const savedReceipt = (id: string): ReceiptSummary => ({
  id, channel: "web", filename: null, media_type: "text/plain", size_bytes: 7,
  received_at: "2026-10-09T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null,
});

test("several files added together upload in the order they were added", async () => {
  const order: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    order.push(candidate.name);
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("a.txt"), file("b.txt"), file("c.txt")], limits, "inbox");
  await queue.save("inbox", false);
  expect(order).toEqual(["a.txt", "b.txt", "c.txt"]);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["saved", "saved", "saved"]);
});

test("a file added while another uploads waits, then uploads behind it", async () => {
  const order: string[] = [];
  let releaseA!: (receipt: ReceiptSummary) => void;
  const queue = new ReceiptUploadQueue(async (candidate) => {
    order.push(candidate.name);
    if (candidate.name === "a.txt") await new Promise<ReceiptSummary>((resolve) => { releaseA = resolve; });
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("a.txt")], limits, "inbox");
  const running = queue.save("inbox", false);
  expect(queue.snapshot()[0].status).toBe("uploading");
  queue.add([file("b.txt")], limits, "inbox");
  expect(queue.snapshot().map((item) => [item.file.name, item.status])).toEqual([
    ["a.txt", "uploading"],
    ["b.txt", "queued"],
  ]);
  releaseA(savedReceipt("a.txt"));
  await running;
  expect(order).toEqual(["a.txt", "b.txt"]);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["saved", "saved"]);
});

test("a failure on the file in flight still uploads the file added behind it", async () => {
  const order: string[] = [];
  let failA!: (error: Error) => void;
  const queue = new ReceiptUploadQueue(async (candidate) => {
    order.push(candidate.name);
    if (candidate.name === "a.txt") await new Promise<ReceiptSummary>((_resolve, reject) => { failA = reject; });
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("a.txt")], limits, "inbox");
  const running = queue.save("inbox", false);
  queue.add([file("b.txt")], limits, "inbox");
  failA(new Error("offline"));
  await running;
  expect(order).toEqual(["a.txt", "b.txt"]);
  expect(queue.snapshot().map((item) => [item.file.name, item.status])).toEqual([
    ["a.txt", "failed"],
    ["b.txt", "saved"],
  ]);
});
