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
  document.body.innerHTML = "";
  search = "";
});

async function mount({ enabled = true, width = 1440, transacciones, view = "transactions", porIgualarCount }: { enabled?: boolean; width?: number; transacciones?: TransaccionesSource; view?: string | null; porIgualarCount?: number | null } = {}) {
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
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = {
    ...fixture,
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
        <header data-testid="top-bar">{workspace?.headerActions?.(shell as never)}</header>
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
    <BusinessWorkspaceProvider source={source as BusinessDataSource}>
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

async function recordsOf(expenses: Parameters<typeof import("@/components/business-app/transacciones/transacciones-adapter")["createRecordsTransaccionesSource"]>[0]["expenses"] extends (...args: never[]) => Promise<infer T> ? T : never, overview: object = EMPTY_OVERVIEW) {
  const { createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
  return createRecordsTransaccionesSource({ expenses: async () => expenses, overview: async () => ({ ...EMPTY_OVERVIEW, ...overview }), workspace: async () => ({ accounts: [] }), ownerFunds: "Dinero del dueño" });
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
  test("with igualar off, the third screen is still Transacciones: the period's saved gastos, no igualar parts, Entradas unknown", async () => {
    const page = await mount({ enabled: false });
    const rail = page.host.querySelector('[data-testid="business-sidebar-nav"]')!;
    assert.ok([...rail.querySelectorAll("button")].some((button) => button.textContent?.includes("Transacciones")), "the rail names Transacciones");
    assert.ok(!rail.textContent?.includes("Gastos"));
    await page.settle(() => page.records().length > 0, "the saved records");
    assert.equal(page.screen()?.querySelector("h2")?.textContent, "Transacciones");
    assert.deepEqual([...new Set(page.records().map((node) => node.dataset.kind))], ["gasto"], "no venta is rebuilt from month-close lines");
    for (const absent of ["transacciones-segments", "transacciones-run", "transacciones-grid"]) assert.equal(document.querySelector(`[data-testid="${absent}"]`), null, `${absent} stays behind the flag`);
    assert.doesNotMatch(page.body(), /Banco al día|Por igualar|Igualadas|¿Este\?|Igualar sugerencias/);
    const summary = document.querySelector<HTMLElement>('[data-testid="transacciones-summary"]')!;
    assert.deepEqual([...summary.querySelectorAll("[data-total]")].map((cell) => cell.getAttribute("data-total")), ["entradas", "salidas"]);
    assert.equal(summary.querySelector('[data-total="entradas"] dd')?.textContent, "-sin dato");
    assert.match(summary.querySelector('[data-total="salidas"]')?.textContent ?? "", /RD\$\s?\d/);
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
    assert.match(page.body(), /Aquí verás tus gastos/);
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
    const third = [...rail.querySelectorAll("button")].find((button) => button.textContent?.includes("Transacciones"));
    assert.ok(third, "the rail names Transacciones");
    await page.click(third!);
    await page.ready();
    assert.equal(page.screen()?.querySelector("h2")?.textContent, "Transacciones");
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
    assert.match(page.host.querySelector('[data-testid="business-bottom-tabs"]')?.textContent ?? "", /Transacciones/);
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
      assert.deepEqual([...error.querySelectorAll("button")].map((button) => button.textContent), action ? [action] : [], code);
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

  test("one primary in the page, Igualar sugerencias; the top bar's Agregar stays primary, as on every screen", async () => {
    const page = await mount();
    await page.ready();
    const primaries = [...page.screen()!.querySelectorAll('[data-primary="true"]')];
    assert.equal(primaries.length, 1);
    assert.equal(primaries[0].getAttribute("data-testid"), "transacciones-run");
    const add = document.querySelector<HTMLElement>('[data-testid="add-menu-header"] [data-testid="business-primary-upload"]')!;
    assert.ok(add, "Agregar stays in the top bar");
    assert.match(add.className, /bg-\[var\(--cuadrao-green\)\]/);
    assert.equal(add.getAttribute("data-primary"), "true");
  });
});
