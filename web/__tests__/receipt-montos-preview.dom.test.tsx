import assert from "node:assert/strict";
import { test } from "bun:test";
import { fill, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

for (const form of ["606", "607"] as const) test(`header currency warns before saving a non-DOP ${form}`, async () => {
  const page = await setup("fiscal", (dossier) => { dossier.dgii = { ...dossier.dgii, form }; });
  try {
    await page.openRow("currency");
    const selector = '[data-testid="edit-currency"] select';
    const select = page.host.querySelector<HTMLSelectElement>(selector)!;
    assert.deepEqual([...select.options].map((option) => option.value), ["", "DOP", "USD", "EUR"]);
    for (const currency of ["USD", "EUR"]) {
      await fill(page, selector, currency, HTMLSelectElement);
      assert.ok(page.row("currency").textContent?.includes(`En ${currency} este documento no entra al ${form} (la DGII pide pesos).`));
      assert.equal(page.writes.length, 0);
    }
    await fill(page, selector, "DOP", HTMLSelectElement);
    assert.equal(page.row("currency").querySelector('[role="status"]'), null);
    await page.dismiss("currency");
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});

test("amount edit and cancel keep the number box and the two action slots", async () => {
  const page = await setup();
  try {
    const before = page.row("amount").querySelector<HTMLElement>("[data-number-box]")!;
    assert.ok(!page.row("amount").querySelector("button")!.classList.contains("opacity-0"));
    const width = [...before.classList].find((name) => name.startsWith("w-["));
    assert.ok(width);
    await page.openRow("amount");
    const editing = page.row("amount").querySelector<HTMLElement>("[data-number-box]")!;
    assert.ok(editing.classList.contains(width));
    assert.ok(editing.querySelector("input")!.classList.contains("text-right"));
    assert.equal(editing.querySelector("select"), null);
    assert.equal(editing.querySelector('[aria-hidden="true"]'), null);
    assert.equal(editing.nextElementSibling?.querySelectorAll("button").length, 2);
    await page.dismiss("amount");
    assert.ok(page.row("amount").querySelector("[data-number-box]"));
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
    assert.equal(page.row("amount").querySelector('[data-testid="amounts-difference"]')?.textContent, "Diferencia 20.00");
    assert.equal(page.host.querySelector('[data-testid="receipt-facts-montos"]')?.getAttribute("aria-busy"), "true");
    await page.wait(() => requests.length === 1);
    assert.deepEqual(requests[0].input, { amount: { state: "known", value: "1201" } });
    await page.act(async () => requests[0].resolve({ net_amount: { amount: "1000", source: "read" }, mismatch: { code: "amounts_mismatch", difference: "7.89" } }));
    assert.equal(page.row("amount").querySelector('[data-testid="amounts-difference"]')?.textContent, "Diferencia 7.89");
    assert.equal(page.writes.length, 0);
    await fill(page, '[data-testid="dossier-review-amount"]', "1202");
    await page.wait(() => requests.length === 2);
    await page.dismiss("amount");
    await page.act(async () => requests[1].resolve({ net_amount: { amount: "1000", source: "read" }, mismatch: null }));
    assert.equal(page.row("amount").querySelector('[data-testid="amounts-difference"]')?.textContent, "Diferencia 20.00");
    assert.equal(page.writes.length, 0);
    await page.openRow("itbis");
    await fill(page, '[data-testid="dossier-review-itbis"]', "300");
    assert.equal(page.row("amount").querySelector('[data-testid="amounts-difference"]')?.textContent, "Diferencia 20.00");
    await page.wait(() => requests.length === 3);
    await page.act(async () => requests[2].resolve({ net_amount: { amount: "980", source: "calculated" }, mismatch: null }));
    assert.equal(page.row("amount").querySelector('[data-testid="amounts-difference"]'), null);
  } finally { await page.close(); }
});

test("a tax preview updates the closed calculated net using the server result", async () => {
  const page = await setup("fiscal", (dossier) => { dossier.net_amount = { amount: "1000.00", source: "calculated" }; }, () => ({
    previewAmounts: async () => ({ net_amount: { amount: "980.00", source: "calculated" }, mismatch: null }),
  }));
  try {
    await page.openRow("itbis");
    await fill(page, '[data-testid="dossier-review-itbis"]', "200");
    await page.wait(() => page.row("net_amount").textContent?.includes("980.00") === true);
    assert.ok(page.row("net_amount").querySelector('[data-testid="amount-calculated"]'));
    assert.equal(page.writes.length, 0);
    await page.dismiss("itbis");
    assert.ok(page.row("net_amount").textContent?.includes("1,000.00"));
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
    assert.equal(page.row("amount").querySelector('[data-testid="amounts-difference"]')?.textContent, "Diferencia 20.00");
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});

test("a preview shows only for the amounts it was computed from, and a failed one says the sum is checked on save", async () => {
  const requests: { resolve: (value: import("@/lib/business-api").BusinessAmountsPreview) => void; reject: (error: Error) => void }[] = [];
  const page = await setup("fiscal", (dossier) => { dossier.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "20.00" }]; }, () => ({
    previewAmounts: async () => new Promise((resolve, reject) => { requests.push({ resolve, reject }); }),
  }));
  const difference = () => page.row("amount").querySelector('[data-testid="amounts-difference"]')?.textContent;
  const unavailable = () => page.row("amount").querySelector('[data-testid="amounts-unavailable"]');
  try {
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "1201");
    await page.wait(() => requests.length === 1);
    await page.act(async () => requests[0].resolve({ net_amount: { amount: "1000", source: "read" }, mismatch: null }));
    assert.equal(difference(), undefined);
    await fill(page, '[data-testid="dossier-review-amount"]', "1202");
    assert.equal(difference(), "Diferencia 20.00");
    await page.wait(() => requests.length === 2);
    await page.act(async () => requests[1].reject(new Error("preview offline")));
    assert.equal(difference(), "Diferencia 20.00");
    assert.equal(unavailable()?.textContent, "Se revisa al guardar.", "the server checks the sum again when the person saves");
    assert.equal(page.writes.length, 0);
  } finally { await page.close(); }
});
