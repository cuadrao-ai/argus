import assert from "node:assert/strict";
import { test } from "bun:test";
import { addLocalEvidence, type LocalEvidence } from "@/components/business-app/transacciones/records-evidence-preview";

const limits = { max_bytes: 100, media_types: ["application/pdf", "image/png"] };
test("local evidence adds several files and deduplicates content rather than filenames", async () => {
  const first = await addLocalEvidence([], [new File(["first"], "receipt.pdf", { type: "application/pdf" })], limits);
  assert.equal(first.kind, "ready");
  if (first.kind !== "ready") return;
  const next = await addLocalEvidence(first.attachments, [new File(["first"], "renamed.pdf", { type: "application/pdf" }), new File(["second"], "receipt.pdf", { type: "application/pdf" }), new File(["third"], "photo.png", { type: "image/png" })], limits);
  assert.equal(next.kind, "ready");
  if (next.kind !== "ready") return;
  assert.equal(next.duplicates, 1);
  assert.deepEqual(next.attachments.map(({ file }) => file.name), ["receipt.pdf", "receipt.pdf", "photo.png"]);
  assert.equal(next.attachments[0].digest, "a7937b64b8caa58f03721bb6bacf5c78cb235febe0e70b1b84cd99541461a08e");
  assert.equal(new Set(next.attachments.map(({ digest }) => digest)).size, 3);
  const repeated = await addLocalEvidence(next.attachments, [new File(["first"], "receipt.pdf", { type: "application/pdf" })], limits);
  assert.equal(repeated.kind, "ready");
  if (repeated.kind !== "ready") return;
  assert.equal(repeated.attachments.length, 3); assert.equal(repeated.duplicates, 1);
});

test("invalid evidence selection leaves existing entries intact", async () => {
  const existing: LocalEvidence[] = [{ digest: "kept", file: new File(["kept"], "existing.pdf", { type: "application/pdf" }) }];
  const result = await addLocalEvidence(existing, [new File(["other"], "good.pdf", { type: "application/pdf" }), new File(["invalid"], "bad.exe", { type: "application/octet-stream" })], limits);
  assert.deepEqual(result, { kind: "invalid", reason: "unsupported", filename: "bad.exe" });
  assert.equal(existing[0].file.name, "existing.pdf"); assert.equal(existing.length, 1);
});


test.each([
  ["empty name", "", "application/pdf", "data", "invalid_name"],
  ["long name", "a".repeat(256), "application/pdf", "data", "invalid_name"],
  ["path separator", "bad/name.pdf", "application/pdf", "data", "invalid_name"],
  ["control character", "bad\u0000name.pdf", "application/pdf", "data", "invalid_name"],
  ["unsupported media", "file.exe", "application/octet-stream", "data", "unsupported"],
  ["empty file", "file.pdf", "application/pdf", "", "empty_file"],
  ["oversize file", "file.pdf", "application/pdf", "a".repeat(101), "too_large"],
])("rejects %s without accepting the valid files from the same selection", async (_label, name, type, body, reason) => {
  const existing: LocalEvidence[] = [{ digest: "kept", file: new File(["kept"], "existing.pdf", { type: "application/pdf" }) }];
  const result = await addLocalEvidence(existing, [new File(["new"], "new.pdf", { type: "application/pdf" }), new File([String(body)], String(name), { type: String(type) })], limits);
  assert.deepEqual(result, { kind: "invalid", reason, filename: name });
  assert.equal(existing.length, 1);
  assert.equal(existing[0].digest, "kept");
});
