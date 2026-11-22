import assert from "node:assert/strict";
import { test } from "bun:test";
import type { TFunction } from "i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { ReceiptUploadQueue, type ReceiptUpload } from "@/components/business-app/receipt-upload-queue";
import { UPLOAD_START_PERCENT, uploadBatchView, uploadRemovable, uploadStage, uploadSummaryText, uploadTimeLeftText } from "@/components/business-app/receipt-upload-view";

const limits = { max_bytes: 20, media_types: ["text/plain"] };
const file = (name: string) => new File(["receipt"], name, { type: "text/plain" });
const savedReceipt = (id: string, extra: Partial<ReceiptSummary> = {}): ReceiptSummary => ({
  id, channel: "web", filename: null, media_type: "text/plain", size_bytes: 7,
  received_at: "2026-11-22T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null, ...extra,
});
const limited = () => Object.assign(new Error("document_rate_limited"), { status: 429, retryAfterMs: 1 });
const settle = async (done: () => boolean) => { for (let turn = 0; turn < 200 && !done(); turn += 1) await new Promise((resolve) => setTimeout(resolve, 1)); };
/** The words a key would print, as the key and its values: the tests read which line was chosen, not its copy. */
const t = ((key: string, values?: Record<string, unknown>) => `${key}${values ? JSON.stringify(values) : ""}`) as unknown as TFunction;

type Attempt = { progress: (sent: number, total: number) => void; finish: (receipt: ReceiptSummary) => void; fail: (error: unknown) => void };
/** A queue whose every attempt is held open, so a test moves the bytes and ends the attempt by hand. */
function heldQueue() {
  const attempts: (Attempt & { name: string; key: string })[] = [];
  const queue = new ReceiptUploadQueue((candidate, _consent, key, _type, onProgress) => new Promise<ReceiptSummary>((resolve, reject) => {
    attempts.push({ name: candidate.name, key, progress: onProgress, finish: resolve, fail: reject });
  }), () => undefined);
  const start = (...names: string[]) => { queue.add(names.map(file), limits, "inbox"); void queue.save("inbox", false); };
  const stageOf = (name: string) => { const item = queue.snapshot().find((entry) => entry.file.name === name)!; return uploadStage(item, queue.retryWaiting(item.key)); };
  return { queue, attempts, start, stageOf };
}

test("a file walks waiting, sending from the start nudge, saving once every byte is sent, then saved", async () => {
  const { queue, attempts, start, stageOf } = heldQueue();
  start("a.txt", "b.txt");
  assert.deepEqual(stageOf("b.txt"), { kind: "waiting" });
  assert.deepEqual(stageOf("a.txt"), { kind: "sending", percent: UPLOAD_START_PERCENT }, "no byte yet still shows the start");
  attempts[0].progress(3, 100);
  assert.deepEqual(stageOf("a.txt"), { kind: "sending", percent: UPLOAD_START_PERCENT }, "the nudge is a floor, not an addition");
  attempts[0].progress(100, 100);
  assert.deepEqual(stageOf("a.txt"), { kind: "saving" });
  attempts[0].finish(savedReceipt("a"));
  await settle(() => attempts.length === 2);
  assert.deepEqual(stageOf("a.txt"), { kind: "saved", replayed: false });
  attempts[1].finish(savedReceipt("b", { replayed: true }));
  await settle(() => !queue.uploading);
  assert.deepEqual(stageOf("b.txt"), { kind: "saved", replayed: true });
});

test("the bar never moves back when the upload limit makes the same file send again", async () => {
  const { attempts, start, stageOf } = heldQueue();
  start("a.txt");
  attempts[0].progress(100, 100);
  attempts[0].fail(limited());
  await settle(() => attempts.length === 2);
  assert.equal(attempts[1].key, attempts[0].key, "the second send repeats the upload key");
  assert.deepEqual(stageOf("a.txt"), { kind: "sending", percent: 100 }, "nothing of the new attempt is sent, and the bar holds");
});

test("a lost connection stops the file at the share it had really sent, and a retry starts from nothing", async () => {
  const { queue, attempts, start, stageOf } = heldQueue();
  start("a.txt");
  attempts[0].progress(60, 100);
  attempts[0].fail(new TypeError("Failed to fetch"));
  await settle(() => !queue.uploading);
  assert.deepEqual(stageOf("a.txt"), { kind: "stopped", percent: 60, failure: "offline" });
  queue.retry(attempts[0].key);
  assert.deepEqual(stageOf("a.txt"), { kind: "sending", percent: UPLOAD_START_PERCENT });
});

test("the connection coming back retries every file it stopped, each with its own key, and no other failure", async () => {
  let online = false;
  const sent: { name: string; key: string }[] = [];
  const queue = new ReceiptUploadQueue(async (candidate, _consent, key) => {
    sent.push({ name: candidate.name, key });
    if (candidate.name === "refused.txt") throw Object.assign(new Error("invalid_document"), { status: 422 });
    if (!online) throw new TypeError("Failed to fetch");
    return savedReceipt(candidate.name);
  }, () => undefined);
  queue.add([file("a.txt"), file("refused.txt"), file("b.txt")], limits, "inbox");
  await queue.save("inbox", false);
  assert.deepEqual(queue.snapshot().map((item) => item.status), ["failed", "failed", "failed"]);
  online = true;
  queue.retryOffline();
  await settle(() => !queue.uploading);
  assert.deepEqual(queue.snapshot().map((item) => item.status), ["saved", "failed", "saved"]);
  const keysOf = (name: string) => sent.filter((attempt) => attempt.name === name).map((attempt) => attempt.key);
  assert.equal(new Set(keysOf("a.txt")).size, 1);
  assert.equal(new Set(keysOf("b.txt")).size, 1);
  assert.equal(keysOf("refused.txt").length, 1, "a refusal is not a lost connection");
  queue.retryOffline();
  assert.equal(queue.uploading, false, "with nothing stopped by the connection it does nothing");
});

test("a waiting, stopped or refused file can leave the list during a drain; the one being sent and a saved one cannot", async () => {
  const { queue, attempts, start } = heldQueue();
  queue.add([new File(["x".repeat(30)], "big.txt", { type: "text/plain" })], limits, "inbox");
  start("a.txt", "b.txt", "c.txt");
  const key = (name: string) => queue.snapshot().find((item) => item.file.name === name)!.key;
  const removable = (name: string) => { const item = queue.snapshot().find((entry) => entry.file.name === name)!; return uploadRemovable(uploadStage(item, queue.retryWaiting(item.key))); };
  assert.deepEqual(["big.txt", "a.txt", "b.txt"].map(removable), [true, false, true]);
  queue.remove(key("a.txt"));
  assert.ok(queue.snapshot().some((item) => item.file.name === "a.txt"), "the file being sent stays");
  queue.remove(key("b.txt"));
  queue.remove(key("big.txt"));
  attempts[0].finish(savedReceipt("a"));
  await settle(() => attempts.length === 2);
  assert.equal(attempts[1].name, "c.txt", "the removed file is never sent");
  assert.equal(removable("a.txt"), false, "a saved file has no X");
  attempts[1].fail(new TypeError("Failed to fetch"));
  await settle(() => !queue.uploading);
  assert.equal(removable("c.txt"), true);
  queue.remove(key("c.txt"));
  assert.deepEqual(queue.snapshot().map((item) => item.file.name), ["a.txt"]);
});

test("the panel and the chip read one count and differ only in their words", async () => {
  const { queue, attempts, start } = heldQueue();
  start("a.txt", "b.txt");
  const view = () => uploadBatchView(queue.snapshot(), queue.retryWaiting);
  assert.equal(view().busy, true);
  assert.equal(uploadSummaryText(t, view(), queue.progress, "panel"), 'business.intake.uploading_progress{"position":1,"total":2}');
  assert.equal(uploadSummaryText(t, view(), queue.progress, "chip"), 'business.intake.chip_uploading{"position":1,"total":2}');
  attempts[0].finish(savedReceipt("a"));
  await settle(() => attempts.length === 2);
  attempts[1].fail(new TypeError("Failed to fetch"));
  await settle(() => !queue.uploading);
  assert.equal(view().busy, false, "a stopped file that nobody retried is not busy");
  assert.equal(uploadSummaryText(t, view(), queue.progress, "panel"), 'business.intake.summary_saved{"count":1} · business.intake.summary_failed{"count":1}');
  assert.equal(uploadSummaryText(t, view(), queue.progress, "chip"), 'business.intake.chip_saved{"count":1} · business.intake.summary_failed{"count":1}');
});

test("the time left is said in round words, and not at all before there is an honest rate", () => {
  const batch = (share: number) => ({ share }) as ReturnType<typeof uploadBatchView>;
  assert.equal(uploadTimeLeftText(t, batch(0.2), null), null);
  assert.equal(uploadTimeLeftText(t, batch(0.2), 4), "business.intake.time_seconds");
  assert.equal(uploadTimeLeftText(t, batch(0.2), 10), "business.intake.time_seconds");
  assert.equal(uploadTimeLeftText(t, batch(0.2), 45), "business.intake.time_under_minute");
  assert.equal(uploadTimeLeftText(t, batch(0.2), 61), 'business.intake.row_minutes_left{"count":2}');
  assert.equal(uploadTimeLeftText(t, batch(1), null), "business.intake.time_finishing", "every byte is sent");
});

test("a refused file and a file deleted before have their own stage", () => {
  const base = { key: "k", file: file("a.txt"), documentType: null, grant: null, target: "inbox" as const };
  const rejected: ReceiptUpload = { ...base, status: "rejected", reason: "too_large" };
  const deleted: ReceiptUpload = { ...base, status: "saved", consent: false, receipt: savedReceipt("a", { deleted: { actor: { actor_id: "a", display_name: "Ana" }, at: "2026-11-20T10:00:00Z", purge_at: "2026-11-27T10:00:00Z", key: "d", previous_state: { state: "open", group: "attention" } } }) };
  assert.deepEqual(uploadStage(rejected, false), { kind: "rejected", reason: "too_large" });
  assert.deepEqual(uploadStage(deleted, false), { kind: "deleted" });
  assert.equal(uploadRemovable(uploadStage(deleted, false)), false);
});
