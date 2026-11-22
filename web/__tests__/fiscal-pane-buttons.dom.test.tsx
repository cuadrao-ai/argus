import assert from "node:assert/strict";
import { test } from "bun:test";
import { primaryButtonClass, secondaryButtonClass } from "@/components/business-app/business-ui";
import { button, fill, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

async function fiscalPage() {
  const page = await setup("fiscal");
  const pane = () => page.host.querySelector<HTMLElement>('[data-testid="fiscal-declaration"]')!;
  const approve = () => button(page.host, "Aceptar");
  const reason = () => page.host.querySelector('[data-testid="approve-reason"]')?.textContent ?? null;
  const edit = () => fill(page, '[data-testid="fiscal-declaration-itbis_cost"]', "12.00");
  /** Whatever a person approving would see: an approval sent or a confirm step opened. */
  const approvalStarted = () => page.approvals() > 0 || Boolean(document.querySelector('[role="alertdialog"]'));
  return { ...page, pane, approve, reason, edit, approvalStarted };
}

test("Guardar is the pane's main button with the short label, and Cancelar is the outlined one", async () => {
  const page = await fiscalPage();
  try {
    const save = button(page.pane(), "Guardar");
    const cancel = button(page.pane(), "Cancelar");
    assert.equal(save.className, primaryButtonClass);
    assert.equal(cancel.className, secondaryButtonClass);
    assert.ok(save.compareDocumentPosition(cancel) & Node.DOCUMENT_POSITION_FOLLOWING, "Guardar comes first");
  } finally { await page.close(); }
});

test("an unsaved fiscal edit holds Aceptar with its reason until Cancelar", async () => {
  const page = await fiscalPage();
  try {
    assert.equal(page.approve().disabled, false, "nothing typed, nothing held");
    await page.edit();
    assert.equal(page.approve().disabled, true);
    assert.equal(page.reason(), "Guarda o cancela Más datos fiscales para aceptar.");
    assert.equal(page.approve().getAttribute("aria-describedby"), page.host.querySelector('[data-testid="approve-reason"]')!.id);
    await page.act(async () => button(page.pane(), "Cancelar").click());
    assert.equal(page.approve().disabled, false);
    assert.equal(page.reason(), null);
  } finally { await page.close(); }
});

test("an unsaved fiscal edit holds Aceptar until Guardar saves it", async () => {
  const page = await fiscalPage();
  try {
    await page.edit();
    assert.equal(page.approve().disabled, true);
    await page.act(async () => button(page.pane(), "Guardar").click());
    await page.wait(() => Boolean(page.pane().querySelector('[data-testid="row-saved"]')));
    assert.deepEqual(page.writes.map(({ kind }) => kind), ["fiscal"]);
    assert.equal(page.approve().disabled, false);
    assert.equal(page.reason(), null);
  } finally { await page.close(); }
});

test("the approve shortcut does nothing while a fiscal edit is unsaved, and works once it is dropped", async () => {
  const page = await fiscalPage();
  try {
    await page.edit();
    let ran = true;
    await page.act(async () => { ran = page.runShortcut("approve"); });
    assert.equal(ran, false, "the shortcut is not offered");
    assert.equal(page.approvalStarted(), false);
    await page.act(async () => button(page.pane(), "Cancelar").click());
    await page.act(async () => { ran = page.runShortcut("approve"); });
    assert.equal(ran, true);
    await page.wait(page.approvalStarted);
  } finally { await page.close(); }
});
