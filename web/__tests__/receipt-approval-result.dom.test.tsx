import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { button, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

describe("the receipt dossier on an open draft", () => {
  test("approving sends the suggestions shown, and the approved record keeps their icons", async () => {
    const sent: unknown[] = [];
    const page = await setup("fiscal", () => undefined, (fixture) => ({
      approveDraft: async (id, version, key, action, options) => { sent.push(options?.suggestions); return fixture.approveDraft(id, version, key, action, options); },
    }));
    try {
      await page.act(async () => button(page.host, "Aceptar").click());
      await page.wait(() => sent.length === 1 && !page.host.querySelector('[data-testid="receipt-facts-choices"] [aria-busy="true"]'));
      assert.deepEqual(sent, [{ category: { value: "02", source: "last_choice" }, payment_method: { value: "03", source: "last_choice" } }]);
      await page.wait(() => Boolean(page.host.querySelector('[data-approved="true"]') && !page.host.querySelector("[data-review-primary]")));
      assert.match(page.row("category").querySelector("[data-row-value]")?.textContent ?? "", /Gastos por trabajos/);
      assert.equal(page.row("category").querySelector('[role="img"]')?.getAttribute("aria-label"), "Última vez");
      assert.equal(page.row("payment_method").querySelector('[role="img"]')?.getAttribute("aria-label"), "Última vez");
    } finally { await page.close(); }
  });

  test("a refusal for a stale suggestion reloads the record instead of saving it", async () => {
    let calls = 0;
    const page = await setup("fiscal", () => undefined, () => ({
      approveDraft: async () => { calls += 1; throw Object.assign(new Error("suggestion_stale"), { status: 422, code: "suggestion_stale", requestId: "sample-suggestion_stale" }); },
    }));
    try {
      await page.act(async () => button(page.host, "Aceptar").click());
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="receipt-load-error"]')));
      assert.equal(calls, 1);
      assert.match(page.host.querySelector('[data-testid="receipt-load-error"]')?.textContent ?? "", /cambió/);
      await page.act(async () => button(page.host.querySelector('[data-testid="receipt-load-error"]')!, "Reintentar").click());
      await page.wait(() => Boolean(page.row("category")?.querySelector("[data-row-value]")));
      assert.match(page.row("category").textContent ?? "", /Gastos por trabajos/);
    } finally { await page.close(); }
  });
});
