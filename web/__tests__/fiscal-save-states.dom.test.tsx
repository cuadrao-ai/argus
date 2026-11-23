import assert from "node:assert/strict";
import { test } from "bun:test";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { button, fill, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

type ReviewFiscal = BusinessDataSource["reviewFiscal"];

/** The fiscal pane over the sample's server, with each fiscal write answered by `answer`. */
async function fiscalPane(answer: (fixture: BusinessDataSource) => ReviewFiscal) {
  const page = await setup("fiscal", () => undefined, (fixture) => ({ reviewFiscal: answer(fixture) }));
  const pane = () => page.host.querySelector<HTMLElement>('[data-testid="fiscal-declaration"]')!;
  const row = () => page.row("itbis_cost");
  const save = () => page.action("itbis_cost", "Guardar");
  const cancel = () => page.action("itbis_cost", "Cancelar");
  await page.openRow("itbis_cost");
  await fill(page, '[data-testid="fiscal-declaration-itbis_cost"]', "12.00");
  return { ...page, pane, row, save, cancel };
}

const after = (first: Element, second: Element) => Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

test("while it saves, the button says so, Cancelar stays put but off, and every field is off", async () => {
  let finish: () => void = () => undefined;
  const view = await fiscalPane((fixture) => (id, version, review, key) => new Promise((resolve) => { finish = () => resolve(fixture.reviewFiscal(id, version, review, key)); }));
  try {
    await view.act(async () => view.save().click());
    const saving = view.pane().querySelector('[aria-busy="true"]');
    assert.ok(saving, "the save button is busy");
    assert.equal(saving, view.save());
    assert.ok(saving.querySelector("svg.animate-spin"), "with a spinner");
    assert.equal(view.cancel().disabled, true, "Cancelar stays, switched off");
    const controls = [...view.pane().querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-group] input, [data-group] select')];
    assert.equal(controls.length, 1);
    assert.deepEqual(controls.filter((control) => !control.disabled).map((control) => control.id || control.getAttribute("data-testid")), [], "every field is off");
    assert.equal(view.pane().querySelector("button[data-row-value]"), null, "other rows cannot start an edit during a save");
    await view.act(async () => finish());
  } finally { await view.close(); }
});

const READ_MODE = '[data-fact="itbis_cost"] button[data-row-value]';

test("a successful fiscal save returns its row to read mode with the new value and says nothing", async () => {
  const view = await fiscalPane((fixture) => fixture.reviewFiscal);
  try {
    await view.act(async () => view.save().click());
    await view.wait(() => Boolean(view.pane().querySelector(READ_MODE)));
    assert.equal(view.pane().querySelector(READ_MODE)?.textContent, "12.00");
    assert.equal(view.row().querySelector("input"), null, "the field closed");
    assert.equal(view.pane().querySelector('[role="status"], [data-testid="row-saved"]'), null, "no saved mark");
    assert.ok(!view.pane().textContent?.includes("Guardado"));
  } finally { await view.close(); }
});

test("a lost save shows below the buttons with its reference and Reintentar, which sends the same request", async () => {
  const keys: string[] = [];
  let lose = true;
  const view = await fiscalPane((fixture) => async (id, version, review, key) => {
    keys.push(key);
    if (lose) throw Object.assign(new Error("lost"), { status: 503 });
    return fixture.reviewFiscal(id, version, review, key);
  });
  try {
    await view.act(async () => view.save().click());
    await view.wait(() => Boolean(view.pane().querySelector('[data-testid="row-save-failed"]')));
    const failed = view.pane().querySelector('[data-testid="row-save-failed"]')!;
    assert.equal(failed.getAttribute("role"), "alert");
    assert.ok(failed.textContent?.includes("No se confirmó que los datos fiscales se guardaran."));
    assert.ok(failed.querySelector('[data-testid="error-reference"]'), "with its reference");
    assert.ok(after(view.cancel().parentElement!, failed), "below the buttons");
    assert.ok(view.row().contains(failed));
    assert.equal(view.cancel().disabled, true, "an edit whose outcome is unknown cannot be dropped");
    lose = false;
    await view.act(async () => button(failed, "Reintentar").click());
    await view.wait(() => Boolean(view.pane().querySelector(READ_MODE)));
    assert.equal(view.pane().querySelector('[data-testid="row-save-failed"]'), null, "the error leaves with the save that landed");
    assert.equal(keys.length, 2);
    assert.equal(keys[1], keys[0], "the retry is the same request");
  } finally { await view.close(); }
});
