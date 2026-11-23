import assert from "node:assert/strict";
import { test } from "bun:test";
import { button, fill, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

async function fiscalPage() {
  const page = await setup("fiscal");
  const pane = () => page.host.querySelector<HTMLElement>('[data-testid="fiscal-declaration"]')!;
  const approve = () => button(page.host, "Aceptar");
  const reason = () => page.host.querySelector('[data-testid="approve-reason"]')?.textContent ?? null;
  const edit = async () => {
    await page.openRow("itbis_cost");
    await fill(page, '[data-testid="fiscal-declaration-itbis_cost"]', "12.00");
  };
  /** Whatever a person approving would see: an approval sent or a confirm step opened. */
  const approvalStarted = () => page.approvals() > 0 || Boolean(document.querySelector('[role="alertdialog"]'));
  return { ...page, pane, approve, reason, edit, approvalStarted };
}

test("an open fiscal row has its own save and cancel actions", async () => {
  const page = await fiscalPage();
  try {
    await page.openRow("itbis_cost");
    const save = page.action("itbis_cost", "Guardar");
    const cancel = page.action("itbis_cost", "Cancelar");
    assert.equal(save.parentElement, cancel.parentElement);
    assert.ok(save.compareDocumentPosition(cancel) & Node.DOCUMENT_POSITION_FOLLOWING, "Guardar comes first");
  } finally { await page.close(); }
});

test("an unsaved fiscal edit holds Aceptar with its reason until Cancelar", async () => {
  const page = await fiscalPage();
  try {
    assert.equal(page.approve().disabled, false, "nothing typed, nothing held");
    await page.edit();
    assert.equal(page.approve().disabled, true);
    assert.equal(page.reason(), "Guarda o cancela Datos fiscales para aceptar.");
    assert.equal(page.approve().getAttribute("aria-describedby"), page.host.querySelector('[data-testid="approve-reason"]')!.id);
    await page.dismiss("itbis_cost");
    assert.equal(page.approve().disabled, false);
    assert.equal(page.reason(), null);
  } finally { await page.close(); }
});

test("an unsaved fiscal edit holds Aceptar until Guardar saves it", async () => {
  const page = await fiscalPage();
  try {
    await page.edit();
    assert.equal(page.approve().disabled, true);
    await page.check("itbis_cost");
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
    await page.dismiss("itbis_cost");
    await page.act(async () => { ran = page.runShortcut("approve"); });
    assert.equal(ran, true);
    await page.wait(page.approvalStarted);
  } finally { await page.close(); }
});
