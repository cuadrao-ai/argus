import assert from "node:assert/strict";
import { test } from "bun:test";
import { fill, kindAsked, pick, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

async function history(page: Awaited<ReturnType<typeof setup>>) {
  await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-tab="historial"]')!.click());
  return page.host.querySelector('[data-testid="receipt-history"]')!;
}

const diff = (rail: Element, field: RegExp, before: RegExp, after: RegExp) =>
  [...rail.querySelectorAll("li")].some((row) => field.test(row.querySelector("p")?.textContent ?? "")
    && before.test(row.querySelector("del")?.textContent ?? "") && after.test(row.querySelector("ins")?.textContent ?? ""));

test("an accepted record saves a fact in place and shows the server revision in Historial", async () => {
  const page = await setup("recordedThenMarked", (dossier) => {
    dossier.editable_fields = ["counterparty"];
  });
  try {
    assert.equal(page.host.querySelector('[data-testid="dossier-status"]'), null);
    assert.equal(page.host.querySelector("[data-review-primary]"), null);
    const edit = page.row("counterparty").querySelector<HTMLButtonElement>("[data-row-value]");
    assert.ok(edit, "the server enables editing the counterparty in place");
    await page.openRow("counterparty");
    await fill(page, '[data-testid="edit-counterparty"] input', "Comercio corregido");
    await page.check("counterparty");
    await page.wait(() => page.row("counterparty").textContent?.includes("Comercio corregido") === true);
    assert.deepEqual(page.writes.map(({ kind, body }) => ({ kind, body })), [
      { kind: "facts", body: { counterparty: { state: "known", value: "Comercio corregido" } } },
    ]);
    assert.equal(page.host.querySelector("[data-review-primary]"), null);
    const rail = await history(page);
    assert.ok(diff(rail, /Emisor/, /Ferretería La Esquina/, /Comercio corregido/));
    assert.ok(rail.querySelector('[data-approved="true"] time[datetime]'));
  } finally { await page.close(); }
});

test("an accepted Total keeps its saved value after a blank write is refused inline", async () => {
  const page = await setup("recordedThenMarked");
  try {
    const total = page.row("amount").querySelector("[data-row-value]")?.textContent;
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "");
    await page.check("amount");
    await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-save-failed"]')));
    assert.deepEqual(page.writes.map(({ body }) => body), [{ amount: { state: "unknown", value: null } }]);
    assert.match(page.row("amount").querySelector('[role="alert"]')?.textContent ?? "", /Escribe un valor para Total/);
    assert.equal(page.row("amount").querySelector("input")?.value, "");
    await page.dismiss("amount");
    assert.equal(page.row("amount").querySelector("[data-row-value]")?.textContent, total);
    await page.openRow("amount");
    await fill(page, '[data-testid="dossier-review-amount"]', "1999.00");
    await page.check("amount");
    await page.wait(() => page.row("amount").querySelector("[data-row-value]")?.textContent === "1,999.00");
    assert.equal(page.host.querySelector("[data-review-primary]"), null);
    assert.ok(diff(await history(page), /Total/, /3,450[.]00/, /1,999[.]00/));
  } finally { await page.close(); }
});

test("accepted ITBIS and Subtotal can each be saved as zero and then cleared", async () => {
  const page = await setup("recordedThenMarked");
  try {
    for (const [row, selector] of [["itbis", "dossier-review-itbis"], ["net_amount", "dossier-review-net_amount"]]) {
      for (const [value, shown] of [["0.00", "0.00"], ["", "Sin dato"]]) {
        await page.openRow(row);
        await fill(page, `[data-testid="${selector}"]`, value);
        await page.check(row);
        await page.wait(() => page.row(row).querySelector("[data-row-value]")?.textContent === shown);
        assert.ok(page.row(row).querySelector('[data-testid="row-saved"]'), `${row} saved`);
      }
    }
    assert.equal(page.host.querySelector("[data-review-primary]"), null);
    const rail = await history(page);
    for (const field of [/ITBIS/, /Subtotal/]) {
      assert.ok(diff(rail, field, /^$/, /0[.]00/), `${field} history shows the inserted zero`);
      assert.ok(diff(rail, field, /0[.]00/, /Sin dato/), `${field} history shows the cleared zero`);
    }
  } finally { await page.close(); }
});

test("accepted Datos fiscales uses the shared row check and cancel", async () => {
  const page = await setup("recordedThenMarked");
  try {
    await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-tab="fiscal"]')!.click());
    await page.openRow("itbis_cost");
    await fill(page, '[data-testid="fiscal-declaration-itbis_cost"]', "12.50");
    await page.dismiss("itbis_cost");
    assert.deepEqual(page.writes, []);
    await page.openRow("itbis_cost");
    await fill(page, '[data-testid="fiscal-declaration-itbis_cost"]', "25.35");
    await page.check("itbis_cost");
    await page.wait(() => Boolean(page.row("itbis_cost").querySelector('[data-testid="row-saved"]')));
    assert.equal(page.row("itbis_cost").querySelector("[data-row-value]")?.textContent, "25.35");
    await page.openRow("itbis_cost");
    await fill(page, '[data-testid="fiscal-declaration-itbis_cost"]', "36.25");
    await page.check("itbis_cost");
    await page.wait(() => page.row("itbis_cost").querySelector("[data-row-value]")?.textContent === "36.25");
    assert.deepEqual(page.writes.map(({ kind }) => kind), ["fiscal", "fiscal"]);
    assert.equal(page.host.querySelector("[data-review-primary]"), null);
    assert.ok(diff(await history(page), /Datos del 606 guardados/, /25[.]35/, /36[.]25/));
  } finally { await page.close(); }
});

test("accepted record edit controls follow the server field allowlist", async () => {
  const page = await setup("recordedThenMarked", (dossier) => {
    dossier.editable_fields = ["counterparty"];
    dossier.facts_editable = false;
    dossier.declaration_editable = false;
  });
  try {
    assert.ok(page.row("counterparty").querySelector("button[data-row-value]"));
    for (const row of ["amount", "occurred_on", "itbis", "itbis_cost"]) {
      assert.equal(page.row(row).querySelector("button[data-row-value]"), null, row);
    }
    assert.equal(page.host.querySelector<HTMLButtonElement>('[data-testid="montos-currency"]')?.disabled, true);
  } finally { await page.close(); }
});

test("accepted 606 choices save on the pick and show the returned fiscal diff", async () => {
  const page = await setup("recordedThenMarked", (dossier) => { dossier.sin_comprobante = false; });
  try {
    for (const value of ["01", "03"]) {
      await pick(page, "payment_method", value);
      await page.wait(() => Boolean(page.row("payment_method").querySelector('[data-testid="row-saved"]')));
    }
    assert.deepEqual(page.writes.map(({ body }) => body), [{ payment_method: "01" }, { payment_method: "03" }]);
    assert.ok(diff(await history(page), /Datos del 606 guardados/, /Efectivo/, /Tarjeta crédito/));
  } finally { await page.close(); }
});

test("changing an accepted document type shows the server's before and after types", async () => {
  const page = await setup("recordedThenMarked", kindAsked);
  try {
    await page.openRow("document_type");
    await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
    await page.check("document_type");
    await page.wait(() => page.host.querySelector('[data-testid="receipt-mark-sale"]')?.getAttribute("aria-checked") === "true");
    assert.equal(page.host.querySelector('[data-fact="document_type"]'), null, "the row leaves once the type is settled");
    assert.equal(page.host.querySelector("[data-review-primary]"), null);
    assert.ok(diff(await history(page), /Tipo/, /Compra/, /Venta/));
  } finally { await page.close(); }
});

test("clearing the last saved withholding leaves its check and cancel on screen", async () => {
  const page = await setup("recordedThenMarked", (dossier) => {
    if (dossier.version === 4) dossier.dgii = { form: "606", itbis_withheld: "10.00" };
  });
  try {
    await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-tab="fiscal"]')!.click());
    await page.openRow("itbis_withheld");
    await fill(page, '[data-testid="fiscal-declaration-itbis_withheld"]', "");
    assert.equal(page.row("itbis_withheld").closest("ul")?.hidden, false);
    await page.check("itbis_withheld");
    await page.wait(() => page.writes.length === 1);
  } finally { await page.close(); }
});
