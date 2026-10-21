import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
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

const DENSITY_KEY = "cuadrao:table_density";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  localStorage.removeItem(DENSITY_KEY);
  (await import("@/components/business-app/transacciones/table-density")).resetTableDensity();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  (await import("@/components/business-app/foundation/toasts")).clearToasts();
  document.body.innerHTML = "";
  search = "";
});

async function mount({ enabled = true, width = 1440, transacciones, view = "transactions" }: { enabled?: boolean; width?: number; transacciones?: TransaccionesSource; view?: string | null } = {}) {
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
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: false }), captures: async () => [] };
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

describe("the gate", () => {
  test("with igualar off, the third screen is still Transacciones: the period's saved gastos and ventas, no igualar parts", async () => {
    const page = await mount({ enabled: false });
    const rail = page.host.querySelector('[data-testid="business-sidebar-nav"]')!;
    assert.ok([...rail.querySelectorAll("button")].some((button) => button.textContent?.includes("Transacciones")), "the rail names Transacciones");
    assert.ok(!rail.textContent?.includes("Gastos"));
    await page.settle(() => page.records().length > 0, "the saved records");
    assert.equal(page.screen()?.querySelector("h2")?.textContent, "Transacciones");
    const kinds = new Set(page.records().map((node) => node.dataset.kind));
    assert.deepEqual([...kinds].sort(), ["gasto", "venta"]);
    for (const absent of ["transacciones-segments", "transacciones-run", "transacciones-grid"]) assert.equal(document.querySelector(`[data-testid="${absent}"]`), null, `${absent} stays behind the flag`);
    assert.doesNotMatch(page.body(), /Banco al día|Por igualar|Igualadas|¿Este\?|Igualar sugerencias/);
    const summary = document.querySelector<HTMLElement>('[data-testid="transacciones-summary"]')!;
    assert.deepEqual([...summary.querySelectorAll("[data-total]")].map((cell) => cell.getAttribute("data-total")), ["entradas", "salidas"]);
    assert.match(summary.querySelector('[data-total="entradas"]')?.textContent ?? "", /RD\$\s?\d/);
    assert.match(summary.querySelector('[data-total="salidas"]')?.textContent ?? "", /RD\$\s?\d/);
  });

  test("the Comprobante column is never an empty cell: a gasto without a receipt and a venta both read as a short dash", async () => {
    const page = await mount({ enabled: false });
    await page.settle(() => page.records().length > 0, "the saved records");
    const proof = (kind: string, withIcon: boolean) => page.records().filter((node) => node.dataset.kind === kind && Boolean(node.querySelector('[data-testid="record-proof"]')) === withIcon).map((node) => node.querySelector<HTMLElement>('[data-col="comprobante"]'));
    const noReceipt = proof("gasto", false).filter(Boolean)[0];
    assert.ok(noReceipt, "a gasto without a receipt has a Comprobante cell");
    assert.ok(!page.body().includes("\u2014"), "the records table never shows the long dash");
    assert.equal(noReceipt!.querySelector('[aria-hidden="true"]')?.textContent, "-");
    assert.match(noReceipt!.textContent ?? "", /Sin recibo/);
    const venta = proof("venta", false).filter(Boolean)[0];
    assert.ok(venta, "a venta has a Comprobante cell");
    assert.equal(venta!.querySelector('[aria-hidden="true"]')?.textContent, "-");
    assert.match(venta!.textContent ?? "", /sin dato/);
    for (const cell of page.host.querySelectorAll('td[data-col="comprobante"]')) assert.ok(cell.querySelector('[data-testid="record-proof"]') || (cell.textContent ?? "").trim() !== "", "a cell holds the receipt icon or a dash");
  });

  test("a saved record with a receipt shows the receipt icon and opens in the record tray beside the list", async () => {
    const page = await mount({ enabled: false });
    await page.settle(() => page.records().length > 0, "the saved records");
    const withReceipt = page.records().find((node) => node.querySelector('[data-testid="record-proof"]'));
    assert.ok(withReceipt, "a gasto with its receipt shows the icon");
    assert.equal(withReceipt!.dataset.kind, "gasto");
    await page.click(withReceipt!);
    const opened = page.api().panel;
    assert.ok(opened.kind === "receipt" || opened.kind === "draft", `opened ${opened.kind}`);
    assert.equal((opened as { list?: string }).list, "transactions");
    await page.settle(() => document.querySelector('[data-testid="transacciones-records"]') !== null && document.querySelector('[data-testid="business-record-review"]') !== null, "the record beside the list");
    const venta = page.records().find((node) => node.dataset.kind === "venta")!;
    assert.match(venta.textContent ?? "", /Venta/);
    assert.match(venta.querySelector('[data-col="monto"]')?.textContent ?? "", /\+/);
  });

  test("an old Gastos link lands on Transacciones", async () => {
    const page = await mount({ enabled: false, view: "expenses" });
    assert.equal(page.api().panel.kind, "transactions");
    await page.settle(() => page.records().length > 0, "the saved records");
  });

  test("an empty period offers a real next step, never a zero list", async () => {
    const { createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
    const none = createRecordsTransaccionesSource({ expenses: async () => [], overview: async () => ({ from: "2026-10-01", to: "2026-10-20", today: "2026-10-20", totals: [], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null }), workspace: async () => ({ accounts: [] }), month: async (month) => ({ month, from: `${month}-01`, to: `${month}-28`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] }), ownerFunds: "Dinero del dueño" });
    const page = await mount({ enabled: false, transacciones: none });
    await page.settle(() => document.querySelector('[data-testid="transacciones-records-empty"]') !== null, "the empty state");
    assert.match(page.body(), /Aquí verás tus gastos y ventas/);
    assert.ok(document.querySelector('[data-testid="transacciones-records-empty"] button'), "one action to add");
  });

  test("Salidas is the server's own total; a personal gasto stays listed, marked Personal, and out of it", async () => {
    const { createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
    const saved = createRecordsTransaccionesSource({
      expenses: async () => [
        { id: "exp-1", merchant: "Colmado Don Pepe", amount: "860.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null },
        { id: "exp-2", merchant: "Comedor Doña Ana", amount: "1250.00", currency: "DOP", category_id: "dining", account_id: null, occurred_on: "2026-10-05", receipt_id: null, personal: true },
      ],
      overview: async () => ({ from: "2026-10-01", to: "2026-10-20", today: "2026-10-20", totals: [{ currency: "DOP", amount: "860.00", count: 1 }], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null }),
      workspace: async () => ({ accounts: [] }),
      month: async (month) => ({ month, from: `${month}-01`, to: `${month}-28`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] }),
      ownerFunds: "Dinero del dueño",
    });
    const page = await mount({ enabled: false, transacciones: saved });
    await page.settle(() => page.records().length === 2, "the saved records");
    assert.match(document.querySelector('[data-testid="transacciones-summary"] [data-total="salidas"]')?.textContent ?? "", /RD\$\s?860\.00/);
    assert.ok(document.querySelector('[data-record-id="exp-2"] [data-mark="personal"]'), "the personal gasto says so");
    assert.equal(document.querySelector('[data-record-id="exp-1"] [data-mark="personal"]'), null);
  });

  test("while the server has the bank routes off, the records list instead of an error", async () => {
    const { createBankTransaccionesSource, createRecordsTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
    const saved = createRecordsTransaccionesSource({ expenses: async () => [{ id: "exp-1", merchant: "Colmado Don Pepe", amount: "860.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-04", receipt_id: null }], overview: async () => ({ from: "2026-10-01", to: "2026-10-20", today: "2026-10-20", totals: [{ currency: "DOP", amount: "860.00", count: 1 }], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null }), workspace: async () => ({ accounts: [] }), month: async (month) => ({ month, from: `${month}-01`, to: `${month}-28`, currency: "DOP", closed_at: null, earliest_month: null, documents: [] }), ownerFunds: "Dinero del dueño" });
    const off = createBankTransaccionesSource(async () => { throw Object.assign(new Error("off"), { status: 404, code: "financial_connections_unavailable" }); }, saved);
    const view = await off.load({ from: "2026-10-01", to: null });
    assert.equal(view.mode, "records");
    assert.equal(view.mode === "records" ? view.records[0].counterparty : null, "Colmado Don Pepe");
    const failing = createBankTransaccionesSource(async () => { throw Object.assign(new Error("down"), { status: 503 }); }, saved);
    await assert.rejects(failing.load({ from: "2026-10-01", to: null }), "any other failure stays a failure");
  });

  test("with the flag on, the rail reads Transacciones and opens the new screen", async () => {
    const page = await mount({ view: null });
    const rail = page.host.querySelector('[data-testid="business-sidebar-nav"]')!;
    const third = [...rail.querySelectorAll("button")].find((button) => button.textContent?.includes("Transacciones"));
    assert.ok(third, "the rail names Transacciones");
    assert.ok(!rail.textContent?.includes("Gastos"));
    await page.click(third!);
    await page.ready();
    assert.equal(page.screen()?.querySelector("h2")?.textContent, "Transacciones");
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
    await page.click(page.segment("todas"));
    const words = new Map(page.rows().map((row) => [row.dataset.movementId, row.querySelector<HTMLElement>('[data-testid="state-icon"]')]));
    const expected: Record<string, string> = {
      "mv-ferreteria": "Sugerencia",
      "mv-colmado": "Falta comprobante",
      "mv-estacion": "Igualada",
      "mv-caribe": "Igualada en parte",
      "mv-dgii": "No lleva comprobante",
      "doc-taller": "Sin movimiento",
    };
    for (const [id, word] of Object.entries(expected)) {
      const icon = words.get(id)!;
      assert.equal(icon.getAttribute("role"), "img", `${id} icon is an image`);
      assert.equal(icon.getAttribute("aria-label"), word, `${id} reads ${word}`);
      assert.doesNotMatch(icon.className, /9e2f39|red/, `${id} icon is not red`);
    }
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
    const grid = page.grid()!;
    const amount = page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-col="monto"]')!;
    assert.match(amount.className, /text-right/);
    assert.match(amount.className, /tabular-nums/);
    assert.match(page.row("mv-ferreteria")!.querySelector<HTMLElement>('[data-col="contraparte"]')!.className, /text-left/);
    const sorted = [...grid.querySelectorAll("th[aria-sort]")];
    assert.deepEqual(sorted.map((th) => [th.getAttribute("data-col"), th.getAttribute("aria-sort")]), [["fecha", "descending"]]);
    assert.equal(grid.querySelectorAll('[data-testid="sort-arrow"]').length, 1);
  });

  test("unknown reads as a dash, a known zero as 0.00, and the amount carries its sign and Ocultar montos", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.segment("todas"));
    const cell = (id: string, col: string) => page.row(id)!.querySelector<HTMLElement>(`[data-col="${col}"]`)!;
    assert.equal(cell("mv-colmado", "categoria").querySelector('[aria-hidden="true"]')?.textContent, "-");
    assert.match(cell("mv-colmado", "categoria").textContent ?? "", /sin dato/);
    assert.ok(!page.body().includes("\u2014"), "the movements table never shows the long dash");
    assert.match(cell("mv-verificacion", "monto").textContent ?? "", /0\.00/);
    assert.doesNotMatch(cell("mv-verificacion", "monto").textContent ?? "", /[-—]/);
    assert.match(cell("mv-ferreteria", "monto").textContent ?? "", /−3,450\.00/);
    assert.match(cell("mv-caribe", "monto").textContent ?? "", /\+42,940\.68/);
    assert.match(cell("mv-nube", "monto").textContent ?? "", /−US\$ 24\.00/);
    assert.ok(cell("mv-ferreteria", "monto").querySelector(".cuadrao-amount"));
    assert.ok(document.querySelector('[data-testid="transacciones-summary"] .cuadrao-amount'));
  });

  test("over today's bank routes, what the server does not serve shows as unknown, never as zero", async () => {
    const { createBankTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-adapter");
    const live = createBankTransaccionesSource(async <T,>(path: string): Promise<T> => (path.includes("unmatched")
      ? { count: 1, period_start: "2026-10-01", period_end: "2026-10-31", lines: [{ id: "l1", occurred_on: "2026-10-16", description: "COMPRA POS COLMADO", amount: "-860.00", currency: "DOP", sense: "charge", state: "sin_comprobante" }] }
      : []) as T);
    const page = await mount({ transacciones: live });
    await page.ready();
    const summary = document.querySelector<HTMLElement>('[data-testid="transacciones-summary"]')!;
    assert.match(summary.querySelector('[data-total="entradas"]')?.textContent ?? "", /^Entradas-sin dato$/);
    assert.match(summary.querySelector('[data-total="por_igualar"]')?.textContent ?? "", /1/);
    const row = page.row("l1")!;
    assert.match(row.querySelector('[data-col="contraparte"]')?.textContent ?? "", /COMPRA POS COLMADO/);
    assert.match(row.querySelector('[data-col="cuenta"]')?.textContent ?? "", /sin dato/);
    assert.equal(row.querySelector('[data-row-action="sin_comprobante"]'), null, "no Sin comprobante the server cannot take");
  });

  test("density: Normal 48 by default; Compacto 40 and Amplio 56 from the view options, remembered in this browser", async () => {
    const page = await mount();
    await page.ready();
    const height = () => page.row("mv-ferreteria")!.style.height;
    assert.equal(page.grid()!.dataset.density, "normal");
    assert.equal(height(), "48px");
    await page.click(document.querySelector('[data-testid="transacciones-view-options"]'));
    const options = [...document.querySelectorAll<HTMLElement>("[data-density-option]")];
    assert.deepEqual(options.map((option) => option.textContent?.trim()), ["Compacto", "Normal", "Amplio"]);
    await page.click(document.querySelector('[data-density-option="compacto"]'));
    assert.equal(height(), "40px");
    assert.equal(localStorage.getItem(DENSITY_KEY), "compacto");
    await page.unmount();
    (await import("@/components/business-app/transacciones/table-density")).resetTableDensity();
    localStorage.setItem(DENSITY_KEY, "amplio");
    const again = await mount();
    await again.ready();
    assert.equal(again.row("mv-ferreteria")!.style.height, "56px");
  });

  test("a phone ignores density: two-line rows of at least 64px with a kebab", async () => {
    localStorage.setItem(DENSITY_KEY, "compacto");
    const page = await mount({ width: 390 });
    await page.ready();
    assert.equal(page.grid(), null, "no table on a phone");
    const row = page.row("mv-ferreteria")!;
    assert.match(row.className, /min-h-16/);
    assert.ok(row.querySelector('[data-testid="row-kebab"]'));
    assert.equal(document.querySelector('[data-testid="transacciones-view-options"]'), null);
  });
});

describe("Transacciones decisions", () => {
  test("Igualar from the row confirms, moves the row to Igualadas, and Deshacer brings it back", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.row("mv-ferreteria")!.querySelector('[data-row-action="igualar"]'));
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina, RD$ 3,450.00"), "the confirm toast");
    await page.settle(() => page.row("mv-ferreteria") === null, "the row to leave Por igualar");
    await page.click(page.segment("igualadas"));
    assert.equal(page.row("mv-ferreteria")?.dataset.state, "igualada");
    const undo = [...document.querySelectorAll<HTMLButtonElement>('[data-testid="toast-viewport"] button')].find((button) => button.textContent === "Deshacer");
    await page.click(undo!);
    await page.click(page.segment("por_igualar"));
    await page.settle(() => page.row("mv-ferreteria")?.dataset.state === "sugerencia", "the suggestion back");
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
    for (const step of [1, 2, 3]) {
      const igualar = document.querySelector<HTMLButtonElement>('[data-tray-action="igualar"]')!;
      await page.click(igualar);
      if (step < 3) await page.settle(() => (tray()?.textContent ?? "").includes(`Sugerencia ${step + 1} de 3`), `step ${step + 1}`);
    }
    await page.settle(() => page.body().includes("3 igualadas"), "the shared toast");
    const viewport = document.querySelector('[data-testid="toast-viewport"]')!;
    assert.equal(viewport.children.length, 1, "one toast on screen");
    assert.doesNotMatch(viewport.textContent ?? "", /Igualada:/);
    assert.equal([...viewport.querySelectorAll("button")].filter((button) => button.textContent === "Deshacer").length, 1);
    await page.settle(() => document.querySelector('[data-testid="transacciones-run"]') === null, "the run button to leave with no suggestions");
  });

  test("No es este declines the pair and the row waits for its comprobante", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.row("mv-repuestos")!.querySelector('[data-row-action="rechazar"]'));
    await page.settle(() => page.row("mv-repuestos")?.dataset.state === "falta_comprobante", "the declined row");
  });

  test("Sin comprobante asks why, and the reason says it on the row", async () => {
    const page = await mount();
    await page.ready();
    await page.click(page.row("mv-colmado")!.querySelector('[data-row-action="sin_comprobante"]'));
    await page.settle(() => document.querySelector('[data-reason="compra_informal"]') !== null, "the reasons");
    assert.deepEqual([...document.querySelectorAll("[data-reason]")].map((node) => node.textContent?.trim()), ["Cargo del banco", "Entre mis cuentas", "Compra informal", "Personal"]);
    await page.click(document.querySelector('[data-reason="compra_informal"]'));
    await page.settle(() => page.row("mv-colmado") === null, "the row to leave Por igualar");
    await page.click(page.segment("igualadas"));
    assert.equal(page.row("mv-colmado")?.dataset.state, "no_lleva");
    assert.match(page.row("mv-colmado")!.textContent ?? "", /Compra informal/);
    assert.ok([...document.querySelectorAll('[data-testid="toast-viewport"] button')].some((button) => button.textContent === "Deshacer"));
  });

  test("a failed Igualar says so inline with Reintentar, never in a toast, and Reintentar finishes it", async () => {
    const { createSampleTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-sample");
    const page = await mount({ transacciones: createSampleTransaccionesSource({ failDecide: true }) });
    await page.ready();
    await page.click(page.row("mv-ferreteria")!.querySelector('[data-row-action="igualar"]'));
    await page.settle(() => document.querySelector('[data-testid="transacciones-decision-error"]') !== null, "the inline error");
    const error = document.querySelector<HTMLElement>('[data-testid="transacciones-decision-error"]')!;
    assert.equal(error.getAttribute("role"), "alert");
    assert.match(error.textContent ?? "", /Ref\./);
    assert.equal(document.querySelector('[data-testid="toast-viewport"]')?.textContent, "");
    await page.click([...error.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!);
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina"), "the retried confirm");
  });

  test("a list that fails to load says so with Reintentar", async () => {
    const { createSampleTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-sample");
    const page = await mount({ transacciones: createSampleTransaccionesSource({ failLoad: true }) });
    await page.settle(() => document.querySelector('[data-testid="transacciones-error"]') !== null, "the load error");
    assert.match(page.body(), /No pudimos cargar tus movimientos/);
    assert.ok([...document.querySelectorAll('[data-testid="transacciones-error"] button')].some((button) => button.textContent === "Reintentar"));
  });

  test("without undo on the server, the confirm toast offers no Deshacer", async () => {
    const { createSampleTransaccionesSource } = await import("@/components/business-app/transacciones/transacciones-sample");
    const sample = createSampleTransaccionesSource();
    const page = await mount({ transacciones: { load: sample.load, decide: sample.decide, supports: sample.supports } });
    await page.ready();
    await page.click(page.row("mv-ferreteria")!.querySelector('[data-row-action="igualar"]'));
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina"), "the confirm toast");
    assert.ok(![...document.querySelectorAll('[data-testid="toast-viewport"] button')].some((button) => button.textContent === "Deshacer"));
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
    await page.settle(() => page.body().includes("Igualada: Ferretería La Esquina"), "the keyed igualar");
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
