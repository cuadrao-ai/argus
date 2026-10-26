import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, beforeEach, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { TransaccionesSource } from "@/components/business-app/transacciones/transacciones-model";

// The real workspace over the sample source: the rail, the top bar and the
// panel router, with Transacciones' igualar parts behind their gate.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

/** The person's profile, standing in for `GET` and `PATCH /me`. */
const profile = { stored: "normal" as unknown, writes: [] as string[], refuse: false };

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
beforeEach(async () => {
  Object.assign(profile, { stored: "normal", writes: [], refuse: false });
  // Another file in the same run may have kept a currency for the own Business.
  (await import("@/lib/business-currency-view")).resetCurrencyViews();
  (await import("@/components/business-app/transacciones/table-density")).resetTableDensity({
    read: async () => profile.stored,
    write: async (next) => {
      profile.writes.push(next);
      if (profile.refuse) throw Object.assign(new Error("refused"), { status: 503 });
      profile.stored = next;
    },
  });
});
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  (await import("@/components/business-app/foundation/toasts")).clearToasts();
  (await import("@/lib/business-currency-view")).resetCurrencyViews();
  document.body.innerHTML = "";
  search = "";
});

async function mount({ enabled = true, width = 1440, language = "es-419", transacciones, view = "transactions", porIgualarCount, businessCurrency, expenseRead }: { expenseRead?: BusinessDataSource["expense"]; enabled?: boolean; width?: number; language?: string; transacciones?: TransaccionesSource; view?: string | null; porIgualarCount?: number | null; businessCurrency?: string } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  search = view ? `view=${view}` : "";
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { IgualarGate } = await import("@/components/business-app/transacciones/transacciones-gate");
  const { TransaccionesSourceOverride } = await import("@/components/business-app/transacciones/useTransacciones");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: (await import("@/public/locales/en/common.json")).default } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = {
    ...fixture,
    ...(expenseRead ? { expense: expenseRead } : {}),
    // The Business currency only when a test names it; without it the table lists every currency, as with an older server.
    workspace: async () => {
      const workspace: Record<string, unknown> = { ...(await fixture.workspace()) };
      delete workspace.currency;
      return businessCurrency ? { ...workspace, currency: businessCurrency } : workspace;
    },
    captures: async () => ({ items: [] }),
    receiptPage: porIgualarCount === undefined ? fixture.receiptPage : async (view: "inbox" | "all") => {
      const page = await fixture.receiptPage!(view);
      return { ...page, activity: page.activity ? { ...page.activity, por_igualar_count: porIgualarCount } : page.activity };
    },
  };
  const below = width < 720;
  const shell = { currentView: "workspace", conversationId: null, isBelowTablet: below, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined, openSearch: undefined };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Chrome() {
    const workspace = useChatWorkspace();
    return (
      <>
        <aside data-testid="rail">{workspace?.sidebarNav?.(shell as never)}</aside>
        <header data-testid="top-bar">{below ? null : workspace?.headerSearch?.(shell as never)}{workspace?.headerActions?.(shell as never)}</header>
        {below ? <footer data-testid="tabs">{workspace?.bottomNavigation?.(shell as never)}</footer> : null}
      </>
    );
  }
  function Probe() {
    api = useBusiness();
    return <div data-testid="screen"><BusinessPanel /></div>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const panel = (
    <BusinessWorkspaceProvider source={source as unknown as BusinessDataSource}>
      <Chrome />
      <Probe />
      <ToastViewport />
    </BusinessWorkspaceProvider>
  );
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <BusinessConsentTestProvider accepted>
        <IgualarGate enabled={enabled}>
          {transacciones ? <TransaccionesSourceOverride source={transacciones}>{panel}</TransaccionesSourceOverride> : panel}
        </IgualarGate>
      </BusinessConsentTestProvider>
    </I18nextProvider>,
  ));
  let mounted = true;
  const unmount = async () => { if (mounted) { mounted = false; await act(async () => root.unmount()); } };
  unmounts.push(unmount);
  const settle = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}: ${document.body.textContent?.slice(0, 400)}`);
  };
  const screen = () => host.querySelector<HTMLElement>('[data-testid="transacciones"]');
  const grid = () => document.querySelector<HTMLElement>('[data-testid="transacciones-grid"]');
  const row = (id: string) => document.querySelector<HTMLElement>(`[data-movement-id="${id}"]`);
  const records = () => [...document.querySelectorAll<HTMLElement>("[data-record-id]")];
  const rows = () => [...document.querySelectorAll<HTMLElement>("[data-movement-id]")];
  const segment = (key: string) => document.querySelector<HTMLButtonElement>(`[data-testid="transacciones-segments"] [data-segment="${key}"]`);
  const ready = () => settle(() => rows().length > 0, "the movements");
  const click = (node: Element | null) => act(async () => { (node as HTMLElement).click(); });
  const key = (target: Element, value: string) => act(async () => { target.dispatchEvent(new KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true })); });
  const body = () => document.body.textContent ?? "";
  return { act, host, screen, grid, row, rows, records, segment, ready, settle, click, key, body, unmount, api: () => api! };
}

const EMPTY_OVERVIEW = { from: "2026-10-01", to: "2026-10-20", today: "2026-10-20", totals: [], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null };

type Saved = Parameters<typeof import("@/components/business-app/transacciones/transacciones-adapter")["createRecordsTransaccionesSource"]>[0]["expenses"] extends (...args: never[]) => Promise<infer T> ? T : never;

async function recordsOf(expenses: Saved, overview: object = EMPTY_OVERVIEW, ventas: Saved = []) {
  const { createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
  return createRecordsTransaccionesSource({ expenses: async () => expenses, ventas: async () => ventas, overview: async () => ({ ...EMPTY_OVERVIEW, ...overview }), workspace: async () => ({ accounts: [] }), ownerFunds: "Dinero del dueño" });
}

/** The sample bank through the real adapter, with every request it was sent. */
async function bank(options: Parameters<typeof import("@/components/business-app/transacciones/transacciones-sample")["createSampleBankServer"]>[0] = {}, intercept?: (path: string, init?: RequestInit) => unknown) {
  const { createSampleBankServer } = await import("@/components/business-app/transacciones/transacciones-sample");
  const { createBankTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
  const server = createSampleBankServer(options);
  const calls: { path: string; method: string; key: string | null }[] = [];
  const fetchJson = async <T,>(path: string, init?: RequestInit): Promise<T> => {
    calls.push({ path, method: init?.method ?? "GET", key: new Headers(init?.headers).get("Idempotency-Key") });
    const answer = intercept?.(path, init);
    if (answer instanceof Error) throw answer;
    return server<T>(path, init);
  };
  return { source: createBankTransaccionesSource(fetchJson, await recordsOf([])), calls };
}

const refusal = (status: number, code: string) => Object.assign(new Error(code), { status, code });

describe("the gate", () => {
  test("with igualar off, the third screen is still Transacciones: the period's saved gastos and ventas, no igualar parts, Entradas unknown", async () => {
    const page = await mount({ enabled: false });
    const rail = page.host.querySelector('[data-testid="business-sidebar-nav"]')!;
    assert.ok([...rail.querySelectorAll("button")].some((button) => button.textContent?.includes("Registros")), "the rail names Registros");
    assert.ok(!rail.textContent?.includes("Gastos"));
    await page.settle(() => page.records().length > 0, "the saved records");
    assert.equal(page.host.querySelector('[data-testid="top-bar"] h1')?.textContent, "Registros");
    await page.settle(() => page.records().some((node) => node.dataset.kind === "venta"), "the ventas");
    assert.deepEqual([...new Set(page.records().map((node) => node.dataset.kind))].sort(), ["gasto", "venta"], "the ventas come from the expenses read with kind=income");
    for (const absent of ["transacciones-segments", "transacciones-run", "transacciones-grid"]) assert.equal(document.querySelector(`[data-testid="${absent}"]`), null, `${absent} stays behind the flag`);
    assert.doesNotMatch(page.body(), /Banco al día|Por igualar|Igualadas|¿Este\?|Igualar sugerencias/);
    const summary = document.querySelector<HTMLElement>('[data-testid="transacciones-summary"]')!;
    assert.deepEqual([...summary.querySelectorAll("[data-total]")].map((cell) => cell.getAttribute("data-total")), ["entradas", "salidas"]);
    assert.equal(summary.querySelector('[data-total="entradas"] dd')?.textContent, "-sin dato");
    assert.match(summary.querySelector('[data-total="salidas"]')?.textContent ?? "", /RD\$\s?\d/);
  });

  test("long money widens its column and full account/detail labels remain available in tooltips", async () => {
    const source = await recordsOf([{ id: "long-money", merchant: "Sample supplier", amount: "123456789012345.67", currency: "USD", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null, funding: "owner_funds", personal: true, personal_marked_by: "Ana", fiscal_known: true, fiscal_value: null }]);
    const page = await mount({ enabled: false, transacciones: source });
    await page.settle(() => page.records().length === 1, "the saved record");
    const row = page.records()[0];
    const table = row.closest("table")!;
    assert.match(table.querySelectorAll("col")[2].style.width, /ch/);
    assert.match(table.style.minWidth, /1088px/);
    assert.match(row.querySelector('[data-col="monto"]')!.textContent ?? "", /123,456,789,012,345\.67/);
    const account = row.querySelector('[data-col="cuenta"] .truncate')!;
    const detail = row.querySelector('[data-col="detalle"] > span')!;
    for (const [target, expected] of [[account, /Dinero del dueño/], [detail, /Gasto · Personal · Falta NCF · Marcado por Ana/]] as const) {
      await page.act(async () => { target.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); await new Promise((resolve) => setTimeout(resolve, 330)); });
      assert.match(document.querySelector('[role="tooltip"]')?.textContent ?? "", expected);
      await page.act(async () => target.dispatchEvent(new MouseEvent("mouseout", { bubbles: true })));
    }
    assert.equal(row.style.height, "48px");
  });

  test("local preview paginates 65 real supplied rows and resets page without resetting density", async () => {
    const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
    Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
    try {
      const items = Array.from({ length: 65 }, (_, index) => ({ id: `page-${index}`, merchant: `Sample ${index}`, amount: "24.00", currency: "USD", category_id: null, account_id: null, occurred_on: `2026-10-${String(index % 20 + 1).padStart(2, "0")}`, receipt_id: null }));
      const page = await mount({ enabled: false, transacciones: await recordsOf(items) });
      await page.settle(() => page.records().length === 25, "first local page");
      const footer = () => document.querySelector<HTMLElement>('[data-testid="records-pagination"]')!;
      assert.match(footer().textContent ?? "", /1–25 de 65/);
      const resultSummary = () => document.querySelector('[data-testid="records-results-summary"]')?.textContent ?? null;
      const allResults = resultSummary();
      assert.equal(allResults, null, "Todos hides the financial summary");
      assert.doesNotMatch(allResults ?? "", /0 por revisar/);
      assert.equal(document.querySelector('th[data-col="cuenta"]'), null);
      assert.equal(document.querySelector('th[data-col="detalle"]')?.textContent, "Tipo");
      assert.equal(document.querySelector('th[data-col="monto"]')?.textContent, "Monto");
      assert.match(page.records()[0].querySelector('[data-col="estado"]')!.textContent ?? "", /Estado no disponible/);
      await page.click(document.querySelector('button[aria-label="Página siguiente"]'));
      assert.match(footer().textContent ?? "", /26–50 de 65/);
      assert.equal(resultSummary(), allResults, "summary covers all results, not the selected page");
      await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
      await page.click([...document.querySelectorAll('button[role="radio"]')].find((node) => node.textContent === "Altura de filas")!);
      await page.click([...document.querySelectorAll("label")].find((node) => node.textContent === "Compacto")!);
      assert.equal(document.querySelector<HTMLElement>('[data-testid="transacciones-records"]')!.dataset.density, "compacto");
      assert.deepEqual(profile.writes, [], "local preview density never writes the profile");
      await page.click([...document.querySelectorAll('button[role="radio"]')].find((node) => node.textContent === "Columnas")!);
      assert.ok(document.querySelector('[role="dialog"] [role="radiogroup"]'));
      assert.ok(document.querySelector('[role="dialog"] section[aria-label="Columnas"]'));
      assert.equal(document.querySelector('[role="dialog"] [role="tabpanel"]'), null);
      const category = document.querySelector('[data-column-setting="categoria"] label')!;
      await page.click(category);
      assert.equal(document.querySelector('th[data-col="categoria"]'), null);
      assert.equal(page.records()[0].querySelector('[data-col="categoria"]'), null);
      assert.equal(document.querySelectorAll('colgroup col').length, 8);
      assert.equal(document.querySelector('[data-column-setting="monto"] input'), null);
      assert.equal(document.querySelector('[data-column-setting="contraparte"] input'), null);
      assert.match(document.querySelector('[data-column-setting="monto"]')!.textContent ?? "", /Siempre visible/);
      assert.equal(document.querySelector('[data-column-setting="contraparte"] button'), null);
      const categoryGrip = document.querySelector('[data-column-setting="categoria"] button')!;
      assert.equal(categoryGrip.closest("label"), null, "reorder grip is separate from the checkbox label");
      await page.click(categoryGrip);
      assert.equal((category.querySelector("input") as HTMLInputElement).checked, false, "grip click does not toggle visibility");
      const drag = async (target: string) => {
        const handle = document.querySelector('button[aria-label="Mover Adjunto"]')!;
        const destination = document.querySelector(`[data-column-setting="${target}"]`)!;
        const transfer = { setData: () => {}, effectAllowed: "" };
        await page.act(async () => { const event = new Event("dragstart", { bubbles: true }); Object.defineProperty(event, "dataTransfer", { value: transfer }); handle.dispatchEvent(event); });
        await page.act(async () => destination.dispatchEvent(new Event("dragover", { bubbles: true, cancelable: true })));
        await page.act(async () => destination.dispatchEvent(new Event("drop", { bubbles: true, cancelable: true })));
      };
      await drag("fecha");
      assert.equal(document.querySelectorAll('thead th')[1].getAttribute("data-col"), "comprobante");
      assert.equal(document.querySelector('th[data-col="comprobante"]')?.getAttribute("data-pinned"), "top");
      assert.equal(page.records()[0].querySelector('[data-col="comprobante"]')?.getAttribute("data-pinned"), null);
      await drag("cuenta");
      assert.equal(document.querySelector('th[data-col="comprobante"]')?.getAttribute("data-pinned"), "top right");
      const grip = document.querySelector<HTMLButtonElement>('button[aria-label="Mover Monto"]')!;
      const key = (key: string) => page.act(async () => { grip.focus(); grip.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true })); });
      await key(" "); await key("ArrowUp");
      assert.deepEqual([...document.querySelectorAll('thead th')].map((node) => node.getAttribute("data-col")).slice(0, 4), ["contraparte", "monto", "moneda", "fecha"]);
      await key("Escape");
      assert.ok(document.querySelector('[role="dialog"]'), "Escape restores grabbed order before dismissing");
      assert.deepEqual([...document.querySelectorAll('thead th')].map((node) => node.getAttribute("data-col")).slice(0, 3), ["contraparte", "fecha", "monto"]);
      await key(" "); await key("ArrowUp"); await key(" "); await key("Escape");
      assert.equal(document.querySelector('[role="dialog"]'), null);
      assert.deepEqual([...page.records()[0].querySelectorAll('td')].map((node) => node.getAttribute("data-col")).slice(0, 4), ["contraparte", "monto", "moneda", "fecha"]);
      const clickText = (text: string) => page.click([...document.querySelectorAll("button")].find((node) => node.textContent === text)!);
      await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
      await page.click([...document.querySelectorAll('button[role="radio"]')].find((node) => node.textContent === "Resumen")!);
      await page.click(document.querySelector('[data-summary-setting]'));
      await clickText("Aplicar");
      assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
      await clickText("Vistas"); await clickText("Guardar vista");
      const name = document.querySelector<HTMLInputElement>('[role="dialog"] input')!;
      await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(name, "Mi tabla"); name.dispatchEvent(new Event("input", { bubbles: true })); });
      await page.click(document.querySelector('[role="dialog"] button[type="submit"]'));
      await page.click(document.querySelector('[data-testid="transacciones-view-options"]')); await clickText("Restaurar valores iniciales");
      await page.act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
      await clickText("Vistas"); await clickText("Mi tabla");
      assert.equal(document.querySelector<HTMLElement>('[data-testid="transacciones-records"]')!.dataset.density, "compacto"); assert.equal(document.querySelector('th[data-col="categoria"]'), null);
      assert.equal(document.querySelectorAll('thead th')[1].getAttribute("data-col"), "monto");
      assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null);
      await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
      await clickText("Resumen");
      assert.equal(document.querySelector<HTMLInputElement>("[data-summary-setting] input")!.checked, false, "saved view restores visibility");
      await page.key(document.activeElement!, "Escape");
      await page.click(document.querySelector('button[aria-label="Página siguiente"]'));
      assert.equal(footer().dataset.page, "2");
      await page.click(document.querySelector('th[data-col="fecha"] button'));
      assert.equal(footer().dataset.page, "1");
      const firstDate = page.records()[0].querySelector('[data-col="fecha"]')?.textContent;
      await page.click(document.querySelector('button[aria-label="Página siguiente"]'));
      assert.notEqual(page.records()[0].querySelector('[data-col="fecha"]')?.textContent, firstDate);
      const input = document.querySelector<HTMLInputElement>('[data-testid="records-toolbar"] input')!;
      await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Sample 6"); input.dispatchEvent(new Event("input", { bubbles: true })); });
      assert.equal(footer().dataset.page, "1"); assert.equal(page.records().length, 6);
      assert.match(footer().textContent ?? "", /1–6 de 6/);
      assert.equal(resultSummary(), null);
      await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, ""); input.dispatchEvent(new Event("input", { bubbles: true })); });
      await page.click(document.querySelector('button[aria-label="Última página"]'));
      assert.equal(page.records().length, 15); assert.match(footer().textContent ?? "", /51–65 de 65/);
      await page.click(document.querySelector('button[aria-label^="Registros por página:"]'));
      await page.click([...document.querySelectorAll('[role="dialog"] button')].find((button) => button.textContent === "50 por página")!);
      assert.equal(footer().dataset.page, "1"); assert.equal(page.records().length, 50);
      await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "no-match"); input.dispatchEvent(new Event("input", { bubbles: true })); });
      assert.match(footer().textContent ?? "", /0–0 de 0/);
      await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, ""); input.dispatchEvent(new Event("input", { bubbles: true })); });
      assert.equal(page.records().length, 50, "no-result recovery keeps page size");
      assert.equal(document.querySelector('th[data-col="fecha"]')?.getAttribute("aria-sort"), "ascending", "no-result recovery keeps sort");
      await page.unmount();
    } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
  });

  test("fixture results summary follows loaded search and kind while preview amounts describe records", async () => {
    const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
    Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
    try {
      const items = [
        { id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-25", receipt_id: null },
        { id: "exp-hosting", merchant: "Nube Hosting", amount: "24.00", currency: "USD", category_id: null, account_id: null, occurred_on: "2026-10-24", receipt_id: null },
        { id: "exp-lunch", merchant: "Comedor Doña Ana", amount: "1250.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-23", receipt_id: null },
      ];
      const page = await mount({ enabled: false, transacciones: await recordsOf(items, {}, items) });
      const summary = () => document.querySelector('[data-testid="records-results-summary"]');
      await page.settle(() => page.records().length === 6, "fixture scope summary");
      assert.equal(summary(), null, "Todos has no monetary summary");
      assert.equal(document.querySelectorAll('thead th').length, 9);
      assert.equal(document.querySelector('th[data-col="cuenta"]'), null);
      assert.deepEqual([...document.querySelectorAll('th')].map((node) => node.getAttribute("data-col")), ["contraparte", "fecha", "monto", "moneda", "detalle", "categoria", "estado", "notas", "comprobante"]);
      const amount = page.records().find((row) => row.dataset.kind === "gasto")!.querySelector('[data-col="monto"]')!;
      assert.equal(amount.textContent, "2,100.00");
      assert.equal(amount.parentElement!.querySelector('[data-col="moneda"]')!.textContent, "RD$");
      assert.ok(amount.querySelector(".cuadrao-amount"), "document amount respects privacy masking");
      assert.equal(page.records()[0].querySelector('[data-col="detalle"]')!.textContent, "Gasto");
      await page.click([...document.querySelectorAll("button")].find((node) => node.textContent === "Filtros")!);
      await page.click([...document.querySelectorAll("label")].find((node) => node.textContent === "Gasto")!);
      await page.click([...document.querySelectorAll("button")].find((node) => node.textContent === "Aplicar")!);
      assert.equal(page.records().length, 3);
      assert.match(summary()!.textContent ?? "", /Importes en 2 monedas/);
      assert.equal(summary()!.querySelectorAll(".cuadrao-amount").length, 6, "three amounts remain separate by currency");
      const input = document.querySelector<HTMLInputElement>('[data-testid="records-toolbar"] input')!;
      await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Nube"); input.dispatchEvent(new Event("input", { bubbles: true })); });
      assert.equal(page.records().length, 1); assert.match(summary()!.textContent ?? "", /US\$ 24.00/);
      await page.click(document.querySelector('button[aria-label="Quitar filtro Registro"]'));
      assert.equal(page.records().length, 2);
      assert.equal(summary(), null, "removing the type returns to Todos");
      await page.unmount();
    } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
  });

  test("phone preview opens a saved record in the shared sheet and keeps the list mounted", async () => {
    const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
    Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
    try {
      let detailReads = 0;
      const page = await mount({ enabled: false, width: 390, expenseRead: async () => { detailReads += 1; throw new Error("detail-unavailable"); } });
      await page.settle(() => page.records().length > 0, "saved records");
      const row = page.records().find((item) => item.dataset.kind === "gasto")!;
      const key = row.dataset.recordKey;
      await page.click(row.matches("tr") ? row : row.querySelector("button"));
      await page.settle(() => Boolean(document.querySelector('[role="dialog"]')), "record sheet");
      assert.ok(document.querySelector('[data-testid="records-page-preview"]'));
      assert.ok(document.querySelector('[data-testid="loaded-record-glance"]'));
      assert.equal(detailReads, 0, "explicit loaded-row preview makes no detail request");
      assert.ok(page.records().some((item) => item.dataset.recordKey === key));
      await page.click(document.querySelector('[role="dialog"] button[aria-label="Cerrar"]'));
      await page.settle(() => !document.querySelector('[role="dialog"]'), "sheet closed");
      assert.ok(page.records().some((item) => item === row), "source row stays mounted");
      await page.unmount();
    } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
  });

  test("records filters keep the table contract and period totals while narrowing saved rows", async () => {
    const page = await mount({ enabled: false });
    await page.settle(() => page.records().length > 0, "the saved records");
    const total = page.records().length;
    const summary = document.querySelector('[data-testid="transacciones-summary"]')!.textContent;
    const toolbar = document.querySelector('[data-testid="records-toolbar"]')!;
    await page.click([...toolbar.querySelectorAll("button")].find((button) => button.getAttribute("aria-label")?.startsWith("Tipo:"))!);
    await page.click([...toolbar.querySelectorAll('[role="dialog"] button')].find((button) => button.textContent === "Gasto")!);
    assert.ok(page.records().length < total);
    assert.ok(page.records().every((row) => row.dataset.kind === "gasto"));
    assert.equal(document.querySelector('[data-testid="transacciones-summary"]')!.textContent, summary);
    assert.match(page.body(), /Resumen del período/);
    assert.equal(document.querySelector('[data-testid="records-count"]')?.textContent, `${page.records().length} registros`);
    await page.click([...toolbar.querySelectorAll("button")].find((button) => button.textContent?.includes("Limpiar filtros"))!);
    assert.equal(page.records().length, total);
    const period = [...toolbar.querySelectorAll("button")].find((button) => button.getAttribute("aria-label")?.startsWith("Período:") || button.getAttribute("aria-label")?.startsWith("Periodo:"))!;
    await page.click(period);
    assert.ok(toolbar.querySelector('[role="dialog"]'));
    await page.key(document.activeElement!, "Escape");
    assert.equal(toolbar.querySelector('[role="dialog"]'), null);
    assert.equal(document.activeElement, period);
  });

  test("search keeps same-id purchases and sales distinct on desktop and phone", async () => {
    const item = { id: "shared-id", merchant: "Nube Hosting", amount: "24.00", currency: "USD", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null };
    for (const width of [1440, 390]) {
      const source = await recordsOf([item, { ...item, id: "other-id", merchant: "Comedor" }], {}, [item]);
      const page = await mount({ enabled: false, width, transacciones: source });
      await page.settle(() => page.records().length === 3, "three saved records");
      assert.equal(new Set(page.records().map((row) => row.dataset.recordKey)).size, 3);
      const input = document.querySelector<HTMLInputElement>('[data-testid="records-toolbar"] input')!;
      await page.act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Nube");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      assert.equal(page.records().length, 2);
      assert.deepEqual(page.records().map((row) => row.dataset.kind).sort(), ["gasto", "venta"]);
      assert.equal(document.querySelector('[data-testid="records-count"]')?.textContent, "2 registros");
      await page.unmount();
    }
  });

  test("the Comprobante column is never an empty cell: a gasto without a receipt reads as a short dash", async () => {
    const page = await mount({ enabled: false });
    await page.settle(() => page.records().length > 0, "the saved records");
    const noReceipt = page.records().find((node) => !node.querySelector('[data-testid="record-proof"]'))?.querySelector<HTMLElement>('[data-col="comprobante"]');
    assert.ok(noReceipt, "a gasto without a receipt has a Comprobante cell");
    assert.ok(!page.body().includes("—"), "the records table never shows the long dash");
    assert.equal(noReceipt!.querySelector('[aria-hidden="true"]')?.textContent, "-");
    assert.match(noReceipt!.textContent ?? "", /Sin recibo/);
    for (const cell of page.host.querySelectorAll('td[data-col="comprobante"]')) assert.ok(cell.querySelector('[data-testid="record-proof"]') || (cell.textContent ?? "").trim() !== "", "a cell holds the receipt icon or a dash");
  });

  test("a saved record with a receipt shows the receipt icon and opens in the record tray beside the list", async () => {
    const page = await mount({ enabled: false });
    await page.settle(() => page.records().length > 0, "the saved records");
    const withReceipt = page.records().find((node) => node.querySelector('[data-testid="record-proof"]'));
    assert.ok(withReceipt, "a gasto with its receipt shows the icon");
    await page.click(withReceipt!);
    const opened = page.api().panel;
    assert.ok(opened.kind === "receipt" || opened.kind === "draft", `opened ${opened.kind}`);
    assert.equal((opened as { list?: string }).list, "transactions");
    await page.settle(() => document.querySelector('[data-testid="transacciones-records"]') !== null && document.querySelector('[data-testid="business-record-review"]') !== null, "the record beside the list");
  });

  test("an old Gastos link lands on Transacciones", async () => {
    const page = await mount({ enabled: false, view: "expenses" });
    assert.equal(page.api().panel.kind, "transactions");
    await page.settle(() => page.records().length > 0, "the saved records");
  });

  test("an empty period offers a real next step, never a zero list", async () => {
    const page = await mount({ enabled: false, transacciones: await recordsOf([]) });
    await page.settle(() => document.querySelector('[data-testid="transacciones-records-empty"]') !== null, "the empty state");
    assert.match(page.body(), /Aquí verás tus gastos y ventas/);
    assert.ok(document.querySelector('[data-testid="transacciones-records-empty"] button'), "one action to add");
    assert.equal(document.querySelector('[data-testid="transacciones-summary"] [data-total="salidas"] dd')?.textContent, "-sin dato", "no row names a currency, so the zero is not shown as pesos");
  });

  test("Salidas is the server's own total; a personal gasto stays listed, marked Personal, and out of it", async () => {
    const saved = await recordsOf([
      { id: "exp-1", merchant: "Colmado Don Pepe", amount: "860.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null },
      { id: "exp-2", merchant: "Comedor Doña Ana", amount: "1250.00", currency: "DOP", category_id: "dining", account_id: null, occurred_on: "2026-10-05", receipt_id: null, personal: true },
    ], { totals: [{ currency: "DOP", amount: "860.00", count: 1 }] });
    const page = await mount({ enabled: false, transacciones: saved });
    await page.settle(() => page.records().length === 2, "the saved records");
    assert.match(document.querySelector('[data-testid="transacciones-summary"] [data-total="salidas"]')?.textContent ?? "", /RD\$\s?860\.00/);
    assert.ok(document.querySelector('[data-record-id="exp-2"] [data-mark="personal"]'), "the personal gasto says so");
    assert.equal(document.querySelector('[data-record-id="exp-1"] [data-mark="personal"]'), null);
  });

  test("with igualar on and no statement imported yet, the saved records list in records mode", async () => {
    const { createSampleBankServer } = await import("@/components/business-app/transacciones/transacciones-sample");
    const { createBankTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
    const saved = await recordsOf([{ id: "exp-1", merchant: "Colmado Don Pepe", amount: "860.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null }], { totals: [{ currency: "DOP", amount: "860.00", count: 1 }] });
    const page = await mount({ transacciones: createBankTransaccionesSource(createSampleBankServer({ noStatement: true }), saved) });
    await page.settle(() => page.records().length === 1, "the saved records");
    assert.equal(document.querySelector('[data-testid="transacciones-segments"]'), null);
    assert.equal(document.querySelector('[data-testid="transacciones-summary"]')?.getAttribute("data-mode"), "records");
  });

  test("with the flag on, the rail reads Transacciones and opens the new screen", async () => {
    const page = await mount({ view: null });
    const rail = page.host.querySelector('[data-testid="business-sidebar-nav"]')!;
    const third = [...rail.querySelectorAll("button")].find((button) => button.textContent?.includes("Registros"));
    assert.ok(third, "the rail names Registros");
    await page.click(third!);
    await page.ready();
    assert.equal(page.host.querySelector('[data-testid="top-bar"] h1')?.textContent, "Registros");
  });

  test("the rail shows the server's Por igualar count; null means bank matching is off, not zero", async () => {
    const on = await mount({ view: null, porIgualarCount: 4 });
    await on.settle(() => on.host.querySelector('[data-testid="business-igualar-count"]') !== null, "the count");
    assert.equal(on.host.querySelector('[data-testid="business-igualar-count"]')?.textContent, "4");
    await on.unmount();
    const off = await mount({ view: null, porIgualarCount: null });
    await off.settle(() => off.host.querySelector('[data-testid="business-sidebar-nav"]') !== null, "the rail");
    await off.act(async () => { await new Promise((resolve) => setTimeout(resolve, 150)); });
    assert.equal(off.host.querySelector('[data-testid="business-igualar-count"]'), null);
    await off.unmount();
    const flagOff = await mount({ enabled: false, view: null, porIgualarCount: 4 });
    await flagOff.act(async () => { await new Promise((resolve) => setTimeout(resolve, 150)); });
    assert.equal(flagOff.host.querySelector('[data-testid="business-igualar-count"]'), null, "no count beside a screen with no Por igualar");
  });

  test("a phone's tabs read Transacciones too", async () => {
    const page = await mount({ width: 390 });
    assert.match(page.host.querySelector('[data-testid="business-bottom-tabs"]')?.textContent ?? "", /Registros/);
  });
});

describe("Transacciones table", () => {
  test("each state is a gray icon with its word for screen readers and on hover; red is never a state", async () => {
    const page = await mount();
    await page.ready();
    const check = (expected: Record<string, string>) => {
      for (const [id, word] of Object.entries(expected)) {
        const icon = page.row(id)!.querySelector<HTMLElement>('[data-testid="state-icon"]')!;
        assert.equal(icon.getAttribute("role"), "img", `${id} icon is an image`);
        assert.equal(icon.getAttribute("aria-label"), word, `${id} reads ${word}`);
        assert.doesNotMatch(icon.className, /9e2f39|red/, `${id} icon is not red`);
      }
    };
    check({ "doc-taller": "Sin movimiento" });
    await page.click(page.segment("todas"));
    await page.settle(() => page.row("mv-estacion") !== null, "Todas");
    check({ "mv-ferreteria": "Sugerencia", "mv-colmado": "Falta comprobante", "mv-estacion": "Igualada", "mv-dgii": "No lleva comprobante" });
  });

  test("the header pins on vertical scroll, Contraparte pins left and Comprobante pins right", async () => {
    const page = await mount();
    await page.ready();
    const grid = page.grid()!;
    for (const th of grid.querySelectorAll("thead th")) {
      assert.match(th.className, /\bsticky\b/);
      assert.match(th.className, /\btop-0\b/);
    }
    const first = page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-col="contraparte"]')!;
    const last = page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-col="comprobante"]')!;
    assert.equal(first.dataset.pinned, "left");
    assert.match(first.className, /\bsticky\b.*\bleft-0\b|\bleft-0\b.*\bsticky\b/);
    assert.equal(last.dataset.pinned, "right");
    assert.match(last.className, /\bright-0\b/);
    assert.equal(grid.querySelector('th[data-col="contraparte"]')?.getAttribute("data-pinned"), "top left");
  });

  test("text sits left and numbers right in tabular figures; only the sorted column has a sort arrow", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.segment("todas"));
    await page.settle(() => page.row("mv-estacion") !== null, "Todas");
    const grid = page.grid()!;
    const amount = page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-col="monto"]')!;
    assert.match(amount.className, /text-right/);
    assert.match(amount.className, /tabular-nums/);
    assert.match(page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-col="contraparte"]')!.className, /text-left/);
    const sorted = [...grid.querySelectorAll("th[aria-sort]")];
    assert.deepEqual(sorted.map((th) => [th.getAttribute("data-col"), th.getAttribute("aria-sort")]), [["fecha", "descending"]]);
    assert.equal(grid.querySelectorAll('[data-testid="sort-arrow"]').length, 1);
  });

  test("unknown reads as a dash, a known zero as 0.00, each row in its own currency, and a USD row keeps its symbol beside DOP", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.segment("todas"));
    await page.settle(() => page.row("mv-nube") !== null, "Todas");
    const cell = (id: string, col: string) => page.row(id)!.querySelector<HTMLElement>(`[data-col="${col}"]`)!;
    assert.equal(cell("mv-colmado", "categoria").querySelector('[aria-hidden="true"]')?.textContent, "-");
    assert.match(cell("mv-colmado", "categoria").textContent ?? "", /sin dato/);
    assert.ok(!page.body().includes("—"), "the movements table never shows the long dash");
    assert.match(cell("mv-verificacion", "monto").textContent ?? "", /0\.00/);
    assert.doesNotMatch(cell("mv-verificacion", "monto").querySelector('[aria-hidden="true"]')?.textContent ?? "", /[-−—+]/);
    assert.equal(cell("mv-ferreteria", "monto").querySelector('[aria-hidden="true"]')?.textContent, "−3,450.00");
    assert.equal(cell("mv-caribe", "monto").querySelector('[aria-hidden="true"]')?.textContent, "+42,940.68");
    assert.equal(cell("mv-nube", "monto").querySelector('[aria-hidden="true"]')?.textContent, "−US$ 24.00");
    assert.ok(cell("mv-ferreteria", "monto").querySelector(".cuadrao-amount"));
    const salidas = document.querySelector<HTMLElement>('[data-testid="transacciones-summary"] [data-total="salidas"] dd')!;
    assert.deepEqual([...salidas.querySelectorAll(".cuadrao-amount")].map((node) => node.textContent), ["RD$ 59,361.43", "US$ 24.00"], "one total per currency, the header's first, never added");
  });

  test("a contract answer with no account name and no category reads them as unknown, never invented", async () => {
    const { createBankTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
    const live = createBankTransaccionesSource(async <T,>(): Promise<T> => ({
      period_start: "2026-10-01", period_end: "2026-10-31", segment: "por_igualar", sense: null,
      accounts: [{ account_id: "a", name: null, type: "checking", bank_account_id: "b", currency: "DOP", covered_through: "2026-10-16" }],
      totals: [{ currency: "DOP", entradas_minor: 0, entradas: "0.00", salidas_minor: 86000, salidas: "860.00", por_igualar_minor: 86000, por_igualar: "860.00", counts: { movimientos: 1, igualadas: 0, no_lleva_comprobante: 0, sugerencias: 0, falta_comprobante: 1, sin_movimiento: 0, por_igualar: 1 } }],
      items: [{ kind: "movement", id: "l1", occurred_on: "2026-10-16", description: "COMPRA POS COLMADO", counterparty: "COMPRA POS COLMADO", sense: "charge", currency: "DOP", amount_minor: -86000, amount: "-860.00", state: "falta_comprobante", reason: null, category_id: null, account: { account_id: "a", name: null, type: "checking" }, method: "transferencia", document: null, suggestions: [] }],
      next_cursor: null,
    }) as T);
    const page = await mount({ transacciones: live });
    await page.ready();
    const row = page.row("l1")!;
    assert.match(row.querySelector('[data-col="contraparte"]')?.textContent ?? "", /COMPRA POS COLMADO/);
    assert.match(row.querySelector('[data-col="cuenta"]')?.textContent ?? "", /sin dato/);
    assert.match(row.querySelector('[data-col="categoria"]')?.textContent ?? "", /sin dato/);
    assert.match(document.querySelector('[data-testid="transacciones-summary"] [data-total="entradas"]')?.textContent ?? "", /RD\$ 0\.00/, "a known zero in the server's block");
    assert.match(page.screen()?.textContent ?? "", /Banco al día hasta el/);
  });

  test("density comes from the profile: Normal by default, the person's Amplio when /me says so, and a choice is written back", async () => {
    const page = await mount();
    await page.ready();
    const height = () => page.row("mv-ferreteria")!.style.height;
    assert.equal(page.grid()!.dataset.density, "normal");
    assert.equal(height(), "48px");
    await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
    assert.deepEqual([...document.querySelectorAll<HTMLElement>("[data-density-option]")].map((option) => option.textContent?.trim()), ["Compacto", "Normal", "Amplio"]);
    assert.match(page.body(), /Se guarda para ti en cada equipo donde entres/);
    await page.click(document.querySelector('[data-density-option="compacto"]'));
    assert.equal(height(), "40px");
    assert.deepEqual(profile.writes, ["compacto"]);
    await page.unmount();
    const { resetTableDensity } = await import("@/components/business-app/transacciones/table-density");
    resetTableDensity({ read: async () => "amplio", write: async () => undefined });
    const again = await mount();
    await again.ready();
    await again.settle(() => again.row("mv-ferreteria")!.style.height === "56px", "the profile's Amplio");
  });

  test("a density the profile refuses goes back to the kept one and says so beside the choice", async () => {
    profile.refuse = true;
    const page = await mount();
    await page.ready();
    await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
    await page.click(document.querySelector('[data-density-option="amplio"]'));
    await page.settle(() => document.querySelector('[data-testid="density-failed"]') !== null, "the refusal");
    assert.equal(page.row("mv-ferreteria")!.style.height, "48px");
    assert.equal(document.querySelector('[data-testid="density-failed"]')?.getAttribute("role"), "alert");
  });

  test("a phone ignores density: two-line rows of at least 64px with a kebab", async () => {
    profile.stored = "compacto";
    const page = await mount({ width: 390 });
    await page.ready();
    assert.equal(page.grid(), null, "no table on a phone");
    const row = page.row("mv-ferreteria")!;
    assert.match(row.className, /min-h-16/);
    assert.ok(row.querySelector('[data-testid="row-kebab"]'));
    assert.equal(document.querySelector('[data-testid="transacciones-view-options"]'), null);
  });

  test("Cargar más reads the next page and keeps the rows shown; a cursor the server no longer takes says the list changed", async () => {
    const { source, calls } = await bank({ pageSize: 5 }, (path) => (path.includes("cursor=o%3A10") ? refusal(422, "invalid_cursor") : undefined));
    const page = await mount({ transacciones: source });
    await page.ready();
    await page.click(page.segment("todas"));
    await page.settle(() => page.rows().length === 5, "the first page");
    const more = () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="transacciones-more"] button')][0];
    assert.equal(more()?.textContent, "Cargar más");
    await page.click(more());
    await page.settle(() => page.rows().length === 10, "the second page");
    assert.ok(calls.some((call) => call.path.includes("cursor=o%3A5")));
    await page.click(more());
    await page.settle(() => /La lista cambió/.test(document.querySelector('[data-testid="transacciones-more"]')?.textContent ?? ""), "the changed list");
    assert.equal(page.rows().length, 10, "rows already shown stay");
    assert.equal(more()?.textContent, "Actualizar");
  });
});

describe("Transacciones currency", () => {
  const movementsCalls = (calls: { path: string }[]) => calls.filter((call) => call.path.startsWith("/business/bank/movements?")).map((call) => new URLSearchParams(call.path.split("?")[1]));
  const menu = () => document.querySelector<HTMLButtonElement>('[data-testid="transacciones-currency"] [data-testid="month-close-currency"]');
  const pick = async (page: Awaited<ReturnType<typeof mount>>, currency: string) => {
    await page.click(menu());
    await page.click(document.querySelector(`[data-testid="month-close-currency-picker"] [data-currency="${currency}"]`));
  };

  test("the table follows the Business currency, and choosing another reads it from the top: the cursor resets on every currency and segment change", async () => {
    const { source, calls } = await bank({ pageSize: 5 });
    const page = await mount({ transacciones: source, businessCurrency: "DOP" });
    await page.ready();
    assert.equal(movementsCalls(calls)[0].get("currency"), "DOP", "the first read is already in the Business currency");
    await page.click(page.segment("todas"));
    await page.settle(() => page.rows().length === 5, "the first page");
    assert.ok(page.rows().every((row) => !/US\$/.test(row.textContent ?? "")), "no dollar row in a peso table");
    await page.click(document.querySelector<HTMLButtonElement>('[data-testid="transacciones-more"] button'));
    await page.settle(() => page.rows().length === 10, "the second page");
    assert.equal(movementsCalls(calls).at(-1)?.get("cursor"), "o:5");
    assert.equal(movementsCalls(calls).at(-1)?.get("currency"), "DOP", "a cursor travels with the currency that handed it out");
    await pick(page, "USD");
    await page.settle(() => page.row("mv-nube") !== null && page.rows().length === 1, "the dollar table");
    const switched = movementsCalls(calls).at(-1)!;
    assert.equal(switched.get("currency"), "USD");
    assert.equal(switched.get("cursor"), null, "a new currency starts from the top");
    assert.equal(menu()?.textContent, "USD");
    assert.match(document.querySelector('[data-testid="transacciones-summary"] [data-total="salidas"]')?.textContent ?? "", /US\$\s?24\.00/);
    assert.doesNotMatch(document.querySelector('[data-testid="transacciones-summary"]')?.textContent ?? "", /RD\$/, "the totals follow the table");
    assert.match(localStorage.getItem("cuadrao:business_currency_view:v1") ?? "", /"own":"USD"/, "one kept choice drives Inicio and Transacciones");
    await page.click(page.segment("igualadas"));
    await page.settle(() => movementsCalls(calls).at(-1)?.get("segment") === "igualadas", "Igualadas");
    assert.equal(movementsCalls(calls).at(-1)?.get("cursor"), null, "a new segment starts from the top");
    assert.equal(movementsCalls(calls).at(-1)?.get("currency"), "USD");
  });

  test("counts are the server's: Igualadas is the period's across currencies, Por igualar the chosen currency's, and nothing is added on the web", async () => {
    const { source, calls } = await bank({}, () => undefined);
    const forged = { ...source, async load(request: Parameters<TransaccionesSource["load"]>[0]) {
      const view = await source.load(request);
      return view.mode === "igualar" ? { ...view, counts: view.counts && { ...view.counts, movimientos: 90, igualadas: 40, noLleva: 2 } } : view;
    } };
    const page = await mount({ transacciones: forged, businessCurrency: "DOP" });
    await page.ready();
    assert.ok(calls.length > 0);
    const cell = (key: string) => document.querySelector<HTMLElement>(`[data-testid="transacciones-summary"] [data-total="${key}"] dd`)?.textContent ?? "";
    assert.equal(cell("igualadas"), "42de 90", "the period's own counts, as sent");
    const dop = (await source.load({ from: "2026-10-01", to: "2026-10-31", segment: "por_igualar", currency: "DOP" }));
    assert.ok(dop.mode === "igualar");
    const dopCount = dop.totals.find((block) => block.currency === "DOP")!.counts.porIgualar;
    assert.match(cell("por_igualar"), new RegExp(`^${dopCount}`), "Por igualar counts the rows the table covers");
    assert.equal(page.segment("por_igualar")?.textContent?.replace(/\D/g, ""), String(dopCount));
  });

  test("an older server without counts shows them as unknown, never a sum", async () => {
    const { source } = await bank();
    const older = { ...source, async load(request: Parameters<TransaccionesSource["load"]>[0]) {
      const view = await source.load(request);
      return view.mode === "igualar" ? { ...view, currency: null, counts: null, otherCurrencies: [] } : view;
    } };
    const page = await mount({ transacciones: older, businessCurrency: "DOP" });
    await page.ready();
    assert.equal(document.querySelector('[data-testid="transacciones-summary"] [data-total="igualadas"] dd')?.textContent, "-sin dato");
    assert.equal(menu(), null, "a server that does not follow a currency offers no menu");
  });

  test("the other-currencies line names what the table leaves out and switches to it; nothing renders when nothing is left out", async () => {
    const { source, calls } = await bank();
    const page = await mount({ transacciones: source, businessCurrency: "DOP" });
    await page.ready();
    await page.click(page.segment("todas"));
    await page.settle(() => document.querySelector('[data-testid="transacciones-other-currencies"]') !== null, "the line");
    const line = document.querySelector<HTMLElement>('[data-testid="transacciones-other-currencies"]')!;
    assert.match(line.textContent ?? "", /También hay 1 movimiento en US\$\./);
    await page.click([...line.querySelectorAll("button")].find((button) => button.textContent === "Ver en US$")!);
    await page.settle(() => page.row("mv-nube") !== null && page.rows().length === 1, "the dollar table");
    assert.equal(movementsCalls(calls).at(-1)?.get("currency"), "USD");
    assert.match(document.querySelector('[data-testid="transacciones-other-currencies"]')?.textContent ?? "", /movimientos en RD\$/);
    await page.unmount();
    const single = { ...source, async load(request: Parameters<TransaccionesSource["load"]>[0]) {
      const view = await source.load(request);
      return view.mode === "igualar" ? { ...view, otherCurrencies: [], totals: view.totals.filter((block) => block.currency === "DOP") } : view;
    } };
    (await import("@/lib/business-currency-view")).resetCurrencyViews();
    const one = await mount({ transacciones: single, businessCurrency: "DOP" });
    await one.ready();
    assert.equal(document.querySelector('[data-testid="transacciones-other-currencies"]'), null, "an empty list renders nothing");
    assert.equal(menu(), null, "one currency, no menu");
  });

  test("records mode lists the server's ventas beside the gastos, each in its own currency, and Entradas stays unknown: no total is made on the web", async () => {
    const saved = await recordsOf(
      [{ id: "exp-1", merchant: "Colmado Don Pepe", amount: "860.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null }],
      { totals: [{ currency: "DOP", amount: "860.00", count: 1 }] },
      [
        { id: "venta-1", merchant: "Cliente Uno", amount: "5000.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-10", receipt_id: null },
        { id: "venta-2", merchant: "Cliente Dos", amount: "120.00", currency: "USD", category_id: null, account_id: null, occurred_on: "2026-10-12", receipt_id: "rcpt-9" },
      ],
    );
    const page = await mount({ enabled: false, transacciones: saved, businessCurrency: "DOP" });
    await page.settle(() => page.records().length === 3, "gastos and ventas");
    assert.deepEqual(page.records().map((node) => [node.dataset.recordId, node.dataset.kind]), [["venta-2", "venta"], ["venta-1", "venta"], ["exp-1", "gasto"]]);
    const amount = (id: string) => document.querySelector(`[data-record-id="${id}"] [data-col="monto"] [aria-hidden="true"]`)?.textContent;
    assert.equal(amount("venta-1"), "+5,000.00", "a venta is money in");
    assert.equal(amount("venta-2"), "+US$ 120.00", "in its own currency");
    assert.equal(amount("exp-1"), "−860.00");
    assert.match(document.querySelector('[data-record-id="venta-1"]')?.textContent ?? "", /Venta/);
    assert.equal(document.querySelector('[data-record-id="venta-1"]')?.className.includes("cursor-pointer"), false, "a venta with no receipt or draft has no record to open");
    assert.equal(document.querySelector('[data-record-id="venta-2"]')?.className.includes("cursor-pointer"), true);
    assert.equal(document.querySelector('[data-testid="transacciones-summary"] [data-total="entradas"] dd')?.textContent, "-sin dato");
  });
});

describe("Transacciones decisions", () => {
  // The workspace and the harness each mount a viewport over the one presenter; the first is enough.
  const toastButtons = () => [...(document.querySelector('[data-testid="toast-viewport"]')?.querySelectorAll<HTMLButtonElement>("button") ?? [])];

  test("Igualar from the row confirms, moves the row to Igualadas, and Deshacer desiguala it back to its suggestion", async () => {
    const { source, calls } = await bank();
    const page = await mount({ transacciones: source });
    await page.ready();
    await page.click(page.row("mv-ferreteria")!.querySelector('[data-row-action="igualar"]'));
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina SRL, RD$ 3,450.00"), "the confirm toast");
    await page.settle(() => page.row("mv-ferreteria") === null, "the row to leave Por igualar");
    await page.click(toastButtons().find((button) => button.textContent === "Deshacer")!);
    await page.settle(() => page.row("mv-ferreteria")?.dataset.state === "sugerencia", "the suggestion back");
    const writes = calls.filter((call) => call.method !== "GET");
    assert.deepEqual(writes.map((call) => [call.method, call.path]), [["POST", "/business/bank/suggestions/sg-ferreteria/confirm"], ["POST", "/business/bank/movements/mv-ferreteria/unmatch"]]);
    assert.ok(writes.every((call) => call.key), "every decision carries an Idempotency-Key");
    assert.notEqual(writes[0].key, writes[1].key, "Deshacer is its own decision");
  });

  test("the suggestion run walks the tray one suggestion at a time; three igualadas share one toast", async () => {
    const page = await mount();
    await page.ready();
    await page.settle(() => page.api().chosen?.space_id === "fixture-space", "the Business scope to finish loading");
    const run = document.querySelector<HTMLButtonElement>('[data-testid="transacciones-run"]')!;
    assert.match(run.textContent ?? "", /Igualar sugerencias\s*3/);
    await page.click(run);
    const tray = () => document.querySelector<HTMLElement>('[data-testid="transacciones-tray"]');
    await page.settle(() => (tray()?.textContent ?? "").includes("Sugerencia 1 de 3"), "the run's first step");
    assert.match(tray()!.textContent ?? "", /Ferretería La Esquina SRL/);
    assert.match(tray()!.textContent ?? "", /El monto es exacto/);
    assert.match(tray()!.textContent ?? "", /El comprobante es de un día antes/);
    for (const step of [1, 2, 3]) {
      await page.click(document.querySelector<HTMLButtonElement>('[data-tray-action="igualar"]')!);
      if (step < 3) await page.settle(() => (tray()?.textContent ?? "").includes(`Sugerencia ${step + 1} de 3`), `step ${step + 1}`);
    }
    await page.settle(() => page.body().includes("3 igualadas"), "the shared toast");
    const viewport = document.querySelector('[data-testid="toast-viewport"]')!;
    assert.equal(viewport.children.length, 1, "one toast on screen");
    assert.equal(toastButtons().filter((button) => button.textContent === "Deshacer").length, 1);
    await page.settle(() => document.querySelector('[data-testid="transacciones-run"]') === null, "the run button to leave with no suggestions");
  });

  test("No es este declines the pair, the row waits for its comprobante, and the toast offers no Deshacer the server cannot do", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.row("mv-repuestos")!.querySelector('[data-row-action="rechazar"]'));
    await page.settle(() => page.row("mv-repuestos")?.dataset.state === "falta_comprobante", "the declined row");
    assert.match(page.body(), /Quitamos esa sugerencia/);
    assert.ok(!toastButtons().some((button) => button.textContent === "Deshacer"));
  });

  test("Sin comprobante asks why, the reason says it on the row, and Deshacer takes the reason back", async () => {
    const { source, calls } = await bank();
    const page = await mount({ transacciones: source });
    await page.ready();
    await page.click(page.row("mv-colmado")!.querySelector('[data-row-action="sin_comprobante"]'));
    await page.settle(() => document.querySelector('[data-reason="compra_informal"]') !== null, "the reasons");
    assert.deepEqual([...document.querySelectorAll("[data-reason]")].map((node) => node.textContent?.trim()), ["Cargo del banco", "Entre mis cuentas", "Compra informal", "Personal"]);
    await page.click(document.querySelector('[data-reason="compra_informal"]'));
    await page.settle(() => page.row("mv-colmado") === null, "the row to leave Por igualar");
    await page.click(page.segment("igualadas"));
    await page.settle(() => page.row("mv-colmado")?.dataset.state === "no_lleva", "the row in Igualadas");
    assert.match(page.row("mv-colmado")!.textContent ?? "", /Compra informal/);
    assert.equal(document.querySelector('[data-testid="transacciones-tray"]'), null, "the tray left with its row and does not reopen on another segment");
    assert.match(page.row("mv-colmado")!.querySelector('[data-col="comprobante"]')?.textContent ?? "", /No lleva comprobante/, "the proof cell is never empty");
    await page.click(toastButtons().find((button) => button.textContent === "Deshacer")!);
    await page.settle(() => page.row("mv-colmado") === null, "the reason taken back");
    assert.deepEqual(calls.filter((call) => call.method !== "GET").map((call) => [call.method, call.path]), [["PUT", "/business/bank/movements/mv-colmado/disposition"], ["DELETE", "/business/bank/movements/mv-colmado/disposition"]]);
  });

  test("a failed Igualar says so inline with Reintentar and its reference, never in a toast; Reintentar sends the same key", async () => {
    const { source, calls } = await bank({ failDecideOnce: true });
    const page = await mount({ transacciones: source });
    await page.ready();
    await page.click(page.row("mv-ferreteria")!.querySelector('[data-row-action="igualar"]'));
    await page.settle(() => document.querySelector('[data-testid="transacciones-decision-error"]') !== null, "the inline error");
    const error = document.querySelector<HTMLElement>('[data-testid="transacciones-decision-error"]')!;
    assert.equal(error.getAttribute("role"), "alert");
    assert.match(error.textContent ?? "", /No pudimos guardar este cambio/);
    assert.match(error.textContent ?? "", /Ref\./);
    assert.equal(document.querySelector('[data-testid="toast-viewport"]')?.textContent, "");
    await page.click([...error.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!);
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina SRL"), "the retried confirm");
    const confirms = calls.filter((call) => call.path.endsWith("/confirm"));
    assert.equal(confirms.length, 2);
    assert.equal(confirms[0].key, confirms[1].key, "the retry is the same request");
  });

  test("each refusal says what happened in place: a moved-on line offers Actualizar, an impossible pair offers nothing, neither a reference", async () => {
    const cases: [string, number, RegExp, string | null][] = [
      ["document_already_matched", 409, /ya está igualado con otro movimiento/, "Actualizar"],
      ["line_marked_no_receipt", 409, /ya está marcado como que no lleva comprobante/, "Actualizar"],
      ["line_not_found", 404, /ya no está en tu estado de cuenta/, "Actualizar"],
      ["document_not_matchable", 422, /debe ser del mismo monto y la misma moneda/, null],
      ["business_bank_unavailable", 503, /No pudimos guardar este cambio/, "Reintentar"],
    ];
    for (const [code, status, text, action] of cases) {
      const { source } = await bank({}, (path, init) => (init?.method === "POST" ? refusal(status, code) : undefined));
      const page = await mount({ transacciones: source });
      await page.ready();
      await page.click(page.row("mv-ferreteria")!.querySelector('[data-row-action="igualar"]'));
      await page.settle(() => document.querySelector('[data-testid="transacciones-decision-error"]') !== null, `the ${code} error`);
      const error = document.querySelector<HTMLElement>('[data-testid="transacciones-decision-error"]')!;
      assert.match(error.textContent ?? "", text, code);
      assert.deepEqual([...error.querySelectorAll("button:not([data-testid=\"error-reference\"])")].map((button) => button.textContent), action ? [action] : [], code);
      assert.equal(/Ref\./.test(error.textContent ?? ""), action === "Reintentar", `${code} reference`);
      assert.equal(document.querySelector('[data-testid="toast-viewport"]')?.textContent, "", `${code} is never a toast`);
      await page.unmount();
    }
  });

  test("a list that fails to load says so with Reintentar", async () => {
    const { source } = await bank({ failLoad: true });
    const page = await mount({ transacciones: source });
    await page.settle(() => document.querySelector('[data-testid="transacciones-error"]') !== null, "the load error");
    assert.match(page.body(), /No pudimos cargar tus movimientos/);
    assert.ok([...document.querySelectorAll('[data-testid="transacciones-error"] button')].some((button) => button.textContent === "Reintentar"));
  });
});

describe("Transacciones keyboard and buttons", () => {
  test("single keys act only while focus is in the table", async () => {
    const page = await mount();
    await page.ready();
    await page.key(document.body, "i");
    assert.equal(page.row("mv-ferreteria")?.dataset.state, "sugerencia", "a key outside the table does nothing");
    const row = page.row("mv-ferreteria")!;
    await page.act(async () => row.focus());
    await page.key(row, "ArrowDown");
    assert.equal(document.activeElement, page.row("mv-repuestos"), "the arrow moves to the next row");
    await page.key(page.row("mv-repuestos")!, "ArrowUp");
    await page.key(page.row("mv-ferreteria")!, "i");
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina SRL"), "the keyed igualar");
  });

  test("each row action names its key", async () => {
    const page = await mount();
    await page.ready();
    const igualar = page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-row-action="igualar"]')!;
    assert.equal(igualar.querySelector("kbd")?.textContent, "I");
    assert.equal(page.row("mv-ferreteria")!.querySelector('[data-row-action="rechazar"] kbd')?.textContent, "N");
  });

  test("the content heading keeps Igualar sugerencias alongside Agregar", async () => {
    const page = await mount();
    await page.ready();
    const primaries = [...page.screen()!.querySelectorAll('[data-primary="true"]')];
    assert.equal(primaries.length, 2);
    assert.equal(primaries[0].getAttribute("data-testid"), "transacciones-run");
    const add = document.querySelector<HTMLElement>('[data-testid="add-menu-header"] [data-testid="business-primary-upload"]')!;
    assert.ok(page.screen()!.contains(add), "Agregar is in the content heading");
    assert.equal(document.querySelector('[data-testid="top-bar"] [data-testid="business-primary-upload"]'), null);
    assert.match(add.className, /bg-\[var\(--cuadrao-green\)\]/);
    assert.equal(add.getAttribute("data-primary"), "true");
  });
});


test("new local business has no sample sales or bank movements", async () => {
  const nodeEnv = process.env.NODE_ENV;
  const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  const { createLocalBusiness, LOCAL_BUSINESS_KEY, LOCAL_BUSINESS_EVENT } = await import("@/app/design-workspace/localBusinessPreview");
  const page = await mount({ enabled: true });
  const local = createLocalBusiness(localStorage, "Taller vacío", "CA", { kind: "default" }, "local-business-no-sales");
  try {
    await page.act(async () => {
      window.dispatchEvent(new Event(LOCAL_BUSINESS_EVENT));
      page.api().chooseBusiness(local.id);
      page.api().openPanel({ kind: "transactions" });
    });
    await page.settle(() => Boolean(page.screen()?.querySelector('[data-testid="transacciones-records-empty"]')) && page.api().records.workspace?.country === "CA", "empty local transactions");
    assert.equal(page.records().length, 0);
    assert.equal(page.rows().length, 0);
    assert.doesNotMatch(page.body(), /Cliente Colmado|Panadería Luna/);
  } finally {
    await page.unmount();
    localStorage.removeItem(LOCAL_BUSINESS_KEY);
    localStorage.removeItem("cuadrao-identity-v1:business:local-business-no-sales");
    Object.assign(process.env, { NODE_ENV: nodeEnv, NEXT_PUBLIC_MOCK_AUTH: mockAuth });
  }
});

for (const language of ["es-419", "en"]) test(`shared currency filter updates rows, cards, footer and removable chip in ${language}`, async () => {
  const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    const items = [
      { id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-25", receipt_id: null },
      { id: "exp-hosting", merchant: "Nube Hosting", amount: "24.00", currency: "USD", category_id: null, account_id: null, occurred_on: "2026-10-24", receipt_id: null },
      { id: "exp-lunch", merchant: "Comedor Doña Ana", amount: "1250.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-23", receipt_id: null },
    ];
    const page = await mount({ enabled: false, language, transacciones: await recordsOf(items, {}, items) });
    await page.settle(() => page.records().length === 6, "loaded six records");
    const es = language === "es-419";
    const clickText = (text: string) => page.click([...document.querySelectorAll("button")].find((node) => node.textContent === text)!);
    const open = async () => {
      await page.click([...document.querySelectorAll('[data-testid="records-toolbar"] button')].find((node) => node.textContent?.startsWith(es ? "Filtros" : "Filters"))!);
      await page.click(document.querySelector('[data-group="amount"]'));
    };
    await open(); await clickText("USD"); await clickText(es ? "Aplicar" : "Apply");
    assert.equal(page.records().length, 2);
    const footer = () => document.querySelector<HTMLElement>('[data-testid="records-pagination"]')!;
    assert.match(footer().textContent ?? "", es ? /1–2 de 2/ : /1–2 of 2/);
    assert.equal(footer().dataset.page, "1");
    assert.equal(document.querySelector('[data-testid="records-results-summary"]'), null, "currency alone does not create a mixed summary");
    const removeCurrency = es ? "Quitar filtro Moneda" : "Remove filter Currency";
    assert.ok(document.querySelector(`button[aria-label="${removeCurrency}"]`));
    await page.click(document.querySelector(`button[aria-label="${removeCurrency}"]`));
    assert.equal(page.records().length, 6);
    await open(); await clickText("USD");
    const minimum = document.querySelector<HTMLInputElement>('input[inputmode="decimal"]')!;
    await page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(minimum, "25"); minimum.dispatchEvent(new Event("input", { bubbles: true })); });
    await clickText(es ? "Aplicar" : "Apply");
    assert.equal(page.records().length, 0);
    assert.match(footer().textContent ?? "", es ? /0–0 de 0/ : /0–0 of 0/);
    assert.ok(document.querySelector(`button[aria-label="${es ? "Quitar filtro Moneda y monto" : "Remove filter Currency and amount"}"]`));
    const clear = [...document.querySelectorAll("button")].filter((node) => node.textContent === (es ? "Limpiar filtros" : "Clear filters")).at(-1)!;
    await page.click(clear);
    assert.equal(page.records().length, 6, "empty-result clear also clears the shared currency/amount filter");
    assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]'), null);
    await page.unmount();
  } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
});


for (const width of [1440, 390]) test(`overview filters share chips while counts retain business and period scope at ${width}px`, async () => {
  const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    const items = [
      { id: "exp-gas", merchant: "Estación Ruta 3", amount: "2100.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-25", receipt_id: null },
      { id: "exp-hosting", merchant: "Nube Hosting", amount: "24.00", currency: "USD", category_id: null, account_id: null, occurred_on: "2026-10-24", receipt_id: null },
      { id: "exp-lunch", merchant: "Comedor Doña Ana", amount: "1250.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-23", receipt_id: null },
    ];
    const page = await mount({ enabled: false, width, transacciones: await recordsOf(items, {}, items) });
    await page.settle(() => page.records().length === 6, "six fixture records");
    const overview = () => document.querySelector('[data-testid="records-overview-preview"]')!;
    const original = overview().textContent;
    const clickText = (text: string) => page.click([...document.querySelectorAll("button")].find((node) => node.textContent === text)!);
    await page.click(document.querySelector('[data-overview-filter="review"]'));
    assert.equal(page.records().length, 2);
    assert.equal(document.querySelector('[data-overview-filter="review"]')?.getAttribute("aria-pressed"), "true");
    assert.ok(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
    const input = document.querySelector<HTMLInputElement>('[data-testid="records-toolbar"] input')!;
    const fill = async (field: HTMLInputElement, value: string) => page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value); field.dispatchEvent(new Event("input", { bubbles: true })); });
    await fill(input, "Estación"); assert.equal(page.records().length, 1);
    assert.equal(overview().textContent, original, "search does not rewrite the overview");
    await page.click(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
    assert.equal(page.records().length, 2, "removing the workflow chip keeps the search");
    await fill(input, "");
    await page.click([...document.querySelectorAll('[data-testid="records-toolbar"] button')].find((node) => node.textContent?.startsWith("Filtros"))!);
    await page.click(document.querySelector('[data-group="amount"]')); await clickText("USD"); await clickText("Aplicar");
    await page.click(document.querySelector('[data-overview-filter="export"]'));
    assert.equal(page.records().length, 1, "currency and overview filters compose");
    assert.equal(overview().textContent, original, "currency and workflow do not rewrite overview");
    await page.click(document.querySelector('button[aria-label="Quitar filtro Moneda"]'));
    await page.click(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
    await page.click([...document.querySelectorAll('[data-testid="records-toolbar"] button')].find((node) => node.textContent === "Este mes")!);
    const fields = [...document.querySelectorAll<HTMLInputElement>('[data-testid="range-picker"] input')];
    await fill(fields[0], "24/10/2026"); await fill(fields[1], "24/10/2026"); await clickText("Confirmar período");
    assert.equal(page.records().length, 2, "page period filters activity dates inclusively");
    assert.match(document.querySelector('[data-overview-filter="review"]')?.textContent ?? "", /0/);
    assert.match(document.querySelector('[data-overview-filter="approval"]')?.textContent ?? "", /1/);
    assert.match(document.querySelector('[data-overview-filter="export"]')?.textContent ?? "", /1/);
    await page.click([...document.querySelectorAll('[data-testid="records-toolbar"] button')].find((node) => node.textContent?.includes("24 oct"))!);
    const emptyFields = [...document.querySelectorAll<HTMLInputElement>('[data-testid="range-picker"] input')];
    await fill(emptyFields[0], "22/10/2026"); await fill(emptyFields[1], "22/10/2026"); await clickText("Confirmar período");
    assert.equal(page.records().length, 0);
    await clickText("Restablecer período");
    assert.equal(page.records().length, 6, "an empty period has a working local reset without API work");
    await page.unmount();
  } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
});
