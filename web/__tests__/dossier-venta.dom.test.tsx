import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { button, openList, pick, registerReceiptReviewPage, setup, type Dossier } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

type Write = { kind: string; version: number; body: unknown };

/** A review page whose type changes and payment picks are kept in order, with the toasts on screen. */
async function venta(change: (dossier: Dossier) => void = () => undefined, start: "recibo" | "venta" = "recibo", seed?: (server: BusinessDataSource, dossier: Dossier) => Promise<unknown>) {
  const writes: Write[] = [];
  let seeded = !seed;
  const page = await setup("fiscal", change, (fixture): Partial<BusinessDataSource> => ({
    dossier: async (draft) => {
      if (!seeded) { seeded = true; await seed!(fixture, await fixture.dossier(draft)); }
      const dossier = await fixture.dossier(draft); change(dossier); return dossier;
    },
    setDocumentType: async (id, version, type, key) => { writes.push({ kind: "type", version, body: type }); const next = await fixture.setDocumentType(id, version, type, key); change(next); return next; },
    reviewSalePayment: async (id, version, form, key) => { writes.push({ kind: "sale_payment", version, body: form }); const next = await fixture.reviewSalePayment(id, version, form, key); change(next); return next; },
  }));
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const { clearToasts } = await import("@/components/business-app/foundation/toasts");
  clearToasts();
  const toastHost = document.createElement("div");
  document.body.appendChild(toastHost);
  const toastRoot = createRoot(toastHost);
  await page.act(async () => { toastRoot.render(<I18nextProvider i18n={page.i18n}><ToastViewport /></I18nextProvider>); });
  const toggle = () => page.host.querySelector<HTMLButtonElement>('[data-testid="receipt-mark-sale"]');
  const settled = (on: boolean) => toggle()?.getAttribute("aria-checked") === String(on) && !toggle()?.hasAttribute("aria-busy");
  const flip = async (to: boolean) => {
    await page.act(async () => toggle()!.click());
    await page.wait(() => settled(to));
  };
  const card = () => page.host.querySelector<HTMLElement>('[data-testid="receipt-facts-choices"]');
  const undo = async () => {
    const found = [...toastHost.querySelectorAll("button")].find((item) => item.textContent === "Deshacer");
    assert.ok(found, "the toast offers Deshacer");
    await page.act(async () => found.click());
  };
  if (start === "venta") {
    await flip(true);
    writes.length = 0;
    page.writes.length = 0;
    await page.act(async () => clearToasts());
  }
  return {
    ...page, writes, declarationWrites: page.writes, toggle, settled, flip, card, undo,
    toast: () => toastHost.textContent ?? "",
    close: async () => { await page.act(async () => { clearToasts(); toastRoot.unmount(); }); toastHost.remove(); await page.close(); },
  };
}

const rowLabels = (scope: ParentNode) => [...scope.querySelectorAll<HTMLElement>("li[data-fact]")].map((row) => row.firstElementChild?.textContent);

describe("the Venta switch in Más", () => {
  test("it is a row like Personal, off on a purchase, with its line", async () => {
    const page = await venta();
    try {
      const personal = page.host.querySelector<HTMLElement>('[data-testid="receipt-mark-personal"]')!;
      const sale = page.toggle()!;
      assert.equal(sale.getAttribute("role"), "menuitemcheckbox");
      assert.equal(sale.getAttribute("aria-checked"), "false");
      assert.equal(sale.className, personal.className, "the same menu row");
      assert.deepEqual([...sale.querySelectorAll("span > span.block")].map((item) => item.textContent), ["Venta", "Pásalo al Reporte 607."]);
      assert.ok(personal.compareDocumentPosition(sale) & Node.DOCUMENT_POSITION_FOLLOWING, "under Personal");
      assert.equal(page.host.querySelector('[data-fact="document_type"]'), null, "a clean record has no Tipo row");
    } finally { await page.close(); }
  });

  test("on makes the record a sale through the type command and says so; Deshacer makes it a purchase again", async () => {
    const page = await venta();
    try {
      assert.equal(page.card()?.getAttribute("aria-label"), "Reporte 606");
      await page.flip(true);
      assert.deepEqual(page.writes, [{ kind: "type", version: 2, body: "venta" }]);
      assert.match(page.toast(), /Ahora es una venta\. Va al Reporte 607\./);
      assert.equal(page.host.querySelector<HTMLElement>("#receipt-more-panel")!.hidden, true, "Más closes on the change");
      assert.match(page.toggle()!.textContent ?? "", /Va al Reporte 607\./);
      assert.equal(page.card()?.getAttribute("aria-label"), "Reporte 607");
      await page.undo();
      await page.wait(() => page.settled(false));
      assert.deepEqual(page.writes.map((write) => write.body), ["venta", "recibo"]);
      assert.equal(page.writes[1].version, 3, "Deshacer changes the revision the switch saved");
      assert.equal(page.card()?.getAttribute("aria-label"), "Reporte 606");
    } finally { await page.close(); }
  });

  test("off makes a sale a purchase and says so, with Deshacer", async () => {
    const page = await venta(undefined, "venta");
    try {
      await page.flip(false);
      assert.deepEqual(page.writes.map((write) => write.body), ["recibo"]);
      assert.match(page.toast(), /Ahora es una compra\. Va al Reporte 606\./);
      assert.match(page.toast(), /Deshacer/);
      assert.match(page.toggle()!.textContent ?? "", /Pásalo al Reporte 607\./);
    } finally { await page.close(); }
  });

  test("it is absent when the server does not allow the change", async () => {
    const page = await venta((dossier) => { dossier.document_type_editable = false; });
    try {
      assert.equal(page.toggle(), null);
      assert.ok(page.host.querySelector('[data-testid="receipt-mark-personal"]'), "Personal stays");
    } finally { await page.close(); }
  });

  test("a refused change rolls the switch back and says so in Más", async () => {
    const page = await setup("saveRefused");
    try {
      const toggle = () => page.host.querySelector<HTMLButtonElement>('[data-testid="receipt-mark-sale"]')!;
      await page.act(async () => toggle().click());
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="receipt-marks-problem"]')));
      assert.equal(toggle().getAttribute("aria-checked"), "false");
      assert.match(page.host.querySelector('[data-testid="receipt-marks-problem"]')!.textContent ?? "", /No pudimos guardar el cambio/);
    } finally { await page.close(); }
  });

  test("answers the change would clear are named before it happens, and Cancelar changes nothing", async () => {
    const page = await venta((dossier) => { if (dossier.document_type !== "venta") dossier.dgii = { form: "606", category: "02", payment_method: "01" }; });
    try {
      await page.act(async () => page.toggle()!.click());
      await page.wait(() => Boolean(document.querySelector('[role="alertdialog"], [role="dialog"]')));
      assert.match(document.body.textContent ?? "", /Cambiar el tipo borra el tipo de gasto y la forma de pago\./);
      await page.act(async () => button(document.body, "Cancelar").click());
      await page.wait(() => page.settled(false));
      assert.equal(page.writes.length, 0);
      await page.act(async () => page.toggle()!.click());
      await page.wait(() => Boolean(document.querySelector('[role="alertdialog"], [role="dialog"]')));
      await page.act(async () => button(document.body, "Guardar").click());
      await page.wait(() => page.settled(true));
      assert.deepEqual(page.writes.map((write) => write.body), ["venta"]);
    } finally { await page.close(); }
  });

  test("under Personal a sale asks about the 607", async () => {
    const personal = (dossier: Dossier) => { dossier.personal = true; dossier.fiscal_question_applies = true; };
    const page = await venta(personal, "venta");
    try {
      assert.match(page.host.querySelector('[data-testid="receipt-606"]')!.textContent ?? "", /^Incluir en el 607/);
      await page.flip(false);
      assert.match(page.host.querySelector('[data-testid="receipt-606"]')!.textContent ?? "", /^Incluir en el 606/);
    } finally { await page.close(); }
  });
});

describe("a sale's General", () => {
  test("Cliente, then Reporte 607 with Tipo de ingreso and Forma de pago, and no Tipo de gasto or Tipo row", async () => {
    const page = await venta(undefined, "venta");
    try {
      assert.deepEqual(rowLabels(page.host.querySelector('[data-testid="receipt-facts-comprobante"]')!), ["RNC", "Cliente", "NCF", "Fecha"]);
      assert.equal(page.card()!.querySelector("h3")?.textContent, "Reporte 607");
      assert.deepEqual(rowLabels(page.card()!), ["Tipo de ingreso", "Forma de pago"]);
      const general = page.host.querySelector('[data-tab-panel="general"]')!;
      assert.doesNotMatch(general.textContent ?? "", /Tipo de gasto/);
      assert.equal(general.querySelector('[data-fact="category"]'), null);
      assert.equal(general.querySelector('[data-fact="payment_method"]'), null);
      assert.equal(general.querySelector('[data-fact="document_type"]'), null);
    } finally { await page.close(); }
  });

  test("both rows open a list: the six income types and the seven 607 payment forms", async () => {
    const page = await venta(undefined, "venta");
    try {
      const income = await openList(page, "income_type");
      assert.deepEqual(income.map((item) => item.textContent), ["Ingresos por operaciones (no financieros)", "Ingresos financieros", "Ingresos extraordinarios", "Ingresos por arrendamientos", "Ingresos por venta de activo depreciable", "Otros ingresos"]);
      const forms = await openList(page, "sale_payment");
      assert.deepEqual(forms.map((item) => item.textContent), ["Efectivo", "Cheque, transferencia o depósito", "Tarjeta de débito o crédito", "Venta a crédito", "Bonos o certificados de regalo", "Permuta", "Otras formas de venta"]);
    } finally { await page.close(); }
  });

  test("one payment pick sends the form and no amount, and the row shows what the server saved", async () => {
    const page = await venta(undefined, "venta");
    try {
      await pick(page, "sale_payment", "bank");
      await page.wait(() => page.row("sale_payment").querySelector("[data-row-value]")?.textContent === "Cheque, transferencia o depósito");
      assert.deepEqual(page.writes, [{ kind: "sale_payment", version: 3, body: "bank" }]);
      assert.doesNotMatch(JSON.stringify(page.writes), /\d+\.\d\d/, "no amount leaves the web");
    } finally { await page.close(); }
  });

  test("a bucket short of the total is no pick: the row is empty, and picking that same form sends the command", async () => {
    const shortCash = async (server: BusinessDataSource, dossier: Dossier) => {
      const sale = await server.setDocumentType(dossier.draft_id, dossier.version, "venta", "seed-type");
      const fiscal = sale.facts.fiscal;
      await server.reviewFiscal(sale.draft_id, sale.version, { fiscal: { rnc: fiscal?.rnc.value ?? null, ncf: fiscal?.ncf.value ?? null, itbis: fiscal?.itbis.value ?? null }, declaration: { ...sale.dgii, form: "607", cash: "1.00" } }, "seed-cash");
    };
    const page = await venta(undefined, "recibo", shortCash);
    try {
      assert.equal(page.toggle()?.getAttribute("aria-checked"), "true", "the record is a sale");
      const value = () => page.row("sale_payment").querySelector("[data-row-value]")?.textContent;
      assert.notEqual(value(), "Efectivo", "no form holds the whole total");
      assert.ok((await openList(page, "sale_payment")).every((item) => item.getAttribute("aria-selected") === "false"), "no form is chosen");
      await pick(page, "sale_payment", "cash");
      await page.wait(() => value() === "Efectivo");
      assert.deepEqual(page.writes.map(({ kind, body }) => ({ kind, body })), [{ kind: "sale_payment", body: "cash" }]);
    } finally { await page.close(); }
  });

  test("an income type pick saves at once on the declaration", async () => {
    const page = await venta(undefined, "venta");
    try {
      await pick(page, "income_type", "4");
      await page.wait(() => page.row("income_type").querySelector("[data-row-value]")?.textContent === "Ingresos por arrendamientos");
      const [write] = page.declarationWrites as { kind: string; body: { declaration: Record<string, unknown> } }[];
      assert.equal(write.kind, "fiscal");
      assert.equal(write.body.declaration.form, "607");
      assert.equal(write.body.declaration.income_type, "4");
      assert.deepEqual(page.writes, [], "no payment form is sent with it");
    } finally { await page.close(); }
  });

  test("a sale nobody may edit shows both answers as text, with no list", async () => {
    const page = await venta((dossier) => { if (dossier.document_type === "venta") { dossier.payment_split_editable = false; dossier.sale_payment = { form: "card", options: dossier.sale_payment?.options ?? [] }; } }, "venta");
    try {
      assert.equal(page.row("sale_payment").querySelector('button[aria-haspopup="listbox"]'), null);
      assert.equal(page.row("income_type").querySelector('button[aria-haspopup="listbox"]'), null);
      assert.equal(page.row("sale_payment").querySelector("[data-row-value]")?.textContent, "Tarjeta de débito o crédito");
    } finally { await page.close(); }
  });
});

describe("a sale's Datos fiscales", () => {
  const cards = (page: { host: ParentNode }) => [...page.host.querySelectorAll<HTMLElement>('[data-testid="fiscal-declaration"] section[data-group]')].map((card) => ({
    title: card.querySelector("h3")?.textContent,
    rows: [...card.querySelectorAll<HTMLElement>("ul:not([hidden]) > li[data-fact]")].map((row) => row.firstElementChild?.textContent),
    folded: card.querySelector("p")?.textContent ?? null,
    add: card.querySelector("button[aria-expanded]")?.textContent ?? null,
  }));

  test("Reporte 607 with Tipo de ID alone, Monto facturado, ITBIS facturado, and both folds closed", async () => {
    const page = await venta(undefined, "venta");
    try {
      assert.deepEqual(cards(page), [
        { title: "Reporte 607", rows: ["Tipo de ID"], folded: null, add: null },
        { title: "Monto facturado", rows: ["Monto facturado"], folded: null, add: null },
        { title: "ITBIS", rows: ["ITBIS facturado"], folded: null, add: null },
        { title: "Retenciones", rows: [], folded: "Sin retenciones.", add: "Agregar retención" },
        { title: "Otros impuestos", rows: [], folded: "Sin otros impuestos.", add: "Agregar impuesto" },
      ]);
    } finally { await page.close(); }
  });

  test("the folds open on the sale's own rows", async () => {
    const page = await venta(undefined, "venta");
    try {
      for (const label of ["Agregar retención", "Agregar impuesto"]) await page.act(async () => button(page.host.querySelector('[data-testid="fiscal-declaration"]')!, label).click());
      const [, , , retentions, other] = cards(page);
      assert.deepEqual(retentions.rows, ["ITBIS retenido por terceros", "Retención de renta por terceros", "Fecha de retención"]);
      assert.deepEqual(other.rows, ["Impuesto Selectivo al Consumo", "Otros Impuestos/Tasas"]);
    } finally { await page.close(); }
  });

  test("nothing of the 606, no perceived amounts, no payment buckets and no NCF modificado on a regular sale", async () => {
    const page = await venta(undefined, "venta");
    try {
      const shown = [...page.host.querySelectorAll<HTMLElement>('[data-testid="fiscal-declaration"] li[data-fact]')].map((row) => row.dataset.fact);
      assert.deepEqual(shown, ["id_type", "billed_amount", "itbis", "itbis_withheld_by_third_parties", "income_withheld_by_third_parties", "withheld_on", "selective_tax", "other_taxes"]);
    } finally { await page.close(); }
  });

  test("a sale that is a note shows NCF modificado", async () => {
    const note = (dossier: Dossier) => { if (dossier.facts.fiscal) dossier.facts.fiscal.ncf = { state: "known", value: "B0400000012", origin: "extracted", verified: false, source_ids: [] }; };
    const page = await venta(note, "venta");
    try {
      assert.deepEqual(cards(page)[0], { title: "Reporte 607", rows: ["Tipo de ID", "NCF modificado"], folded: null, add: null });
    } finally { await page.close(); }
  });

  test("Monto facturado follows the subtotal and stays editable", async () => {
    const linked = (dossier: Dossier) => { if (dossier.document_type === "venta") dossier.inheritance = { billed_amount: { field: "net_amount", inherited: true, value: "2923.73", paired_with: [] } }; };
    const page = await venta(linked, "venta");
    try {
      const row = page.row("billed_amount");
      assert.equal(row.querySelector('[data-testid="row-status-billed_amount"]')?.getAttribute("aria-label"), "Sale del subtotal");
      assert.ok(row.querySelector('button[aria-label="Editar detalles · Monto facturado"]'), "editable");
    } finally { await page.close(); }
  });
});
