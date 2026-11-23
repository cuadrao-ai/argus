import assert from "node:assert/strict";
import { test } from "bun:test";
import { mount, registerReceiptReviewPage } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

async function openSample(receiptId: string) {
  const page = await mount();
  await page.open({ kind: "receipt", receiptId }, () => Boolean(page.host.querySelector('[data-testid="receipt-current-facts"]') && page.host.querySelector('[data-testid="fiscal-declaration"]')));
  const fiscal = page.host.querySelector<HTMLElement>('[data-testid="fiscal-declaration"]')!;
  return { page, fiscal, linked: [...fiscal.querySelectorAll<HTMLElement>("[data-inherited]")].map((row) => row.dataset.inherited) };
}

test("the sample's Datos fiscales shows a purchase's linked rows filled, and Montos says the Total adds up", async () => {
  const { page, fiscal, linked } = await openSample("rcpt-listo-imprenta");
  assert.deepEqual(linked, ["id_type", "paid_on", "services_amount", "itbis"]);
  assert.equal(fiscal.querySelector("[data-restore-inherited]"), null, "nothing is held apart");
  assert.match(fiscal.querySelector('[data-field="services_amount"]')?.textContent ?? "", /4,000\.00/);
  assert.match(page.host.querySelector('[data-fact="amount"]')?.textContent ?? "", /4,720\.00/);
  assert.ok(page.host.querySelector('[data-fact="amount"] [data-status="ok"]'), "the Total check");
  await page.act(async () => page.root.unmount());
});

test("the sample that holds Fecha de pago apart offers its way back", async () => {
  const { page, fiscal, linked } = await openSample("rcpt-listo-limpieza");
  assert.deepEqual(linked, ["id_type", "services_amount", "itbis"]);
  assert.deepEqual([...fiscal.querySelectorAll<HTMLElement>("[data-restore-inherited]")].map((button) => button.dataset.restoreInherited), ["paid_on"]);
  await page.act(async () => page.root.unmount());
});
