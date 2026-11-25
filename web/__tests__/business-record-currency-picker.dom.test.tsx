import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { registerReceiptReviewPage, setup, type Dossier } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

const euros = (dossier: Dossier) => { dossier.facts.currency = { state: "known", value: "EUR", origin: "extracted", verified: false, source_ids: [] }; };

/** A workspace that works in pesos and Canadian dollars, holding a receipt in euros. */
async function receipt(change: (dossier: Dossier) => void = euros) {
  const page = await setup("fiscal", change, (fixture) => ({ workspace: async () => ({ ...await fixture.workspace(), currencies: ["DOP", "CAD"] }) }));
  const montos = () => page.host.querySelector<HTMLElement>('[data-testid="receipt-facts-montos"]')!;
  const picker = () => montos().querySelector<HTMLButtonElement>('[data-testid="montos-currency"]')!;
  const options = () => [...montos().querySelectorAll<HTMLButtonElement>('[role="listbox"][aria-label="Moneda"] [role="option"]')];
  const press = () => page.act(async () => picker().click());
  return { ...page, montos, picker, options, press };
}

describe("the currency picker in the Montos heading", () => {
  test("opens its own list in place: DOP, USD and EUR, the record's own checked, and no Moneda row", async () => {
    const page = await receipt();
    try {
      const rows = () => [...page.montos().querySelectorAll("li[data-fact]")].map((row) => row.getAttribute("data-fact"));
      const before = rows();
      assert.equal(page.picker().textContent, "EUR");
      assert.equal(page.picker().getAttribute("aria-haspopup"), "listbox");
      await page.press();
      assert.equal(page.picker().getAttribute("aria-expanded"), "true");
      assert.deepEqual(page.options().map((option) => option.dataset.value), ["DOP", "USD", "EUR"]);
      assert.deepEqual(page.options().map((option) => option.textContent), ["DOP · Peso dominicano", "USD · Dólar estadounidense", "EUR · Euro"]);
      assert.deepEqual(page.options().map((option) => option.getAttribute("aria-selected")), ["false", "false", "true"]);
      assert.equal(document.activeElement, page.options()[2], "the list takes the focus on the record's own");
      assert.deepEqual(rows(), before, "no row is added under the heading");
      assert.equal(page.montos().querySelector('select, [data-row-open], button[aria-label^="Guardar"], button[aria-label^="Cancelar"]'), null);
      await page.press();
      assert.equal(page.options().length, 0, "a second press closes it");
      assert.equal(page.writes.length, 0, "looking saves nothing");
    } finally { await page.close(); }
  });

  test("a pick saves at once through the record's facts, and picking the same one saves nothing", async () => {
    const page = await receipt(() => undefined);
    try {
      assert.equal(page.picker().textContent, "DOP");
      await page.press();
      await page.act(async () => page.options().find((option) => option.dataset.value === "DOP")!.click());
      assert.equal(page.options().length, 0);
      assert.equal(page.writes.length, 0);
      await page.press();
      await page.act(async () => page.options().find((option) => option.dataset.value === "USD")!.click());
      await page.wait(() => page.picker().textContent === "USD" && !page.picker().hasAttribute("aria-busy"));
      assert.deepEqual(page.writes.map(({ kind, body }) => ({ kind, body })), [{ kind: "facts", body: { currency: { state: "known", value: "USD" } } }]);
      assert.equal(page.options().length, 0, "the list closed");
      assert.equal(document.activeElement, page.picker());
      assert.doesNotMatch(page.montos().textContent ?? "", /Guardado/);
    } finally { await page.close(); }
  });

  test("a pick the server refuses says so under the rows, and the picker keeps the saved currency", async () => {
    const page = await setup("fiscal", euros, () => ({ reviewDraft: async () => { throw Object.assign(new Error("refused"), { status: 422, code: "currency_mismatch" }); } }));
    try {
      const montos = page.host.querySelector<HTMLElement>('[data-testid="receipt-facts-montos"]')!;
      const picker = () => montos.querySelector<HTMLButtonElement>('[data-testid="montos-currency"]')!;
      await page.act(async () => picker().click());
      await page.act(async () => montos.querySelector<HTMLButtonElement>('[role="option"][data-value="USD"]')!.click());
      await page.wait(() => Boolean(montos.querySelector('[data-testid="row-save-failed"]')));
      assert.equal(picker().textContent, "EUR");
    } finally { await page.close(); }
  });

  test("someone who cannot edit the record reads the currency and opens no list", async () => {
    const page = await receipt((dossier) => { euros(dossier); dossier.capabilities = ["read"]; dossier.facts_editable = false; dossier.editable_fields = []; });
    try {
      assert.equal(page.picker().disabled, true);
      assert.equal(page.picker().textContent, "EUR");
    } finally { await page.close(); }
  });
});
