import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import type { BusinessCapture, ReceiptSummary } from "@/lib/business-api";
import { createHttpMonthCloseClient, type MonthCloseClient } from "@/lib/business-month-close";
import type { RecordsFocus } from "@/components/business-app/transacciones/records-focus";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const shell = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined } as unknown as ChatShellBridge;
const AMOUNT = /RD\$|US\$|\d+[.,]\d{2}\b/;

async function i18n() {
  const i18next = (await import("i18next")).default;
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const instance = i18next.createInstance();
  await instance.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  return instance;
}

// ---------------------------------------------------------------- Necesita atención

async function receipts(): Promise<ReceiptSummary[]> {
  const source = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const seed = (await source.receipts("all"))[0];
  const at = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
  const listo = (index: number): ReceiptSummary => ({ ...seed, id: `listo-${index}`, channel: "web", merchant: `Ferretería ${index}`, amount: "1180.00", currency: "DOP", status: "review_ready", attention: null, received_at: at(index), email_original: false, expense_id: null, bandeja: { por_revisar: true, leyendo: false, con_problema: false }, bandeja_group: { group: "listo", reason: null, draft_id: `d${index}`, version: 1 } });
  return [
    ...[1, 2, 3, 4].map(listo),
    { ...listo(9), id: "unreadable", merchant: null, filename: "factura-escaneada.pdf", status: "needs_attention", attention: "unreadable", bandeja: { por_revisar: false, leyendo: false, con_problema: true }, bandeja_group: { group: "attention", reason: "unreadable", draft_id: null, version: null } },
    { ...listo(8), id: "itbis", merchant: "Colmado Esquina", status: "needs_attention", bandeja: { por_revisar: false, leyendo: false, con_problema: true }, bandeja_group: { group: "attention", reason: "missing_itbis", draft_id: "dx", version: 2 } },
    { ...listo(7), id: "photo", merchant: null, filename: null, channel: "whatsapp", status: "review_ready", received_at: at(0) },
  ] as ReceiptSummary[];
}

const NOTE: BusinessCapture = { draft_id: "note-1", version: 1, revision: 1, source_id: "s1", text: "Taxi al aeropuerto", received_at: new Date(Date.now() - 30_000).toISOString(), review_state: "open" } as BusinessCapture;

type AttentionOptions = { waiting?: number | null; firstDay?: boolean | null; rows?: ReceiptSummary[] | null; notes?: BusinessCapture[]; prepare?: boolean; failed?: boolean };

async function attention({ waiting = 8, firstDay = false, rows = undefined, notes = [NOTE], prepare = true, failed = false }: AttentionOptions = {}) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const { HomeAttention } = await import("@/components/business-app/inicio/HomeAttention");
  const opened: unknown[] = [];
  let uploads = 0;
  let reloads = 0;
  const inbox = rows === undefined ? await receipts() : rows;
  const value = {
    records: {
      inbox, notes, emails: [], error: failed, refused: false, failureReference: failed ? "ref-4b1d" : null, serverReference: null,
      receiptActivity: waiting === null ? null : { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: waiting, needs_attention_count: 2, ready_to_review_count: waiting - 2, bandeja_attention_count: 2, bandeja_listo_count: waiting - 2 },
    },
    openPanel: (panel: unknown) => { opened.push(panel); },
    reload: () => { reloads += 1; },
    actions: { create: [{ id: "upload_receipt", label: "Subir", run: () => { uploads += 1; } }] },
    chosen: { space_id: "s", grant_id: "g", role: "owner", name: "Ferretería", capabilities: prepare ? ["read", "prepare"] : ["read"], permissions: [] },
    panel: { kind: "overview" }, invoicing: "unavailable", receivingChannels: { email: { available: false }, whatsapp: { available: false } },
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const translation = await i18n();
  await act(async () => { root.render(createElement(I18nextProvider, { i18n: translation }, createElement(BusinessContext.Provider, { value }, createElement(BusinessSidebarNav, { shell }), createElement(HomeAttention, { firstDay })))); });
  const card = () => host.querySelector<HTMLElement>('[data-testid="home-attention"]')!;
  return { act, host, card, opened, uploads: () => uploads, reloads: () => reloads, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

describe("Necesita atención", () => {
  test("its count is the sidebar's Bandeja count, and Ver todo opens the Bandeja with no filter", async () => {
    const page = await attention();
    try {
      assert.equal(page.host.querySelector('[data-testid="home-attention-count"]')?.textContent, "8");
      assert.equal(page.host.querySelector('[data-testid="business-inbox-count"]')?.textContent, "8");
      await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="home-attention-see-all"]')!.click());
      assert.deepEqual(page.opened, [{ kind: "inbox" }]);
      assert.equal(page.card().querySelector('[data-testid="home-attention-band"]')?.className.includes("h-[57px]"), true, "one band height for both cards");
    } finally { await page.close(); }
  });

  test("up to six rows, problems first, each with its source icon, the Bandeja's reason and when it arrived, never an amount", async () => {
    const page = await attention();
    try {
      const rows = [...page.card().querySelectorAll<HTMLElement>('[data-testid="home-attention-rows"] > li')];
      assert.equal(rows.length, 6);
      assert.deepEqual(rows.slice(0, 2).map((row) => row.dataset.problem), ["true", "true"]);
      assert.match(rows[0].textContent ?? "", /Colmado Esquina.*Falta el ITBIS/, "newest first, as the Bandeja orders them");
      assert.match(rows[1].textContent ?? "", /factura-escaneada\.pdf.*No se pudo leer/);
      assert.equal(rows[0].querySelector('[data-tone="attention"]')?.firstElementChild?.className.includes("rounded-full"), true, "a problem's tag has its dot");
      assert.ok(rows.some((row) => /Foto por WhatsApp/.test(row.textContent ?? "")), "an unread WhatsApp photo names its source");
      assert.ok(rows.some((row) => /Taxi al aeropuerto.*Nota escrita/.test(row.textContent ?? "")));
      assert.ok(rows.some((row) => /Listo para revisar/.test(row.textContent ?? "")));
      for (const row of rows) assert.doesNotMatch(row.textContent ?? "", AMOUNT, "no amount or currency in a row");
      assert.deepEqual(rows.map((row) => row.querySelector('[data-testid="home-attention-verb"]')?.textContent), ["Resolver", "Resolver", "Revisar", "Revisar", "Revisar", "Revisar"]);
      await page.act(async () => rows[0].querySelector("button")!.click());
      assert.deepEqual(page.opened, [{ kind: "receipt", receiptId: "itbis", list: "inbox" }], "a row opens exactly what the Bandeja opens for it");
    } finally { await page.close(); }
  });

  test("someone who may not prepare sees the same rows without Resolver or Revisar", async () => {
    const page = await attention({ prepare: false });
    try {
      assert.equal(page.card().querySelectorAll('[data-testid="home-attention-rows"] > li').length, 6);
      assert.equal(page.card().querySelector('[data-testid="home-attention-verb"]'), null);
      assert.doesNotMatch(page.card().textContent ?? "", /Resolver|Revisar/);
    } finally { await page.close(); }
  });

  test("loading shows row shapes and no count, never Todo al día before the server counted", async () => {
    for (const options of [{ waiting: null, rows: null, notes: [] }, { rows: null }, { waiting: 0, rows: [], notes: [], firstDay: null }] as AttentionOptions[]) {
      const page = await attention(options);
      try {
        assert.ok(page.card().querySelector('[data-testid="home-attention-loading"]'));
        assert.equal(page.card().querySelector('[data-testid="home-attention-count"]'), null);
        assert.doesNotMatch(page.card().textContent ?? "", /Todo al día|Aquí verás/);
      } finally { await page.close(); }
    }
  });

  test.each([false, true])("a completed receipt read with unknown counts offers retry instead of loading (has rows: %s)", async (hasRows) => {
    const page = await attention({ waiting: null, rows: hasRows ? await receipts() : [], notes: [] });
    try {
      const error = page.card().querySelector('[data-testid="home-attention-error"]');
      assert.ok(error, "receipts loaded without activity counts is a final read error");
      assert.equal(error.getAttribute("role"), "alert");
      assert.equal(error.querySelector("p")?.textContent, "No pudimos cargar lo pendiente.");
      for (const state of ["loading", "count", "clear", "first-day", "rows"]) {
        assert.equal(page.card().querySelector(`[data-testid="home-attention-${state}"]`), null, state);
      }
      const retry = [...error.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
      assert.ok(retry);
      await page.act(async () => retry.click());
      assert.equal(page.reloads(), 1);
    } finally { await page.close(); }
  });

  test("a failed read says so with its reference and Reintentar, never a zero", async () => {
    const page = await attention({ failed: true, waiting: null });
    try {
      const error = page.card().querySelector('[data-testid="home-attention-error"]')!;
      assert.match(error.textContent ?? "", /No pudimos cargar lo pendiente\./);
      assert.match(error.textContent ?? "", /4b1d/);
      assert.equal(page.card().querySelector('[data-testid="home-attention-count"]'), null);
      await page.act(async () => [...error.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!.click());
      assert.equal(page.reloads(), 1);
    } finally { await page.close(); }
  });

  test("the first day says what the card is for, in one sentence for every channel, and starts the existing upload", async () => {
    const page = await attention({ waiting: 0, rows: [], notes: [], firstDay: true });
    try {
      const first = page.card().querySelector('[data-testid="home-attention-first-day"]')!;
      // The Bandeja's own empty state and tray art, at its in-card size.
      const shared = first.querySelector('[data-testid="reception-empty"]')!;
      assert.ok(shared, "the first day reuses the Bandeja's empty state");
      assert.equal(shared.getAttribute("data-empty-kind"), "first_run");
      assert.equal(shared.getAttribute("data-compact"), "true", "inside a card it takes the compact spacing");
      assert.match(shared.querySelector("img")?.getAttribute("src") ?? "", /inbox-empty/);
      assert.match(first.textContent ?? "", /Aquí verás lo que espera tu revisión\./);
      assert.match(first.textContent ?? "", /Cada factura o recibo nuevo aparece aquí listo para revisar\./);
      await page.act(async () => page.card().querySelector<HTMLButtonElement>('[data-testid="home-attention-add"]')!.click());
      assert.equal(page.uploads(), 1);
    } finally { await page.close(); }
  });

  test("all caught up says so with no button, and stays short", async () => {
    const page = await attention({ waiting: 0, rows: [], notes: [], firstDay: false });
    try {
      const clear = page.card().querySelector('[data-testid="home-attention-clear"]')!;
      assert.match(clear.textContent ?? "", /Todo al día.*Nada espera tu revisión\./);
      assert.equal(page.card().querySelector("img"), null, "only the first day gets art");
      assert.equal(page.card().querySelector("[data-testid='home-attention-clear'] button"), null);
    } finally { await page.close(); }
  });
});

// ---------------------------------------------------------------- The month card

const MONTH = "2026-11";
function dop(overrides: Record<string, unknown> = {}) {
  return { currency: "DOP", income_before_itbis_minor: 26804350, expense_before_itbis_minor: 31580512, net_result_minor: -4776162, itbis_charged_minor: 4824840, itbis_paid_minor: 5684520, net_result_final: true, documents_counted: 21, documents_total: 28, documents_in_bandeja: 6, ...overrides };
}

function server(month: Record<string, unknown> = {}): MonthCloseClient {
  return createHttpMonthCloseClient(async (path) => {
    if (path.startsWith("/business/open-items")) throw new Error("settlement is off");
    return { month: MONTH, today: "2026-11-09", from: "2026-11-01", to: "2026-11-30", closed: false, reasons: [], earliest_month: "2026-10", dgii_forms: { "606": "needs_review", "607": "prepared_candidate" }, currencies: [dop()], missing_rnc: [], missing_ncf: [], missing_fiscal_rows: [{ family: "purchase", currency: "DOP", count: 3, by_currency: false }], unreviewed_movements_count: 6, ...month };
  });
}

async function monthCard(client: MonthCloseClient, prepares = true, businessId?: string) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessMonthCloseView } = await import("@/components/business-app/BusinessMonthClosePanel");
  const opened: (RecordsFocus | "bandeja")[] = [];
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const translation = await i18n();
  await act(async () => { root.render(createElement(I18nextProvider, { i18n: translation }, createElement(BusinessMonthCloseView, { client, now: new Date(2026, 10, 9, 12), scopeKey: `own-${Math.random()}`, businessId, businessCurrency: "DOP", settlement: false, layout: "finance", openRecords: prepares ? (focus: RecordsFocus) => { opened.push(focus); } : undefined, openBandeja: prepares ? () => { opened.push("bandeja"); } : undefined }))); });
  for (let index = 0; index < 10; index += 1) await act(async () => { await Promise.resolve(); });
  const find = (id: string) => host.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  return { act, host, find, opened, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

describe("The month card", () => {
  test("its figures are whole units, the net is the largest and right-aligned, with no caption", async () => {
    const page = await monthCard(server());
    try {
      assert.equal(page.find("home-month-income")?.textContent, "RD$ 268,044", "26,804,350 minor rounds half up from the text");
      assert.equal(page.find("home-month-expenses")?.textContent, "RD$ 315,805");
      assert.equal(page.find("home-month-net")?.textContent, "-RD$ 47,762", "a plain minus, no color");
      assert.equal(page.find("home-month-net")?.closest("p")?.className.includes("text-right"), true);
      assert.ok(page.find("home-month-net")?.className.includes("text-[34px]"));
      assert.equal(page.find("home-month-itbis-sales")?.textContent, "RD$ 48,248");
      assert.equal(page.find("home-month-itbis-purchases")?.textContent, "RD$ 56,845");
      assert.doesNotMatch(page.find("home-month")?.textContent ?? "", /Ingresos menos gastos aprobados|por marcar|Ya tienes todo|Para cerrar|Cerrar mes|Mes cerrado/);
      assert.equal(page.find("home-month-band")?.className.includes("h-[57px]"), true);
    } finally { await page.close(); }
  });

  test("hover or focus on a number shows the exact amount, and a non-zero amount under one unit says so", async () => {
    const page = await monthCard(server({ currencies: [dop({ income_before_itbis_minor: 49, itbis_paid_minor: 50 })] }));
    try {
      assert.equal(page.find("home-month-income")?.textContent, "menos de RD$ 1", "never RD$ 0 for a real amount");
      assert.equal(page.find("home-month-itbis-purchases")?.textContent, "RD$ 1", "0.50 rounds half up");
      await page.act(async () => { page.find("home-month-income")!.focus(); await new Promise((resolve) => setTimeout(resolve, 350)); });
      assert.match(document.body.textContent ?? "", /RD\$ 0\.49/);
    } finally { await page.close(); }
  });

  test("each footer count opens exactly what it counts", async () => {
    const page = await monthCard(server());
    try {
      assert.equal(page.find("home-month-included")?.textContent, "Documentos incluidos: 21 de 28");
      assert.match(page.find("home-month-bandeja")?.textContent ?? "", /^6 en la Bandeja · Revisar$/);
      const [fiscal] = [...page.host.querySelectorAll<HTMLElement>('[data-testid="home-month-fiscal"]')];
      assert.match(fiscal.textContent ?? "", /^Faltan datos fiscales en 3 registros · Ver$/);
      await page.act(async () => page.find("home-month-bandeja-open")!.click());
      await page.act(async () => page.find("home-month-fiscal-open")!.click());
      assert.deepEqual(page.opened, ["bandeja", { family: "purchase", currency: "DOP", from: "2026-11-01", to: "2026-11-30", fiscal_data: "missing" }]);
    } finally { await page.close(); }
  });

  test("every document counted reads in the same shape; nothing in the Bandeja or held shows no line", async () => {
    const page = await monthCard(server({ currencies: [dop({ documents_counted: 28, documents_total: 28, documents_in_bandeja: 0 })], missing_fiscal_rows: [], unreviewed_movements_count: 0 }));
    try {
      assert.equal(page.find("home-month-included")?.textContent, "Documentos incluidos: 28 de 28");
      assert.equal(page.find("home-month-bandeja"), null);
      assert.equal(page.find("home-month-fiscal"), null);
    } finally { await page.close(); }
  });

  test("someone who may not prepare reads the same counts with no links", async () => {
    const page = await monthCard(server(), false);
    try {
      assert.match(page.find("home-month-bandeja")?.textContent ?? "", /^6 en la Bandeja$/);
      assert.equal(page.find("home-month-fiscal-open"), null);
      assert.equal(page.find("home-month-bandeja-open"), null);
    } finally { await page.close(); }
  });

  test("with two currencies the pill shows the ISO code and the list names each with its document count", async () => {
    const usd = dop({ currency: "USD", income_before_itbis_minor: 120000, expense_before_itbis_minor: 2400, net_result_minor: 117600, net_result_final: false, documents_counted: 2, documents_total: 3, documents_in_bandeja: 1 });
    const page = await monthCard(server({ currencies: [dop(), usd] }));
    try {
      const pill = page.find("month-close-currency")!;
      assert.equal(pill.textContent, "DOP");
      assert.equal(page.find("month-close-currency-others"), null, "no line naming the other currencies");
      await page.act(async () => pill.click());
      const options = [...document.querySelectorAll('[data-testid="month-close-currency-picker"] [role="option"]')].map((option) => option.textContent);
      assert.deepEqual(options, ["DOP · Peso dominicano28", "USD · Dólar estadounidense3"]);
    } finally { await page.close(); }
  });

  test("a single currency has no pill", async () => {
    const page = await monthCard(server());
    try {
      assert.equal(page.find("month-close-currency"), null);
    } finally { await page.close(); }
  });

  test("the first day keeps the structure: muted zeros and when the figures fill", async () => {
    const page = await monthCard(server({ earliest_month: null, currencies: [], missing_fiscal_rows: [], unreviewed_movements_count: 0 }));
    try {
      for (const id of ["home-month-income", "home-month-expenses", "home-month-net", "home-month-itbis-sales", "home-month-itbis-purchases"]) {
        assert.equal(page.find(id)?.textContent, "RD$ 0", id);
        assert.ok(page.find(id)?.className.includes("text-[#7d8a84]"), `${id} is muted`);
      }
      assert.equal(page.find("home-month-first-day")?.textContent, "Las cifras se llenan cuando apruebes tus primeros documentos.");
      assert.equal(page.find("home-month-included"), null);
    } finally { await page.close(); }
  });

  test("while it loads, the labels and the month are there and only the numbers are bars", async () => {
    const page = await monthCard(createHttpMonthCloseClient(() => new Promise(() => undefined)));
    try {
      const card = page.find("home-month")!;
      assert.equal(page.find("home-month-body")?.dataset.state, "loading");
      assert.match(card.textContent ?? "", /Noviembre 2026/);
      assert.match(card.textContent ?? "", /Ingresos.*Gastos.*Resultado neto.*ITBIS en ventas.*ITBIS en compras/);
      assert.doesNotMatch(card.textContent ?? "", /RD\$|Documentos incluidos/);
      assert.equal(page.find("month-close-currency"), null, "nothing reserves room for a pill that may not appear");
    } finally { await page.close(); }
  });
});

describe("Inicio reads at a glance", () => {
  test("both cards take the type one step up, from one set of sizes", async () => {
    const { HOME_TYPE } = await import("@/components/business-app/inicio/HomeCard");
    assert.deepEqual({ ...HOME_TYPE }, { title: "text-[18px]", label: "text-[16px]", rowTitle: "text-[16px]", tag: "text-[13px]", secondary: "text-[14px]", action: "text-[15px]", figure: "text-[22px]", itbisFigure: "text-[19px]", net: "text-[34px]", footer: "text-[15px]", included: "text-[14px]" });
    const page = await monthCard(server());
    try {
      const has = (id: string, size: string) => assert.ok(page.find(id)?.className.split(" ").includes(size), `${id} at ${size}`);
      has("home-month-income", HOME_TYPE.figure);
      has("home-month-expenses", HOME_TYPE.figure);
      has("home-month-itbis-sales", HOME_TYPE.itbisFigure);
      has("home-month-itbis-purchases", HOME_TYPE.itbisFigure);
      has("home-month-net", HOME_TYPE.net);
      has("home-month-footer", HOME_TYPE.footer);
      has("home-month-included", HOME_TYPE.included);
      for (const row of page.host.querySelectorAll<HTMLElement>('[data-testid="home-month-body"] .justify-between')) assert.ok(row.className.includes(HOME_TYPE.label), "labels at 16px");
    } finally { await page.close(); }
    const card = await attention();
    try {
      const first = card.card().querySelector('[data-testid="home-attention-rows"] > li')!;
      assert.ok(first.querySelector('[data-testid="home-attention-title"]')!.className.includes(HOME_TYPE.rowTitle));
      assert.ok(first.querySelector('[data-testid="home-attention-time"]')!.className.includes(HOME_TYPE.secondary));
      assert.ok(first.querySelector('[data-tone="attention"]')!.className.includes(HOME_TYPE.tag));
      assert.ok(first.querySelector("button")!.className.includes("min-h-[62px]"), "rows stay about 60 to 64px");
    } finally { await card.close(); }
    const { readFileSync } = await import("node:fs");
    const panel = readFileSync(new URL("../components/business-app/BusinessOverviewPanel.tsx", import.meta.url).pathname, "utf8");
    assert.match(panel, /grid-cols-\[minmax\(0,1fr\)_440px\]/, "the month card's column is 440px; Necesita atención takes the rest");
  });
});

describe("the chosen currency across months", () => {
  /** November and September hold pesos and dollars; October only pesos. */
  function months(): MonthCloseClient {
    return createHttpMonthCloseClient(async (path) => {
      const month = new URLSearchParams(path.split("?")[1]).get("month")!;
      const usd = dop({ currency: "USD", income_before_itbis_minor: month === "2026-09" ? 50000 : 120000, documents_counted: 1, documents_total: 1, documents_in_bandeja: 0 });
      return { month, today: "2026-11-09", from: `${month}-01`, to: `${month}-30`, closed: false, reasons: [], earliest_month: "2026-09", more_than_one_currency: true, dgii_forms: { "606": "no_operations", "607": "no_operations" }, currencies: month === "2026-10" ? [dop()] : [dop(), usd], missing_rnc: [], missing_ncf: [], missing_fiscal_rows: [] };
    });
  }

  test("it stays chosen while the person moves between months, falls back where a month lacks it, and comes back", async () => {
    const page = await monthCard(months(), true, "business-flip");
    const shown = () => page.find("home-month-body")?.dataset.currency;
    const step = async (direction: "prev" | "next") => {
      await page.act(async () => page.find(`month-close-month-${direction}`)!.click());
      for (let index = 0; index < 10; index += 1) await page.act(async () => { await Promise.resolve(); });
    };
    try {
      assert.equal(shown(), "DOP");
      await page.act(async () => page.find("month-close-currency")!.click());
      await page.act(async () => document.querySelector<HTMLElement>('[data-testid="month-close-currency-picker"] [data-currency="USD"]')!.click());
      assert.equal(shown(), "USD");
      await step("prev");
      assert.equal(page.find("month-close-month")?.textContent, "Octubre 2026");
      assert.equal(shown(), "DOP", "October holds no dollars: the Business's own currency");
      assert.equal(page.find("month-close-currency")?.textContent, "DOP", "the pill stays in view, on the Business's currency");
      await page.act(async () => page.find("month-close-currency")!.click());
      assert.deepEqual([...document.querySelectorAll('[data-testid="month-close-currency-picker"] [role="option"]')].map((option) => option.getAttribute("data-currency")), ["DOP"], "the list is this month's currencies");
      await page.act(async () => page.find("month-close-currency")!.click());
      await step("prev");
      assert.equal(shown(), "USD", "September holds dollars again: the choice comes back");
      assert.equal(page.find("home-month-income")?.textContent, "US$ 500");
      await step("next");
      await step("next");
      assert.equal(page.find("month-close-month")?.textContent, "Noviembre 2026");
      assert.equal(shown(), "USD");
    } finally { await page.close(); }
    const other = await monthCard(months(), true, "another-business");
    try {
      assert.equal(other.find("home-month-body")?.dataset.currency, "DOP", "each Business keeps its own choice");
    } finally { await other.close(); }
  });
});

describe("the month card's second round (Lucas, 2026-11-09)", () => {
  test("a net in its own currency shows, as the server says it is final", async () => {
    const usd = dop({ currency: "USD", income_before_itbis_minor: 150500, expense_before_itbis_minor: 7600, net_result_minor: 142900, net_result_final: true });
    const page = await monthCard(server({ currencies: [usd], missing_fiscal_rows: [] }));
    try {
      assert.equal(page.find("home-month-income")?.textContent, "US$ 1,505");
      assert.equal(page.find("home-month-net")?.textContent, "US$ 1,429");
    } finally { await page.close(); }
  });

  test("with both tabs held, each fiscal line names its tab and opens it", async () => {
    const rows = [{ family: "purchase", currency: "DOP", count: 1, by_currency: false }, { family: "sale", currency: "DOP", count: 2, by_currency: false }];
    const page = await monthCard(server({ missing_fiscal_rows: rows }));
    try {
      const lines = [...page.host.querySelectorAll<HTMLElement>('[data-testid="home-month-fiscal"]')];
      assert.deepEqual(lines.map((line) => line.textContent), ["Faltan datos fiscales en 1 compra · Ver", "Faltan datos fiscales en 2 ventas · Ver"]);
      assert.ok(lines.every((line) => line.querySelector('[tabindex="0"]')?.className.includes("decoration-dotted")), "the term keeps its dotted tooltip");
      for (const line of lines) await page.act(async () => line.querySelector<HTMLButtonElement>('[data-testid="home-month-fiscal-open"]')!.click());
      assert.deepEqual(page.opened.map((focus) => (typeof focus === "string" ? focus : focus.family)), ["purchase", "sale"]);
    } finally { await page.close(); }
    const single = await monthCard(server({ missing_fiscal_rows: [{ family: "purchase", currency: "DOP", count: 1, by_currency: false }] }));
    try {
      assert.equal(single.find("home-month-fiscal")?.textContent, "Faltan datos fiscales en 1 registro · Ver", "one tab needs no name");
    } finally { await single.close(); }
  });

  test("a fiscal line counts and opens only the shown currency's records", async () => {
    const usd = dop({ currency: "USD", documents_counted: 1, documents_total: 2, documents_in_bandeja: 0 });
    const rows = [{ family: "purchase", currency: "DOP", count: 3, by_currency: true }, { family: "purchase", currency: "USD", count: 1, by_currency: true }];
    const page = await monthCard(server({ currencies: [dop(), usd], more_than_one_currency: true, missing_fiscal_rows: rows }), true, "business-fiscal-currency");
    const lines = () => [...page.host.querySelectorAll<HTMLElement>('[data-testid="home-month-fiscal"]')].map((line) => line.textContent);
    try {
      assert.deepEqual(lines(), ["Faltan datos fiscales en 3 registros · Ver"], "pesos shown: only the pesos row");
      await page.act(async () => page.find("month-close-currency")!.click());
      await page.act(async () => document.querySelector<HTMLElement>('[data-testid="month-close-currency-picker"] [data-currency="USD"]')!.click());
      assert.equal(page.find("home-month-body")?.dataset.currency, "USD");
      assert.deepEqual(lines(), ["Faltan datos fiscales en 1 registro · Ver"], "dollars shown: only the dollars row");
      await page.act(async () => page.find("home-month-fiscal-open")!.click());
      assert.deepEqual(page.opened, [{ family: "purchase", currency: "USD", from: "2026-11-01", to: "2026-11-30", fiscal_data: "missing" }], "Ver opens Registros in the row's currency");
    } finally { await page.close(); }
  });

  test("the pill shows whenever the Business holds a second currency in some month, and never otherwise", async () => {
    const held = await monthCard(server({ more_than_one_currency: true }));
    try {
      assert.equal(held.find("month-close-currency")?.textContent, "DOP");
    } finally { await held.close(); }
    const never = await monthCard(server({ more_than_one_currency: false }));
    try {
      assert.equal(never.find("month-close-currency"), null);
    } finally { await never.close(); }
  });
});

describe("what Inicio no longer has", () => {
  test("Para cerrar, closing a sample month, Personalizar Inicio and Continuar trabajando are gone, with their copy", async () => {
    const { existsSync, readFileSync } = await import("node:fs");
    const here = (path: string) => new URL(`../${path}`, import.meta.url).pathname;
    for (const path of ["components/business-app/inicio/HomeOverviewDraft.tsx", "components/business-app/inicio/home-draft-data.ts", "components/business-app/inicio/useHomeCounts.ts"]) {
      assert.equal(existsSync(here(path)), false, path);
    }
    const { STORAGE_REGISTRY } = await import("@/lib/browser-storage");
    assert.equal("cuadrao:home_section_order:v1" in STORAGE_REGISTRY, false, "no saved Inicio order");
    const panel = readFileSync(here("components/business-app/BusinessMonthClosePanel.tsx"), "utf8");
    for (const gone of ["checklistCard", "month-close-checklist", "filing_ready", "closed_at", "month-close-closed"]) assert.equal(panel.includes(gone), false, gone);
    const spanish = (await import("@/public/locales/es-419/common.json")).default as { business: { month_close: Record<string, unknown> } };
    for (const key of ["filing_ready", "checklist_title", "closed", "closed_on", "currency_others"]) assert.equal(key in spanish.business.month_close, false, key);
    const inicio = (spanish as unknown as { business: { inicio: { attention: Record<string, unknown>; month: Record<string, unknown> } } }).business.inicio;
    assert.equal("first_day_channels" in inicio.attention, false, "one first-day sentence for every channel");
    assert.deepEqual(Object.keys(inicio.month).filter((key) => key.startsWith("included")), ["included"], "one coverage line shape");
    assert.doesNotMatch(JSON.stringify(inicio), /PENDIENTE COPY/);
    const sample = (await import("@/lib/business-month-close")).createMockMonthCloseClient();
    assert.equal("closeMonth" in sample, false);
  });
});
