import { test } from "bun:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { rebindAndPrepare } from "@/components/business-app/receipt-rebind";
import type { ReceiptDetail, ReceiptSummary } from "@/lib/business-api";

const detail = (status: ReceiptDetail["status"], error_code: string | null): ReceiptDetail =>
  ({ id: "r1", status, error_code, draft_id: null, version: 1, capabilities: ["read", "prepare", "approve"], accounts: [], missing_fields: [] }) as unknown as ReceiptDetail;

test("the bind action moves the binding, prepares again and shows each step's detail", async () => {
  const calls: string[] = [];
  const shown: string[] = [];
  const source = {
    rebindReceipt: async (id: string) => { calls.push(`rebind:${id}`); return detail("needs_attention", null); },
    prepareReceipt: async (id: string) => { calls.push(`prepare:${id}`); return { id } as unknown as ReceiptSummary; },
    receipt: async (id: string) => { calls.push(`receipt:${id}`); return detail("review_ready", null); },
  };
  await rebindAndPrepare(source, "r1", (next) => shown.push(`${next.status}`));
  assert.deepEqual(calls, ["rebind:r1", "prepare:r1", "receipt:r1"]);
  assert.deepEqual(shown, ["needs_attention", "review_ready"]);
});

test("a refused bind stops before preparing and surfaces the refusal", async () => {
  const calls: string[] = [];
  const source = {
    rebindReceipt: async () => { throw Object.assign(new Error("business_preparation_binding_live"), { status: 422, code: "business_preparation_binding_live" }); },
    prepareReceipt: async (id: string) => { calls.push(`prepare:${id}`); return { id } as unknown as ReceiptSummary; },
    receipt: async () => detail("review_ready", null),
  };
  await assert.rejects(rebindAndPrepare(source, "r1", () => undefined), { code: "business_preparation_binding_live" });
  assert.deepEqual(calls, []);
});

test("the review panel's bind button calls a handler the panel defines", () => {
  // bun tests have no DOM to click in; the frontend build (tsc) is the type gate.
  // This pins the wiring so a renamed or removed handler fails here as well.
  const panel = readFileSync(join(import.meta.dir, "../components/business-app/ReceiptReviewPanel.tsx"), "utf8");
  assert.match(panel, /const rebind = async \(\) => \{[\s\S]*await rebindAndPrepare\(source, detail\.id, show\);/);
  assert.match(panel, /data-testid="receipt-rebind"[^>]*onClick=\{\(\) => void rebind\(\)\}/);
  assert.match(panel, /t\("business\.review\.rebind_failed"/);
});
