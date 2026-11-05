import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "bun:test";
import type { ListoApproval, ListoItem } from "@/lib/business-api";
import { LISTO_LIMIT, listoBatches, replayBatches, runListoBatches, type ListoTarget } from "@/components/business-app/recepcion/reception-approval";
import { BANDEJA_REASON_KEY } from "@/components/business-app/recepcion/reception-status";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";

const target = (index: number): ListoTarget => ({ draft_id: `draft-${index}`, version: index, rowId: `receipt:${index}`, title: `Recibo ${index}` });
const keys = () => { let next = 0; return () => `key-${++next}`; };

test("a selection past the route's limit goes as several requests, each with its own key", async () => {
  const targets = Array.from({ length: LISTO_LIMIT * 2 + 1 }, (_, index) => target(index));
  const sent: { size: number; key: string }[] = [];
  const run = await runListoBatches(async (items, key) => { sent.push({ size: items.length, key }); return { results: items.map(item => ({ draft_id: item.draft_id, outcome: "applied" as const })) }; }, listoBatches(targets, keys()));
  assert.deepEqual(sent, [{ size: 50, key: "key-1" }, { size: 50, key: "key-2" }, { size: 1, key: "key-3" }]);
  assert.equal(run.applied.length, 101);
  assert.deepEqual(run.failed, []);
});

test("a failed request leaves the next one to run, and its rows can be replayed under the same key", async () => {
  const targets = Array.from({ length: LISTO_LIMIT + 1 }, (_, index) => target(index));
  const send = async (items: readonly ListoItem[], key: string): Promise<{ results: ListoApproval[] }> => {
    if (key === "key-1") throw Object.assign(new Error("gateway"), { status: 502, requestId: "request-1234" });
    return { results: items.map(item => ({ draft_id: item.draft_id, outcome: "applied" })) };
  };
  const run = await runListoBatches(send, listoBatches(targets, keys()));
  assert.deepEqual(run.applied, ["receipt:50"]);
  assert.equal(run.failed.length, 50);
  assert.ok(run.failed.every(failure => failure.kind === "unknown" && failure.key === "key-1" && failure.reference === "request-1234"));
  assert.deepEqual(replayBatches(run.failed).map(batch => [batch.key, batch.targets.length]), [["key-1", 50]]);
});

test("only an unsettled item is replayed; a refusal waits for a person", async () => {
  const run = await runListoBatches(async items => ({ results: [{ draft_id: items[0].draft_id, outcome: "refused", code: "stale_version" }, { draft_id: items[1].draft_id, outcome: "outcome_unknown", code: "business_recording_unsettled" }] }), listoBatches([target(1), target(2)], keys()));
  assert.deepEqual(run.failed.map(failure => [failure.target.rowId, failure.kind, failure.code]), [["receipt:1", "refused", "stale_version"], ["receipt:2", "unknown", "business_recording_unsettled"]]);
  assert.deepEqual(replayBatches(run.failed).flatMap(batch => batch.targets.map(item => item.rowId)), ["receipt:2"]);
});

test("every reason the contract names has a word in both languages", () => {
  const openapi = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8");
  const block = openapi.slice(openapi.indexOf("BandejaGroup:"), openapi.indexOf("draft_id:", openapi.indexOf("BandejaGroup:")));
  const reasons = [...block.matchAll(/^\s+- ([a-z_]+)$/gm)].map(match => match[1]).filter(reason => !["listo", "attention", "string"].includes(reason));
  assert.ok(reasons.includes("sin_comprobante"));
  const word = (catalog: unknown, key: string) => key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog);
  // `reading` is its own tag, and `other` says nothing a reason line could add.
  for (const reason of reasons.filter(reason => reason !== "reading" && reason !== "other")) {
    const key = BANDEJA_REASON_KEY[reason];
    assert.ok(key, `no word for ${reason}`);
    assert.equal(typeof word(spanish, key), "string", `${key} in Spanish`);
    assert.equal(typeof word(english, key), "string", `${key} in English`);
  }
});
