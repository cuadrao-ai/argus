import assert from "node:assert/strict";
import { test } from "bun:test";
import { registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

test("the fiscal form names ITBIS Facturado under ITBIS while the main card keeps ITBIS", async () => {
  const page = await setup("fiscal");
  try {
    const pane = page.host.querySelector<HTMLDetailsElement>('[data-testid="fiscal-declaration"]')!;
    assert.equal(pane.querySelector("summary")?.textContent, "Más datos fiscales");
    await page.act(async () => pane.querySelector("summary")!.click());
    assert.equal(pane.open, true);
    const group = pane.querySelector('[data-group="itbis"]')!;
    const heading = group.querySelector("h4")!;
    const field = group.querySelector<HTMLInputElement>('[data-testid="fiscal-declaration-itbis"]')!;
    assert.equal(heading.textContent, "ITBIS");
    assert.equal(page.row("itbis").querySelector("dt")?.textContent, "ITBIS");
    assert.ok(heading.compareDocumentPosition(field) & Node.DOCUMENT_POSITION_FOLLOWING);
    assert.equal(field.closest("label")?.querySelector("span")?.textContent, "ITBIS Facturado");
    assert.equal(field.getAttribute("aria-label"), "ITBIS Facturado en DOP (RD$)");
  } finally { await page.close(); }
});
