import { expect, test } from "bun:test";
import type { ReceiptSummary } from "../lib/business-api";
import { runQuietRetries } from "../lib/failure-screen";
import { ReceiptUploadQueue } from "../components/business-app/receipt-upload-queue";

const limits = { max_bytes: 20, media_types: ["text/plain"] };
const file = (name: string) => new File(["receipt"], name, { type: "text/plain" });
const savedReceipt = (id: string): ReceiptSummary => ({
  id, channel: "web", filename: null, media_type: "text/plain", size_bytes: 7,
  received_at: "2026-11-04T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null,
});
/** The error `uploadBusinessReceipt` rejects with on a 429, Retry-After already read. */
const waitASecond = () => Object.assign(new Error("document_rate_limited"), { status: 429, code: "document_rate_limited", retryAfterMs: 1 });
const refused = (status: number, code: string) => Object.assign(new Error(code), { status, code, retryAfterMs: null });

/** Every status each file passed through, in the order the screen saw them. */
function watchStatuses(queue: ReceiptUploadQueue) {
  const seen = new Map<string, string[]>();
  queue.subscribe(() => {
    for (const item of queue.snapshot()) {
      const trail = seen.get(item.key) ?? [];
      if (trail[trail.length - 1] !== item.status) seen.set(item.key, [...trail, item.status]);
    }
  });
  return seen;
}

test("a 429 then a 201 ends saved and the person never sees a failed state", async () => {
  const attempts: { name: string; key: string }[] = [];
  const queue = new ReceiptUploadQueue(async (candidate, _consent, key) => {
    attempts.push({ name: candidate.name, key });
    if (attempts.length === 1) throw waitASecond();
    return savedReceipt(candidate.name);
  }, () => undefined);
  const seen = watchStatuses(queue);
  queue.add([file("recibo.txt")], limits, "inbox");
  await queue.save("inbox", true);
  const [item] = queue.snapshot();
  expect(item.status).toBe("saved");
  expect(attempts.map((attempt) => attempt.name)).toEqual(["recibo.txt", "recibo.txt"]);
  expect(attempts[0].key).toBe(attempts[1].key);
  expect(seen.get(item.key)).toEqual(["queued", "uploading", "saved"]);
});

test("seventy files with every fourth answer a 429 all end saved, none dropped, in order", async () => {
  const names = Array.from({ length: 70 }, (_, index) => `recibo-${String(index + 1).padStart(2, "0")}.txt`);
  let attempt = 0;
  const saved: string[] = [];
  const queue = new ReceiptUploadQueue(async (candidate) => {
    attempt += 1;
    if (attempt % 4 === 0) throw waitASecond();
    saved.push(candidate.name);
    return savedReceipt(candidate.name);
  }, () => undefined);
  const seen = watchStatuses(queue);
  queue.add(names.map(file), limits, "inbox");
  await queue.save("inbox", true);
  expect(saved).toEqual(names);
  expect(queue.snapshot().map((item) => item.status)).toEqual(Array(70).fill("saved"));
  expect(queue.unfinished).toBe(false);
  expect([...seen.values()].every((trail) => !trail.includes("failed"))).toBe(true);
});

test("a refused file still shows as not uploaded, exactly as before", async () => {
  const answers = new Map([["type.txt", refused(415, "document_media_type_unsupported")], ["big.txt", refused(413, "document_too_large")]]);
  const queue = new ReceiptUploadQueue(async (candidate) => {
    const answer = answers.get(candidate.name);
    if (answer) throw answer;
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("type.txt"), file("big.txt"), file("fine.txt")], limits, "inbox");
  await queue.save("inbox", true);
  expect(queue.snapshot().map((item) => item.status)).toEqual(["rejected", "failed", "saved"]);
});

test("the workspace's quiet retries pass a 429 through to the queue with its wait", async () => {
  const clock = { now: () => 0, sleep: async () => { throw new Error("a 429 is not an outage to wait out here"); } };
  let attempts = 0;
  const queue = new ReceiptUploadQueue((candidate) => runQuietRetries(async () => {
    attempts += 1;
    if (attempts === 1) throw waitASecond();
    return savedReceipt(candidate.name);
  }, clock), () => undefined);
  queue.add([file("recibo.txt")], limits, "inbox");
  await queue.save("inbox", true);
  expect(queue.snapshot()[0].status).toBe("saved");
  expect(attempts).toBe(2);
});
