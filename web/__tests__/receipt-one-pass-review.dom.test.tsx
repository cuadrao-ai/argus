import assert from "node:assert/strict";
import { describe, spyOn, test } from "bun:test";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { button, fill, mount, registerReceiptReviewPage, setup, type Dossier } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();
const keys: [string, number][] = [];

/** The server's standing for a sample changed after it was read: its reasons and its Bandeja label. */
function standing(dossier: Dossier, gaps: NonNullable<Dossier["listo_gaps"]>, confirmable: typeof gaps = []) {
  dossier.listo_gaps = gaps;
  dossier.confirmable = confirmable;
  dossier.bandeja_group = gaps.length ? { group: "attention", reason: gaps[0], label: "needs_attention" } : { group: "listo", reason: null, label: "ready" };
}

/** Presses the reason the status line names, beside the pill or in its list. */
async function pressReason(page: Awaited<ReturnType<typeof setup>>, title: string) {
  const one = page.host.querySelector<HTMLButtonElement>('[data-testid="dossier-reason"]');
  if (one) {
    assert.equal(one.textContent, title);
    await page.act(async () => one.click());
    return;
  }
  await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="dossier-problems"]')!.click());
  const option = [...page.host.querySelectorAll<HTMLButtonElement>('[data-testid="dossier-problem-list"] [role="option"]')].find((item) => item.textContent?.startsWith(title));
  assert.ok(option, `missing reason ${title}`);
  await page.act(async () => option.click());
}

describe("a receipt with no currency", () => {
  const unknownFact = { state: "unknown" as const, value: null, origin: null, verified: false, source_ids: [] };
  const worksIn = (currencies: string[]) => (fixture: BusinessDataSource): Partial<BusinessDataSource> => ({ workspace: async () => ({ ...await fixture.workspace(), currencies }) });
  async function noCurrency(currencies = ["DOP", "USD"], change: (dossier: Dossier) => void = () => undefined) {
    const page = await setup("noCurrency", change, worksIn(currencies));
    await page.wait(() => Boolean(page.api().records.workspace));
    // The Montos heading is the currency's picker; its row opens at the top of the card.
    const picker = () => page.host.querySelector<HTMLButtonElement>('[data-testid="montos-currency"]')!;
    const row = (name: string) => page.host.querySelector<HTMLElement>(`li[data-fact="${name}"]`)!;
    const select = () => row("currency").querySelector<HTMLSelectElement>('[data-testid="edit-currency"] select')!;
    const action = (name: string, label: "Guardar" | "Cancelar") => row(name).querySelector<HTMLButtonElement>(`button[aria-label^="${label} · "]`)!;
    const openRow = (name: string) => page.act(async () => (name === "currency" ? picker() : row(name).querySelector<HTMLButtonElement>("button[data-row-value]")!).click());
    const check = (name: string) => page.act(async () => action(name, "Guardar").click());
    const dismiss = (name: string) => page.act(async () => action(name, "Cancelar").click());
    return { ...page, picker, row, select, action, openRow, check, dismiss };
  }

  test("a missing currency stays unchosen until the person selects and saves it", async () => {
    const page = await noCurrency(["DOP"]);
    try {
      assert.equal(page.picker().getAttribute("data-missing"), "true");
      await page.openRow("currency");
      assert.equal(page.select().value, "");

      assert.equal(page.writes.length, 0, "opening saves nothing");
      await page.dismiss("currency");
      assert.equal(page.row("currency"), null, "the X closes the row");
      assert.equal(page.writes.length, 0, "the X drops it");
      await page.openRow("currency");
      await fill(page, '[data-testid="edit-currency"] select', "DOP", HTMLSelectElement);
      await page.check("currency");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="receipt-facts-montos"] [data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ body }) => body), [{ currency: { state: "known", value: "DOP" } }]);
      assert.equal(page.picker().textContent, "DOP");
      assert.equal(page.picker().getAttribute("aria-label"), "Moneda: DOP");
      assert.equal(page.picker().getAttribute("data-missing"), null);
    } finally { await page.close(); }
  });

  test("a Business with no account offers the three supported currencies", async () => {
    const page = await noCurrency([]);
    try {
      await page.openRow("currency");
      assert.deepEqual([...page.select().options].map((option) => option.value), ["", "DOP", "USD", "EUR"]);
      assert.equal(page.select().value, "");
    } finally { await page.close(); }
  });

  test("several currencies keep the empty choice in a control wide enough for it, and the check alone saves nothing", async () => {
    const page = await noCurrency();
    try {
      await page.openRow("currency");
      assert.equal(page.select().value, "");
      assert.deepEqual([...page.select().options].map((option) => option.text), ["Elegir", "DOP", "USD", "EUR"]);
      await page.check("currency");
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("the currency select has an accessible name", async () => {
    const page = await noCurrency();
    try {
      await page.openRow("currency");
      const label = page.select().closest("label")!;
      const name = [...label.querySelectorAll("span")].find((span) => span.textContent === "Moneda");
      assert.ok(name, "the label names it");
      assert.ok(name.classList.contains("sr-only"), "the row's own label gives the visible context");
      assert.equal(page.row("currency").firstElementChild?.textContent, "Moneda");
    } finally { await page.close(); }
  });

  test("pressing Falta la moneda puts focus on the currency picker, also the second time, and saves nothing", async () => {
    const page = await noCurrency();
    try {
      await pressReason(page, "Falta la moneda");
      assert.equal(document.activeElement, page.picker());
      await page.act(async () => page.picker().blur());
      await pressReason(page, "Falta la moneda");
      assert.equal(document.activeElement, page.picker());
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("pressing Falta el total washes the amount row and puts focus on it", async () => {
    const page = await noCurrency(undefined, (dossier) => {
      dossier.facts.amount = unknownFact;
      dossier.blockers = [{ code: "fact_required", field: "amount" }, { code: "fact_required", field: "currency" }];
      standing(dossier, ["missing_amount", "missing_currency"]);
    });
    try {
      await pressReason(page, "Falta el total");
      assert.ok(page.row("amount").getAttribute("data-flash"));
      assert.equal(document.activeElement, page.row("amount").querySelector("button[data-row-value]"));
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("someone who cannot edit can still read why, and no field opens", async () => {
    const page = await noCurrency(undefined, (dossier) => { dossier.capabilities = ["read"]; dossier.facts_editable = false; dossier.editable_fields = []; });
    try {
      await pressReason(page, "Falta la moneda");
      assert.equal(page.host.querySelector("[data-row-open]"), null);
      assert.equal(page.picker().disabled, true);
      assert.equal(page.host.querySelector('[data-testid="edit-amount"], [data-testid="edit-currency"]'), null);
    } finally { await page.close(); }
  });

  test("an amount saved without a currency stays on its row beside what it lacks, never as bare money", async () => {
    const page = await noCurrency();
    try {
      const shown = page.row("amount").querySelector("[data-row-value]")?.textContent;
      assert.equal(shown, "3,450.00");
      assert.equal(page.picker().getAttribute("aria-label"), "Moneda: Falta la moneda");
      await page.openRow("amount");
      await fill(page, '[data-testid="dossier-review-amount"]', "950");
      await page.check("amount");
      await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ body }) => body), [{ amount: { state: "known", value: "950" } }]);
      assert.equal(page.picker().getAttribute("aria-label"), "Moneda: Falta la moneda");
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.equal(page.picker().getAttribute("aria-label"), "Currency: Currency missing");
      await page.act(async () => { await page.i18n.changeLanguage("es-419"); });
    } finally { await page.close(); }
  });

  test("the rows a reason points at take focus the same way", async () => {
    const page = await setup("fiscalBlocked");
    try {
      await pressReason(page, "Falta la fecha");
      assert.ok(page.row("occurred_on").getAttribute("data-flash"));
      assert.equal(document.activeElement, page.row("occurred_on").querySelector("button[data-row-value]"));
    } finally { await page.close(); }
    const unpaid = await setup("fiscalBlocked", (dossier) => {
      dossier.facts.funding = unknownFact;
      dossier.blockers = [{ code: "unknown_funding", field: "funding" }];
      standing(dossier, ["blocked"]);
    });
    try {
      await pressReason(unpaid, "Tiene algo pendiente");
      assert.ok(unpaid.row("funding").getAttribute("data-flash"));
      assert.equal(document.activeElement, unpaid.row("funding").querySelector("button[data-row-value]"));
    } finally { await unpaid.close(); }
  });
});

describe("the receipt dossier on an open draft", () => {
  test("the six facts lead, then the two choices; what was removed is gone, in both languages", async () => {
    const page = await setup();
    try {
      assert.deepEqual([...page.host.querySelectorAll('[data-testid="receipt-current-facts"] [data-fact]')].map((row) => row.getAttribute("data-fact")), ["rnc", "counterparty", "fiscal_number", "occurred_on", "document_type", "category", "payment_method", "currency", "net_amount", "itbis", "amount"]);
      for (const gone of ["Confirmar", "Actividad", "Parte del negocio", "Categoría", "Cómo se pagó", "Consultar registro actual", "por revisar"]) assert.ok(!page.host.querySelector('[data-testid="business-record-review"]')?.textContent?.includes(gone), gone);
      assert.ok(page.host.querySelector('[data-testid="receipt-more"] [data-testid="receipt-mark-personal"]'), "Personal stays in Más");
      assert.ok(button(page.host, "Aceptar"), "nothing blocks this record");
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null);
      assert.equal(page.host.querySelector('[data-testid="status-pill"]')?.getAttribute("data-label"), "ready");
      assert.equal(page.host.querySelector('[data-testid="dossier-reason"], [data-testid="dossier-problems"]'), null, "no gap, no reason");
      assert.ok(page.host.querySelector('[data-testid="fiscal-declaration"]')?.closest<HTMLElement>('[data-tab-panel="fiscal"]')?.hidden, "the rest of the 606 waits in Datos fiscales");
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.ok(button(page.host, "Accept expense"));
      assert.ok(page.row("category").textContent?.includes("Expense type"));
      for (const copy of ["Tipo de gasto", "Forma de pago", "Datos fiscales"]) assert.ok(!page.host.textContent?.includes(copy), copy);
      await page.act(async () => { await page.i18n.changeLanguage("es-419"); });
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("the Spanish review uses the dictionary fact labels and official 606 options", async () => {
    const page = await setup();
    try {
      assert.equal(page.row("counterparty").firstElementChild?.textContent, "Emisor");
      assert.equal(page.row("occurred_on").firstElementChild?.textContent, "Fecha");
      const spanish = (await import("@/public/locales/es-419/common.json")).default;
      for (const field of ["category", "payment_method"] as const) {
        await page.act(async () => page.row(field).querySelector<HTMLButtonElement>("button[data-row-value]")!.click());
        const options = [...page.row(field).querySelectorAll("option")].filter((option) => option.value);
        const expected = spanish.business.dgii.option[field];
        assert.equal(options.length, Object.keys(expected).length);
        for (const option of options) assert.equal(option.textContent, expected[option.value as keyof typeof expected]);
      }
    } finally { await page.close(); }
  });

  test("the English review and 606 selects translate every backend code without Spanish option text", async () => {
    const page = await setup();
    try {
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.equal(page.row("counterparty").firstElementChild?.textContent, "Supplier");
      assert.equal(page.row("occurred_on").firstElementChild?.textContent, "Date");
      const english = (await import("@/public/locales/en/common.json")).default;
      const spanish = (await import("@/public/locales/es-419/common.json")).default;
      const fields = await page.source.dgiiFields();
      for (const field of ["category", "payment_method"] as const) {
        await page.act(async () => page.row(field).querySelector<HTMLButtonElement>("button[data-row-value]")!.click());
        const options = [...page.row(field).querySelectorAll("option")].filter((option) => option.value);
        assert.deepEqual(options.map((option) => option.value), fields["606"].find((item) => item.name === field)!.options);
        const expected = english.business.dgii.option[field];
        for (const option of options) assert.equal(option.textContent, expected[option.value as keyof typeof expected]);
        for (const label of Object.values(spanish.business.dgii.option[field])) assert.ok(!page.host.textContent?.includes(label), label);
      }
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("the status line and the row say what keeps the record from Listos, and the footer does not", async () => {
    const page = await setup("fiscalBlocked");
    try {
      assert.equal(page.host.querySelector('[data-testid="status-pill"]')?.getAttribute("data-label"), "needs_attention");
      assert.equal(page.host.querySelector('[data-testid="dossier-reason"]')?.textContent, "Falta la fecha");
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null, "the status line says it, so the footer does not");
      assert.equal(page.host.querySelector('[data-testid="business-record-review"]')?.textContent?.includes("Agrega la fecha para aceptar"), false, "nor does a line under the row");
      const status = page.row("occurred_on").querySelector('[data-testid="row-status-occurred_on"]');
      assert.equal(status?.getAttribute("data-status"), "warn", "the row keeps its mark");
      assert.equal(page.row("occurred_on").getAttribute("data-attention"), "true");
      assert.equal(button(page.host, "Aceptar").disabled, true);
      await page.openRow("occurred_on");
      await fill(page, '[placeholder="dd/mm/aaaa"]', "31/02/2026");
      await page.check("occurred_on");
      assert.equal(page.writes.length, 0, "a day that does not exist is not sent");
      assert.ok(page.row("occurred_on").querySelector('[role="alert"]')?.textContent?.includes("dd/mm/aaaa"), "and the row says why it stayed open");
      await fill(page, '[placeholder="dd/mm/aaaa"]', "16/10/2026");
      await page.check("occurred_on");
      await page.wait(() => page.writes.length === 1 && Boolean(page.row("occurred_on").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes[0].body, { occurred_on: { state: "known", value: "2026-10-16" } });
      assert.equal(button(page.host, "Aceptar").disabled, false);
      assert.equal(page.approvals(), 0, "saving never approves");
    } finally { await page.close(); }
  });

  test("ITBIS edits in place and saves on the check, carrying the other fiscal facts and the declaration unchanged", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      assert.equal(document.activeElement, page.host.querySelector('[data-testid="dossier-review-itbis"]'));
      await fill(page, '[data-testid="dossier-review-itbis"]', "500.00");
      await page.check("itbis");
      await page.wait(() => Boolean(page.row("itbis").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ kind, version }) => [kind, version]), [["fiscal", 2]]);
      const { fiscal, declaration } = page.writes[0].body as { fiscal: unknown; declaration: Record<string, unknown> };
      assert.deepEqual(fiscal, { rnc: "131999888", ncf: "B0100000099", itbis: "500.00" });
      assert.equal(declaration.form, "606");
      assert.equal(declaration.category, null);
      assert.ok(page.row("itbis").textContent?.includes("500.00"));
      assert.equal(page.host.querySelector('[data-testid="dossier-review-itbis"]'), null, "the row closes once it is saved");
      assert.equal(page.approvals(), 0);
    } finally { await page.close(); }
  });

  test("the total edits independently of the header currency; unchanged rows write nothing", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await page.check("counterparty");
      assert.equal(page.host.querySelector('[data-testid="edit-counterparty"]'), null);
      await page.openRow("amount");
      await fill(page, '[data-testid="dossier-review-amount"]', "3600");
      assert.equal(page.row("amount").querySelector("select"), null);
      await page.check("amount");
      await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ body }) => body), [{ amount: { state: "known", value: "3600" } }]);
      assert.ok(page.row("amount").textContent?.includes("3,600.00"));
    } finally { await page.close(); }
  });

  test("the two choices offer the server's labels and save with their own checks", async () => {
    const page = await setup();
    try {
      await page.openRow("category");
      await page.openRow("payment_method");
      const options = (name: string) => [...page.row(name).querySelectorAll("option")].map((option) => option.textContent);
      assert.equal(options("category").length, 12, "Elegir and José's 11");
      assert.equal(options("category")[2], "Gastos por trabajos, suministros y servicios");
      assert.equal(options("payment_method").length, 8, "Elegir and José's 7");
      assert.equal(options("payment_method")[3], "Tarjeta crédito/débito");
      assert.equal(button(page.host, "Aceptar").disabled, false, "suggested choices do not block");
      await fill(page, '[data-fact="category"] select', "05", HTMLSelectElement);
      await page.check("category");
      await page.wait(() => Boolean(page.row("category").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ kind, body }) => [kind, body]), [["purchase", { category: "05" }]]);
      await fill(page, '[data-fact="payment_method"] select', "01", HTMLSelectElement);
      await page.check("payment_method");
      await page.wait(() => Boolean(page.row("payment_method").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes[1].body, { payment_method: "01" });
      assert.equal(page.writes[1].version, page.writes[0].version + 1, "each save stands on the last one");
    } finally { await page.close(); }
  });

  const sourceIcon = (row: HTMLElement) => row.querySelector<HTMLElement>('[role="img"]');

  test("a suggestion arrives filled, with an icon that names its source and no helper line", async () => {
    const page = await setup();
    try {
      for (const [choice, code] of [["category", "02"], ["payment_method", "03"]] as const) {
        const row = page.row(choice);
        await page.openRow(choice);
        assert.equal(row.querySelector("select")?.value, code, choice);
        await page.dismiss(choice);
        const icon = sourceIcon(row);
        assert.equal(icon?.getAttribute("aria-label"), "Última elección para este RNC");
        assert.equal(icon?.getAttribute("data-status"), "last_choice");
        assert.ok(icon?.querySelector("svg.lucide-history"), "history marks the last choice");
        assert.equal(row.textContent?.includes("Sugerido"), false, "no helper line");
        assert.equal([...row.querySelectorAll("button")].some((item) => item.textContent === "Usar"), false, "no Usar");
      }
      assert.equal(page.writes.length, 0, "showing a suggestion saves nothing");
    } finally { await page.close(); }
  });

  test("each source has its own icon and accessible name", async () => {
    const page = await setup("fiscal", (dossier) => { dossier.declaration_suggestions = { category: { value: "02", source: "reading" }, payment_method: { value: "03", source: "receipt" } }; });
    try {
      const category = sourceIcon(page.row("category"));
      assert.equal(category?.getAttribute("aria-label"), "Sugerido por la lectura");
      assert.ok(category?.querySelector("svg.lucide-square-sparkles"));
      const payment = sourceIcon(page.row("payment_method"));
      assert.equal(payment?.getAttribute("aria-label"), "Leído del recibo");
      assert.ok(payment?.querySelector("svg.lucide-receipt-text"));
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.equal(sourceIcon(page.row("category"))?.getAttribute("aria-label"), "Suggested by the reading");
      assert.equal(sourceIcon(page.row("payment_method"))?.getAttribute("aria-label"), "Read from the receipt");
      await page.act(async () => { await page.i18n.changeLanguage("es-419"); });
    } finally { await page.close(); }
  });

  test("a value chosen by hand has no icon", async () => {
    const page = await setup();
    try {
      await page.openRow("payment_method");
      await fill(page, '[data-fact="payment_method"] select', "01", HTMLSelectElement);
      await page.check("payment_method");
      await page.wait(() => Boolean(page.row("payment_method").querySelector('[data-testid="row-saved"]')));
      assert.match(page.row("payment_method").querySelector("[data-row-value]")?.textContent ?? "", /Efectivo/);
      assert.equal(sourceIcon(page.row("payment_method")), null);
      assert.ok(sourceIcon(page.row("category")), "the other suggestion keeps its icon");
    } finally { await page.close(); }
  });

  test("with no suggestion each choice reads Sin dato, with no icon", async () => {
    const page = await setup("fiscal", (dossier) => { dossier.declaration_suggestions = { category: null, payment_method: null }; });
    try {
      for (const choice of ["category", "payment_method"]) {
        assert.equal(page.row(choice).querySelector("[data-row-value]")?.textContent, "Sin dato");
        await page.openRow(choice);
        const select = page.row(choice).querySelector("select")!;
        assert.equal(select.value, "");
        assert.equal(select.selectedOptions[0]?.textContent, "Elegir");
        await page.dismiss(choice);
        assert.equal(sourceIcon(page.row(choice)), null);
      }
      assert.equal(button(page.host, "Aceptar").disabled, false);
    } finally { await page.close(); }
  });

  test("an old unconfirmed tipo de gasto reads Sin dato, with no icon", async () => {
    const page = await setup("fiscal", (dossier) => {
      dossier.dgii = { form: "606", category: "09", category_suggested: true, payment_method: null };
      dossier.declaration_suggestions = { category: null, payment_method: null };
    });
    try {
      assert.equal(page.row("category").querySelector("[data-row-value]")?.textContent, "Sin dato");
      assert.equal(sourceIcon(page.row("category")), null);
    } finally { await page.close(); }
  });

  test("a saved answer keeps its source icon; a saved answer with no source has none", async () => {
    const page = await setup("fiscal", (dossier) => {
      dossier.dgii = { form: "606", category: "02", payment_method: "01", suggestion_sources: { category: "last_choice" } };
      dossier.declaration_suggestions = { category: null, payment_method: null };
    });
    try {
      assert.match(page.row("category").querySelector("[data-row-value]")?.textContent ?? "", /Gastos por trabajos/);
      assert.equal(sourceIcon(page.row("category"))?.getAttribute("aria-label"), "Última elección para este RNC");
      assert.equal(sourceIcon(page.row("payment_method")), null);
    } finally { await page.close(); }
  });

  test("edits made in a row keep their order: a second save waits for the first and takes its version", async () => {
    const order: [string, number][] = [];
    let answerFirst = () => undefined as void;
    const firstAnswered = new Promise<void>((resolve) => { answerFirst = resolve; });
    const page = await setup("fiscal", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => { order.push(["facts", version]); await firstAnswered; return fixture.reviewDraft(draft, version, facts, key); },
      reviewFiscal: async (draft, version, review, key) => { order.push(["fiscal", version]); return fixture.reviewFiscal(draft, version, review, key); },
    }));
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.openRow("fiscal_number");
      await fill(page, '[data-testid="edit-fiscal_number"] input', "e310000000777");
      await page.check("counterparty");
      assert.equal(page.action("counterparty", "Guardar").getAttribute("aria-busy"), "true", "the check shows the row working");
      await page.check("fiscal_number");
      assert.equal(page.action("fiscal_number", "Guardar").getAttribute("aria-busy"), "true", "the second row shows it is working too");
      assert.deepEqual(order, [["facts", 2]], "the second save has not gone out");
      await page.act(async () => answerFirst());
      await page.wait(() => order.length === 2 && !page.host.querySelector('[data-row-open]'));
      assert.deepEqual(order, [["facts", 2], ["fiscal", 3]]);
      assert.ok(page.row("fiscal_number").textContent?.includes("E310000000777"), "the server's clean value shows");
    } finally { await page.close(); }
  });

  test("a save that lands while the person types in another row leaves their focus in that row", async () => {
    let answerFirst = () => undefined as void;
    const firstAnswered = new Promise<void>((resolve) => { answerFirst = resolve; });
    const page = await setup("fiscal", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => { await firstAnswered; return fixture.reviewDraft(draft, version, facts, key); },
    }));
    const frames: FrameRequestCallback[] = [];
    const nextFrame = globalThis.requestAnimationFrame;
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.check("counterparty");
      await page.openRow("fiscal_number");
      await fill(page, '[data-testid="edit-fiscal_number"] input', "e310000000777");
      const typing = page.host.querySelector<HTMLInputElement>('[data-testid="edit-fiscal_number"] input');
      globalThis.requestAnimationFrame = (run) => frames.push(run);
      await page.act(async () => answerFirst());
      await page.wait(() => !page.host.querySelector('[data-testid="edit-counterparty"]'));
      frames.splice(0).forEach((run) => run(0));
      assert.equal(document.activeElement, typing, "the next key still lands in the row being typed in");
      assert.equal(typing?.value, "e310000000777");
    } finally {
      globalThis.requestAnimationFrame = nextFrame;
      await page.close();
    }
  });

  test("a refused save says what failed with its reference and the way out, and keeps what was typed", async () => {
    const page = await setup("saveRefused");
    try {
      await page.openRow("itbis");
      await fill(page, '[data-testid="dossier-review-itbis"]', "1.00");
      await page.check("itbis");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      const failure = page.row("itbis").querySelector('[data-testid="row-save-failed"]');
      assert.equal(failure?.getAttribute("role"), "alert");
      assert.ok(failure?.textContent?.includes("No se guardó ITBIS. Revisa el valor."));
      assert.ok(failure?.textContent?.includes("hola@cuadrao.ai"), "a refusal gives the contact line");
      assert.ok(failure?.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref. sample-v"));
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-itbis"]')?.value, "1.00");
      assert.equal(button(page.host, "Aceptar").disabled, true, "nothing is approved while the row shows a value the record does not hold");
      await page.dismiss("itbis");
      assert.equal(page.host.querySelector('[data-testid="row-save-failed"]'), null);
      assert.equal(button(page.host, "Aceptar").disabled, false);
      assert.ok(page.row("itbis").textContent?.includes("526.27"));
      await page.openRow("category");
      await fill(page, '[data-fact="category"] select', "05", HTMLSelectElement);
      await page.check("category");
      await page.wait(() => Boolean(page.row("category").querySelector('[data-testid="row-save-failed"]')));
      assert.equal(button(page.host, "Aceptar").disabled, true);
      await page.dismiss("category");
      assert.equal(button(page.host, "Aceptar").disabled, false, "a refused choice has a way out, so it never holds approval");
    } finally { await page.close(); }
  });

  test("a save whose answer never came pauses approval and retries with its same key and version", async () => {
    let lost = true;
    const page = await setup("fiscal", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => {
        keys.push([key, version]);
        const next = await fixture.reviewDraft(draft, version, facts, key);
        if (lost) { lost = false; throw new TypeError("the answer was lost"); }
        return next;
      },
    }));
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      const failure = page.row("counterparty").querySelector('[data-testid="row-save-failed"]')!;
      assert.ok(failure.textContent?.includes("No pudimos confirmar si Emisor se guardó."));
      assert.ok(failure.querySelector('[data-testid="error-reference"]'), "a lost answer still shows a reference");
      assert.equal(button(page.host, "Aceptar").disabled, true);
      assert.equal(page.action("counterparty", "Cancelar").disabled, true, "nothing may be dropped while its outcome is unknown");
      await page.press('[data-testid="edit-counterparty"] input', "Escape");
      assert.ok(page.host.querySelector('[data-testid="edit-counterparty"]'), "Escape drops nothing either");
      await page.act(async () => button(failure, "Reintentar").click());
      await page.wait(() => Boolean(page.row("counterparty").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(keys[1], keys[0], "the server answers one save once");
      assert.equal(button(page.host, "Aceptar").disabled, false);
      assert.ok(page.row("counterparty").textContent?.includes("Ferretería Norte"));
    } finally { await page.close(); }
  });

  test("a version conflict loads the current record, keeps the edit, and retries on the new version", async () => {
    const page = await setup("saveConcurrent", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => {
        try { return await fixture.reviewDraft(draft, version, facts, key); }
        catch (error) { if (error instanceof TypeError) throw Object.assign(new Error("stale"), { status: 409, code: "stale_version", requestId: "sample-stale" }); throw error; }
      },
    }));
    try {
      await page.openRow("amount");
      await fill(page, '[data-testid="dossier-review-amount"]', "950");
      await page.leave('[data-testid="dossier-review-amount"]');
      await page.check("amount");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      assert.ok(page.row("counterparty").textContent?.includes("Corrección de otra persona"), "the other person's change is on screen");
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-amount"]')?.value, "950.00");
      await page.act(async () => button(page.row("amount"), "Reintentar").click());
      await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-saved"]')));
      assert.ok(page.row("amount").textContent?.includes("950.00"));
    } finally { await page.close(); }
  });

  test("session recovery stops a queued row save and the old row's version check", async () => {
    const { observeBrowserAuth } = await import("@/lib/browser-auth-generation");
    observeBrowserAuth("test-review-owner");
    const reply = Promise.withResolvers<Dossier>();
    const sent: string[] = [];
    let reads = 0;
    const noNetwork = spyOn(globalThis, "fetch").mockRejectedValue(new Error("Unexpected network request"));
    let page: Awaited<ReturnType<typeof setup>> | undefined;
    try {
      page = await setup("fiscal", undefined, (fixture) => ({
        mode: "live",
        dossier: async (id) => { reads += 1; return fixture.dossier(id); },
        reviewDraft: async () => { sent.push("facts"); return reply.promise; },
        reviewPurchase: async (...args) => { sent.push("purchase"); return fixture.reviewPurchase(...args); },
      }));
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.openRow("category");
      await fill(page, '[data-fact="category"] select', "05", HTMLSelectElement);
      await page.check("category");
      assert.deepEqual(sent, ["facts"], "the expense type waits for the first row");
      const readsBeforeRetirement = reads;

      observeBrowserAuth(null);
      await page.close();
      observeBrowserAuth("test-review-owner");
      await page.act(async () => {
        reply.reject(Object.assign(new Error("stale"), { code: "stale_version", status: 409 }));
        await new Promise((resolve) => setTimeout(resolve, 400));
      });

      assert.deepEqual({ sent, reads }, { sent: ["facts"], reads: readsBeforeRetirement });
    } finally {
      await page?.close();
      observeBrowserAuth(null);
      noNetwork.mockRestore();
    }
  });

  test("a row saves only when asked: leaving the field writes nothing, and the check or Enter saves", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.leave('[data-testid="edit-counterparty"] input');
      assert.equal(page.writes.length, 0);
      assert.ok(page.host.querySelector('[data-testid="edit-counterparty"]'), "the row stays open");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.wait(() => Boolean(page.row("counterparty").querySelector('[data-testid="row-saved"]')));
      assert.equal(page.writes.length, 1);
      assert.equal(page.host.querySelector('[data-row-open]'), null);
      assert.ok(page.row("counterparty").textContent?.includes("Ferretería Norte"));
    } finally { await page.close(); }
  });

  test("the X and Escape cancel: the value comes back, nothing is sent, and focus returns to the row", async () => {
    const page = await setup();
    try {
      for (const leave of [() => page.dismiss("counterparty"), () => page.press('[data-testid="edit-counterparty"] input', "Escape")]) {
        await page.openRow("counterparty");
        assert.equal(document.activeElement, page.host.querySelector('[data-testid="edit-counterparty"] input'));
        await fill(page, '[data-testid="edit-counterparty"] input', "Otro nombre");
        await leave();
        await page.act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
        assert.equal(page.host.querySelector('[data-row-open]'), null);
        assert.ok(page.row("counterparty").textContent?.includes("Ferretería La Esquina"));
        assert.equal(document.activeElement, page.row("counterparty").querySelector("button"));
      }
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("an unsaved row holds approval and names itself beside Aceptar; an unchanged one holds nothing", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      assert.equal(button(page.host, "Aceptar").disabled, false, "nothing typed, nothing held");
      await fill(page, '[data-testid="dossier-review-itbis"]', "500.00");
      assert.equal(button(page.host, "Aceptar").disabled, true);
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]')?.textContent, "Guarda o cancela ITBIS para aceptar.");
      await page.dismiss("itbis");
      assert.equal(button(page.host, "Aceptar").disabled, false);
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null);
    } finally { await page.close(); }
  });

  test("leaving with an unsaved row warns first, by any way out; keeping stays, discarding goes", async () => {
    const page = await setup();
    const dialog = () => document.querySelector('[role="alertdialog"]');
    try {
      await page.openRow("counterparty");
      await page.act(async () => page.api().openPanel({ kind: "inbox" }));
      assert.equal(dialog(), null, "an open row with nothing typed loses nothing");
      await page.wait(() => !page.host.querySelector('[data-testid="business-record-review"]'));
    } finally { await page.close(); }
    const held = await setup();
    try {
      await held.openRow("counterparty");
      await fill(held, '[data-testid="edit-counterparty"] input', "Otro nombre");
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      assert.equal(unload.defaultPrevented, true, "a reload or a closed tab warns too");
      await held.act(async () => held.api().openPanel({ kind: "inbox" }));
      assert.ok(dialog()?.textContent?.includes("¿Descartar los cambios?"));
      await held.act(async () => button(dialog()!, "Seguir editando").click());
      assert.equal(dialog(), null);
      assert.equal(held.host.querySelector<HTMLInputElement>('[data-testid="edit-counterparty"] input')?.value, "Otro nombre", "the typed value stays");
      await held.act(async () => held.api().chooseBusiness("another-grant"));
      assert.ok(dialog(), "switching Business warns too");
      await held.act(async () => button(dialog()!, "Seguir editando").click());
      await held.act(async () => held.api().openPanel({ kind: "inbox" }));
      await held.act(async () => button(dialog()!, "Descartar cambios").click());
      await held.wait(() => !held.host.querySelector('[data-testid="business-record-review"]'));
      assert.equal(held.writes.length, 0);
    } finally { await held.close(); }
  });

  test("Tipo is a fact row: the pencil opens its two options, the check saves through the type write, the X cancels", async () => {
    const typed: { version: number; documentType: string }[] = [];
    const page = await setup("fiscal", () => undefined, (fixture) => ({ setDocumentType: async (draft, version, documentType, key) => { typed.push({ version, documentType }); return fixture.setDocumentType(draft, version, documentType, key); } }));
    try {
      assert.equal(page.host.querySelector('[role="radiogroup"], [data-segment]'), null);
      assert.match(page.row("document_type").textContent ?? "", /Tipo\s*Compra/);
      assert.equal(page.row("counterparty").firstElementChild?.textContent, "Emisor");
      await page.openRow("document_type");
      const select = () => page.row("document_type").querySelector("select")!;
      assert.deepEqual([...select().options].map((option) => option.textContent), ["Compra", "Venta"]);
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      assert.equal(typed.length, 0, "picking saves nothing");
      await page.dismiss("document_type");
      assert.equal(page.row("document_type").querySelector("select"), null);
      assert.match(page.row("document_type").textContent ?? "", /Compra/);
      assert.equal(typed.length, 0, "the X sends nothing");

      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      await page.check("document_type");
      await page.wait(() => /Venta/.test(page.row("document_type").textContent ?? ""));
      assert.deepEqual(typed.map(({ version, documentType }) => [version, documentType]), [[2, "venta"]]);
      assert.ok(page.row("document_type").querySelector('[data-testid="row-saved"]'));
      assert.equal(page.row("document_type").getAttribute("data-type"), "venta");
      assert.equal(page.row("counterparty").firstElementChild?.textContent, "Cliente");
    } finally { await page.close(); }
  });

  test("an unchanged Tipo closes without a write, and a held choice stops approval by name", async () => {
    const typed: { version: number; documentType: string }[] = [];
    const page = await setup("fiscal", () => undefined, (fixture) => ({ setDocumentType: async (draft, version, documentType, key) => { typed.push({ version, documentType }); return fixture.setDocumentType(draft, version, documentType, key); } }));
    try {
      await page.openRow("document_type");
      await page.check("document_type");
      assert.equal(page.row("document_type").querySelector("select"), null);
      assert.equal(typed.length, 0);
      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      assert.match(page.host.querySelector('[data-testid="approve-reason"]')?.textContent ?? "", /Tipo/);
    } finally { await page.close(); }
  });

  test("changing Tipo warns first while a tipo de gasto or forma de pago is set, and cancelling saves nothing", async () => {
    const warning = "Cambiar el tipo borra el tipo de gasto y la forma de pago.";
    const dialog = () => document.querySelector('[role="alertdialog"]');
    for (const choice of [{ category: "05", payment_method: null }, { category: null, payment_method: "01" }]) {
      const typed: string[] = [];
      const page = await setup("fiscal", (dossier) => { dossier.dgii = { form: "606", ...choice }; }, (fixture) => ({ setDocumentType: async (draft, version, documentType, key) => { typed.push(documentType); return fixture.setDocumentType(draft, version, documentType, key); } }));
      try {
        await page.openRow("document_type");
        await page.check("document_type");
        assert.equal(dialog(), null, "an unchanged Tipo clears nothing, so it warns nobody");
        await page.openRow("document_type");
        await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
        await page.check("document_type");
        assert.ok(dialog()?.textContent?.includes(warning), "the warning comes before the save");
        assert.deepEqual(typed, []);
        await page.act(async () => button(dialog()!, "Cancelar").click());
        assert.equal(dialog(), null);
        assert.deepEqual(typed, [], "cancelling sends nothing");
        assert.equal(page.row("document_type").querySelector("select")?.value, "venta", "the choice stays in the open row");
        await page.check("document_type");
        await page.act(async () => button(dialog()!, "Guardar").click());
        await page.wait(() => /Venta/.test(page.row("document_type").textContent ?? ""));
        assert.deepEqual(typed, ["venta"]);
        assert.equal(dialog(), null);
      } finally { await page.close(); }
    }
  });

  test("changing Tipo with neither tipo de gasto nor forma de pago set saves with no warning", async () => {
    const typed: string[] = [];
    const page = await setup("fiscal", (dossier) => { dossier.dgii = { form: "606", category: null, payment_method: null }; }, (fixture) => ({ setDocumentType: async (draft, version, documentType, key) => { typed.push(documentType); return fixture.setDocumentType(draft, version, documentType, key); } }));
    try {
      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      await page.check("document_type");
      await page.wait(() => /Venta/.test(page.row("document_type").textContent ?? ""));
      assert.equal(document.querySelector('[role="alertdialog"]'), null);
      assert.deepEqual(typed, ["venta"]);
    } finally { await page.close(); }
  });

  test("a refused choice leaves the row open and says why Aceptar is off", async () => {
    const page = await setup("saveRefused");
    const reason = () => page.host.querySelector('[data-testid="approve-reason"]');
    try {
      await page.openRow("category");
      await fill(page, '[data-fact="category"] select', "05", HTMLSelectElement);
      await page.check("category");
      await page.wait(() => Boolean(page.row("category").querySelector('[data-testid="row-save-failed"]')));
      assert.equal(button(page.host, "Aceptar").disabled, true);
      assert.equal(reason()?.textContent, "Guarda o cancela Tipo de gasto para aceptar.");
      assert.equal(button(page.host, "Aceptar").getAttribute("aria-describedby"), reason()?.id, "the button names its reason");
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.equal(reason()?.textContent, "Save or cancel Expense type to accept.");
      await page.act(async () => page.row("category").querySelector<HTMLButtonElement>('button[aria-label^="Cancel · "]')!.click());
      assert.equal(reason(), null);
      assert.equal(button(page.host, "Accept expense").disabled, false);
    } finally { await page.close(); }
  });

  test("a receipt refetch that fails after a save keeps the dossier and what another open row holds", async () => {
    let down = false;
    let refetches = 0;
    const page = await mount((fixture) => ({
      receipt: async (id, signal) => {
        refetches += 1;
        if (down) throw Object.assign(new Error("unavailable"), { status: 503, requestId: "req-refetch-down" });
        return fixture.receipt(id, signal);
      },
    }));
    const row = (name: string) => page.host.querySelector<HTMLElement>(`[data-fact="${name}"]`)!;
    const open = (name: string) => page.act(async () => row(name).querySelector<HTMLButtonElement>("button")!.click());
    const notice = () => page.host.querySelector('[data-testid="receipt-refetch-failed"]');
    const typed = '[data-fact="counterparty"] input';
    try {
      await page.open({ kind: "receipt", receiptId: "rcpt-listo-suplidora" }, () => Boolean(page.host.querySelector('[data-testid="receipt-current-facts"]')));
      await open("counterparty");
      await fill(page, typed, "Suplidora sin guardar");
      await open("itbis");
      await fill(page, '[data-testid="dossier-review-itbis"]', "100.00");
      down = true;
      const before = refetches;
      await page.act(async () => row("itbis").querySelector<HTMLButtonElement>('button[aria-label^="Guardar · "]')!.click());
      await page.wait(() => refetches > before && Boolean(notice() || page.host.querySelector('[data-testid="receipt-load-error"]')));
      assert.equal(page.host.querySelector('[data-testid="receipt-load-error"]'), null, "the error card does not replace the dossier");
      assert.ok(page.host.querySelector('[data-testid="receipt-current-facts"]'));
      assert.equal(page.host.querySelector<HTMLInputElement>(typed)?.value, "Suplidora sin guardar");
      assert.equal(notice()?.getAttribute("role"), "alert");
      assert.ok(notice()?.textContent?.includes("No pudimos actualizar."));
      assert.ok(notice()?.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
      down = false;
      await page.act(async () => button(notice()!, "Reintentar").click());
      await page.wait(() => !notice());
      assert.equal(page.host.querySelector<HTMLInputElement>(typed)?.value, "Suplidora sin guardar", "a retry keeps the open row too");
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("a receipt that never loaded still shows the error card", async () => {
    const page = await mount(() => ({ receipt: async () => { throw Object.assign(new Error("down"), { status: 500 }); } }));
    try {
      await page.open({ kind: "receipt", receiptId: "rcpt-listo-suplidora" }, () => Boolean(page.host.querySelector('[data-testid="receipt-load-error"]')));
      assert.equal(page.host.querySelector('[data-testid="receipt-refetch-failed"]'), null);
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("a refused Tipo shows its reference and keeps the server type", async () => {
    const page = await setup("fiscal", () => undefined, () => ({ setDocumentType: async () => { throw Object.assign(new Error("locked"), { status: 422, code: "document_type_locked", requestId: "req-type-locked" }); } }));
    try {
      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      await page.check("document_type");
      await page.wait(() => Boolean(page.row("document_type").querySelector('[data-testid="row-save-failed"]')));
      assert.match(page.row("document_type").textContent ?? "", /Revisa el valor/);
      assert.match(page.row("document_type").textContent ?? "", /Ref\./);
      assert.equal(page.row("document_type").getAttribute("data-type"), "recibo");
      await page.dismiss("document_type");
      assert.equal(page.row("document_type").querySelector('[data-testid="row-save-failed"]'), null);
    } finally { await page.close(); }
  });

  test("a row opened with nothing changed warns nobody; only an unsaved change holds the way out", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      assert.equal(event.defaultPrevented, false);
      await fill(page, '[data-testid="dossier-review-itbis"]', "600.00");
      const held = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(held);
      assert.equal(held.defaultPrevented, true);
    } finally { await page.close(); }
  });

  test("a record with no fiscal number marks Sin recibo through the review's facts, and takes it back", async () => {
    const page = await setup("noNumber");
    try {
      const mark = () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!;
      assert.match(page.row("fiscal_number").textContent ?? "", /Sin comprobante fiscal/);
      assert.equal(mark().textContent, "Marcar sin recibo");
      await page.act(async () => mark().click());
      await page.wait(() => /Sin recibo/.test(page.row("fiscal_number").textContent ?? ""));
      assert.deepEqual(page.writes.map(({ kind, version, body }) => [kind, version, body]), [["facts", 2, { receipt_state: { state: "known", value: "no_receipt" } }]]);
      assert.doesNotMatch(page.row("fiscal_number").textContent ?? "", /del revisor/);
      assert.ok(page.row("fiscal_number").querySelector('[data-testid="row-saved"]'));
      assert.equal(mark().textContent, "Deshacer");

      await page.act(async () => mark().click());
      await page.wait(() => /Marcar sin recibo/.test(page.row("fiscal_number").textContent ?? ""));
      assert.deepEqual(page.writes[1].body, { receipt_state: { state: "unknown", value: null } });
      assert.match(page.row("fiscal_number").textContent ?? "", /Sin comprobante fiscal/);
    } finally { await page.close(); }
  });

  test("Sin recibo never asks for an RNC: the row is blank and approval goes straight through", async () => {
    const page = await setup("noNumber");
    try {
      await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!.click());
      await page.wait(() => /Sin recibo/.test(page.row("fiscal_number").textContent ?? ""));
      assert.equal(page.row("rnc").querySelector("[data-row-value]")?.textContent, "Sin dato");
      assert.equal(page.row("rnc").querySelector('[data-testid="row-status-rnc"]'), null, "nothing asks for the RNC");
      assert.equal(page.host.querySelector('[data-testid="dossier-reason"], [data-testid="dossier-problems"]'), null);
      await page.act(async () => button(page.host, "Aceptar").click());
      assert.equal(document.querySelector('[role="alertdialog"]'), null);
      assert.equal(page.approvals(), 1);
    } finally { await page.close(); }
  });

  test("Sin recibo has no Para el 606, whether the server closes the declaration or one is already stored", async () => {
    const choices = (page: { host: Element }) => page.host.querySelector('[data-testid="receipt-facts-choices"]');
    for (const change of [() => undefined, (dossier: Dossier) => { if (dossier.sin_comprobante) Object.assign(dossier, { declaration_editable: false, dgii: { form: "606", category: "02" } }); }]) {
      const page = await setup("noNumber", change);
      try {
        assert.ok(choices(page));
        await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!.click());
        await page.wait(() => /Sin recibo/.test(page.row("fiscal_number").textContent ?? ""));
        assert.equal(choices(page), null);
      } finally { await page.close(); }
    }
  });

  test("a record with a fiscal number offers no Sin recibo mark", async () => {
    const page = await setup();
    try {
      assert.equal(page.host.querySelector('[data-testid="mark-no-receipt"]'), null);
    } finally { await page.close(); }
  });

  test("a refused Sin recibo holds approval, shows its reference under the row, and cancels", async () => {
    const page = await setup("noNumber", () => undefined, () => ({ reviewDraft: async () => { throw Object.assign(new Error("refused"), { status: 422, code: "validation_error", requestId: "req-no-receipt" }); } }));
    try {
      await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!.click());
      await page.wait(() => Boolean(page.row("fiscal_number").querySelector('[data-testid="row-save-failed"]')));
      assert.match(page.row("fiscal_number").textContent ?? "", /Ref\./);
      assert.equal(button(page.host, "Aceptar").disabled, true);
      await page.act(async () => button(page.row("fiscal_number"), "Cancelar").click());
      assert.equal(button(page.host, "Aceptar").disabled, false);
    } finally { await page.close(); }
  });

  test("Historial shows owner choices by code in the reader's language", async () => {
    const page = await setup("fiscalDeclared");
    try {
      const fold = page.host.querySelector('[data-testid="receipt-history"]');
      await page.wait(() => Boolean(fold?.querySelector('[data-testid="history-more"]')));
      await page.act(async () => fold!.querySelector<HTMLButtonElement>('[data-testid="history-more"]')!.click());
      const changes = () => fold?.querySelector('[data-testid="history-changes"]')?.textContent ?? "";
      const shown = changes();
      assert.match(shown, /Gastos por trabajos, suministros y servicios/);
      assert.match(shown, /Tarjeta crédito\/débito/);
      const values = [...fold!.querySelectorAll('[data-testid="history-change"] ins')].map((item) => item.textContent);
      assert.equal(values.includes("02"), false);
      assert.equal(values.includes("03"), false);
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      const translated = changes();
      assert.match(translated, /Work, supplies and services/);
      assert.match(translated, /Credit or debit card/);
      assert.ok(!translated.includes("Gastos por trabajos"));
      assert.ok(!translated.includes("Tarjeta crédito"));
    } finally { await page.close(); }
  });

  test("Historial owns what changed: the raw web actions are gone and the correction is there", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.check("counterparty");
      await page.wait(() => Boolean(page.row("counterparty").querySelector('[data-testid="row-saved"]')));
      const shown = page.host.querySelector('[data-testid="business-record-review"]')!;
      for (const gone of ["Revisiones en la web", "Acción enviada originalmente"]) assert.ok(!shown.textContent?.includes(gone), gone);
      assert.ok(page.host.querySelector('[data-testid="receipt-history"]')?.textContent?.includes("Ferretería Norte"));
    } finally { await page.close(); }
  });

  test("Tab walks the six facts in reading order, and a saved row hands Tab on from itself", async () => {
    const page = await setup();
    try {
      // The value opens its row; the pencil beside it is the same row's second stop.
      const stops = [...page.host.querySelectorAll<HTMLElement>('[data-testid="receipt-facts-comprobante"] button, [data-testid="receipt-facts-montos"] button')].filter((item) => item.closest("[data-fact]") && item.tabIndex === 0).map((item) => item.closest<HTMLElement>("[data-fact]")!.dataset.fact);
      assert.deepEqual(stops.filter((fact, index) => fact !== "document_type" && fact !== stops[index - 1]), ["rnc", "counterparty", "fiscal_number", "occurred_on", "currency", "net_amount", "itbis", "amount"]);
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.wait(() => document.activeElement === page.row("counterparty").querySelector("button"));
    } finally { await page.close(); }
  });

  test("the total warning follows the server amount flag and carries only its difference", async () => {
    const quiet = await setup("totalsOff");
    try { assert.equal(quiet.host.querySelector('[data-testid="row-status-amount"]'), null); } finally { await quiet.close(); }
    const page = await setup("totalsOff", (dossier) => { dossier.review_flags = [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "1.00" }]; });
    try {
      const status = page.row("amount").querySelector('[data-testid="row-status-amount"]');
      assert.equal(status?.getAttribute("data-status"), "warn");
      assert.equal(status?.getAttribute("aria-label"), "Diferencia 1.00");
    } finally { await page.close(); }
  });

  test("Corregir on a flagged value washes that value's row and puts focus on it, without opening it", async () => {
    const page = await setup("fiscal", (dossier) => standing(dossier, ["invalid_ncf"], ["invalid_ncf"]));
    try {
      await page.act(async () => button(page.host, "Aceptar").click());
      const dialog = document.querySelector('[role="alertdialog"]');
      assert.ok(dialog);
      await page.act(async () => button(dialog, "Corregir").click());
      await page.wait(() => Boolean(page.row("fiscal_number").getAttribute("data-flash")));
      assert.equal(document.querySelector('[role="alertdialog"]'), null);
      assert.equal(document.activeElement, page.row("fiscal_number").querySelector("button[data-row-value]"));
      assert.equal(page.host.querySelector('[data-testid="edit-fiscal_number"]'), null);
      assert.equal(page.approvals(), 0);
    } finally { await page.close(); }
  });

  test("prepare-only access has the locked line and no approval; read-only has no edit control", async () => {
    for (const capabilities of [["read", "prepare"], ["read"]] as const) {
      const page = await setup("fiscal", (dossier) => { dossier.capabilities = [...capabilities]; dossier.declaration_editable = capabilities.length === 2; if (!dossier.declaration_editable) { dossier.facts_editable = false; dossier.editable_fields = []; } });
      try {
        assert.equal(page.host.textContent?.includes("Puedes revisar y preparar este recibo. El dueño lo acepta."), capabilities.length === 2);
        // The footer keeps Más; it offers no approval.
        assert.ok(![...page.host.querySelectorAll('[data-testid="receipt-review-footer"] button')].some((item) => item.textContent?.startsWith("Aceptar")));
        if (capabilities.length === 1) {
          assert.equal(page.host.querySelector('[data-fact="amount"] button'), null);
          assert.equal(page.host.querySelector('[data-fact="itbis"] button'), null);
          assert.equal(page.host.querySelector('[data-fact="category"]'), null, "no declaration to read and none to write");
        }
        assert.equal(page.approvals(), 0);
      } finally { await page.close(); }
    }
  });
});
