import assert from "node:assert/strict";
import { test } from "bun:test";
import { registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

test("the fiscal form names ITBIS Facturado under ITBIS while the main card keeps ITBIS", async () => {
  const page = await setup("fiscal");
  try {
    const pane = page.host.querySelector('[data-testid="fiscal-declaration"]')!;
    const group = pane.querySelector('section[data-group="itbis"]')!;
    const heading = group.querySelector("h3")!;
    const field = group.querySelector<HTMLInputElement>('[data-testid="fiscal-declaration-itbis"]')!;
    assert.equal(heading.textContent, "ITBIS");
    assert.equal(page.row("itbis").firstElementChild?.textContent, "ITBIS");
    assert.ok(heading.compareDocumentPosition(field) & Node.DOCUMENT_POSITION_FOLLOWING);
    assert.equal(field.closest("li[data-field]")?.firstElementChild?.textContent, "ITBIS Facturado");
    assert.equal(field.getAttribute("aria-label"), "ITBIS Facturado en DOP (RD$)");
  } finally { await page.close(); }
});
