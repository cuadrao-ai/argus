import assert from "node:assert/strict";
import { test } from "bun:test";
import { fill, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

/** The Total's warning, as its status slot says it; null when the Total carries none. */
const totalWarning = (page: { row: (name: string) => HTMLElement }) => {
  const status = page.row("amount").querySelector('[data-testid="row-status-amount"][data-status="warn"]');
  return status ? status.getAttribute("aria-label") : null;
};

for (const form of ["606", "607"] as const) test(`header currency warns before saving a non-DOP ${form}`, async () => {
  const page = await setup("fiscal", (dossier) => { dossier.dgii = { ...dossier.dgii, form }; });
  const currencyRow = () => page.host.querySelector<HTMLElement>('li[data-fact="currency"]');
  try {
    const heading = page.host.querySelector<HTMLButtonElement>('[data-testid="montos-currency"]')!;
    assert.equal(heading.textContent, "DOP");
    assert.equal(currencyRow(), null, "the currency row opens from the heading");
    await page.act(async () => heading.click());
    const selector = 'li[data-fact="currency"] [data-testid="edit-currency"] select';
    const select = page.host.querySelector<HTMLSelectElement>(selector)!;
    assert.deepEqual([...select.options].map((option) => option.value), ["", "DOP", "USD", "EUR"]);
    for (const currency of ["USD", "EUR"]) {
      await fill(page, selector, currency, HTMLSelectElement);
      assert.equal(currencyRow()!.querySelector('[role="status"]')?.textContent, `En ${currency} este documento no entra al ${form} (la DGII pide pesos).`);
      assert.equal(page.writes.length, 0);
    }
    await fill(page, selector, "DOP", HTMLSelectElement);
    assert.equal(currencyRow()!.querySelector('[role="status"]'), null);
    await page.act(async () => currencyRow()!.querySelector<HTMLButtonElement>('button[aria-label="Cancelar · Moneda"]')!.click());
    assert.equal(currencyRow(), null);
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});

test("amount edit and cancel keep the number box and the two action slots", async () => {
  const page = await setup();
  try {
    const value = () => page.row("amount").querySelector<HTMLElement>("button[data-row-value]");
    assert.ok(value()?.classList.contains("cuadrao-amount"));
    assert.ok(page.row("amount").querySelector('button[aria-label="Editar detalles · Total"]'));
    await page.openRow("amount");
    const field = page.row("amount").querySelector<HTMLElement>("[data-row-open]")!;
    const input = field.querySelector<HTMLInputElement>('[data-testid="dossier-review-amount"]')!;
    assert.ok(input.classList.contains("text-right"));
    assert.equal(field.querySelector("select"), null, "the currency stays in the heading");
    assert.equal(field.textContent?.includes("RD$"), false, "the number carries no symbol");
    assert.deepEqual([...field.nextElementSibling!.querySelectorAll("button")].map((button) => button.getAttribute("aria-label")), ["Guardar · Total", "Cancelar · Total"]);
    await page.dismiss("amount");
    assert.equal(page.row("amount").querySelector("[data-row-open]"), null);
    assert.ok(value());
  } finally { await page.close(); }
});

test("the difference follows the current server preview while typing and drops cancelled replies", async () => {
  const requests: { input: unknown; resolve: (value: import("@/lib/business-api").BusinessAmountsPreview) => void }[] = [];
  const page = await setup("fiscal", (dossier) => { dossier.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "20.00" }]; }, () => ({
    previewAmounts: async (_, __, input) => new Promise((resolve) => { requests.push({ input, resolve }); }),
  }));
  try {
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "1201");
    assert.equal(totalWarning(page), "Diferencia 20.00");
    assert.equal(Boolean(page.host.querySelector('[data-testid="receipt-facts-montos"] > div[aria-busy="true"]')), true);
    await page.wait(() => requests.length === 1);
    assert.deepEqual(requests[0].input, { amount: { state: "known", value: "1201" } });
    await page.act(async () => requests[0].resolve({ net_amount: { amount: "1000", source: "read" }, mismatch: { code: "amounts_mismatch", difference: "7.89" } }));
    assert.equal(totalWarning(page), "Diferencia 7.89");
    assert.equal(page.host.querySelector('[data-testid="receipt-facts-montos"] > div[aria-busy="true"]'), null);
    assert.equal(page.writes.length, 0);
    await fill(page, '[data-testid="dossier-review-amount"]', "1202");
    await page.wait(() => requests.length === 2);
    await page.dismiss("amount");
    await page.act(async () => requests[1].resolve({ net_amount: { amount: "1000", source: "read" }, mismatch: null }));
    assert.equal(totalWarning(page), "Diferencia 20.00");
    assert.equal(page.writes.length, 0);
    await page.openRow("itbis");
    await fill(page, '[data-testid="dossier-review-itbis"]', "300");
    assert.equal(totalWarning(page), "Diferencia 20.00");
    await page.wait(() => requests.length === 3);
    await page.act(async () => requests[2].resolve({ net_amount: { amount: "980", source: "calculated" }, mismatch: null }));
    assert.equal(totalWarning(page), null);
  } finally { await page.close(); }
});

test("a tax preview updates the closed calculated net using the server result", async () => {
  const page = await setup("fiscal", (dossier) => { dossier.net_amount = { amount: "1000.00", source: "calculated" }; }, () => ({
    previewAmounts: async () => ({ net_amount: { amount: "980.00", source: "calculated" }, mismatch: null, inheritance: {} }),
  }));
  const net = () => page.row("net_amount").querySelector("[data-row-value]")?.textContent;
  try {
    assert.equal(net(), "1,000.00");
    await page.openRow("itbis");
    await fill(page, '[data-testid="dossier-review-itbis"]', "200");
    await page.wait(() => net() === "980.00");
    assert.equal(page.row("net_amount").querySelector('[data-testid="row-status-net_amount"]')?.getAttribute("data-status"), "calculated");
    assert.equal(page.writes.length, 0);
    await page.dismiss("itbis");
    assert.equal(net(), "1,000.00");
  } finally { await page.close(); }
});

test("a failed amount preview retains the last warning instead of claiming a balanced receipt", async () => {
  let called = false;
  const page = await setup("fiscal", (dossier) => { dossier.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "20.00" }]; }, () => ({
    previewAmounts: async () => { called = true; throw new Error("preview offline"); },
  }));
  try {
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "1201");
    await page.wait(() => called);
    await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
    assert.equal(totalWarning(page), "Diferencia 20.00");
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});

test("a preview shows only for the amounts it was computed from, and a failed one says the sum is checked on save", async () => {
  const requests: { resolve: (value: import("@/lib/business-api").BusinessAmountsPreview) => void; reject: (error: Error) => void }[] = [];
  const page = await setup("fiscal", (dossier) => { dossier.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "20.00" }]; }, () => ({
    previewAmounts: async () => new Promise((resolve, reject) => { requests.push({ resolve, reject }); }),
  }));
  try {
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "1201");
    await page.wait(() => requests.length === 1);
    await page.act(async () => requests[0].resolve({ net_amount: { amount: "1000", source: "read" }, mismatch: null }));
    assert.equal(totalWarning(page), null);
    await fill(page, '[data-testid="dossier-review-amount"]', "1202");
    assert.equal(totalWarning(page), "Diferencia 20.00");
    await page.wait(() => requests.length === 2);
    await page.act(async () => requests[1].reject(new Error("preview offline")));
    assert.equal(totalWarning(page), "Diferencia 20.00");
    await fill(page, '[data-testid="dossier-review-amount"]', "1201");
    assert.equal(totalWarning(page), null, "the answer for 1201 still stands");
    await fill(page, '[data-testid="dossier-review-amount"]', "1203");
    await page.wait(() => requests.length === 3);
    await page.act(async () => requests[2].reject(new Error("preview offline")));
    assert.equal(totalWarning(page), "Diferencia 20.00");
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});

test("a failed preview on balanced amounts says the sum is checked on save", async () => {
  const requests: { reject: (error: Error) => void }[] = [];
  const page = await setup("fiscal", (dossier) => { dossier.review_flags = []; }, () => ({
    previewAmounts: async () => new Promise((_, reject) => { requests.push({ reject }); }),
  }));
  try {
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "1201");
    assert.equal(totalWarning(page), null);
    await page.wait(() => requests.length === 1);
    await page.act(async () => requests[0].reject(new Error("preview offline")));
    assert.equal(totalWarning(page), "Se revisa al guardar.", "the server checks the sum again when the person saves");
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});
