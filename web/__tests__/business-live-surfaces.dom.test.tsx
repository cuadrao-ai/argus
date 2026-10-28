import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

// Inicio and Actividad on a live Business: only what the server sends, never the local preview's samples.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

// The Actividad feed answers from here; nothing else on these screens is served, so every other live read fails
// and must leave its element out rather than fall back to samples. No environment is changed.
const requested: (string | null)[] = [];
let feed: (cursor: string | null) => Promise<unknown> = async () => ({ items: [], next_cursor: null });
mock.module("@/lib/business-activity-api", () => ({
  getBusinessActivity: (cursor: string | null) => { requested.push(cursor); return feed(cursor); },
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  requested.length = 0;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage", "assign_owner", "download", "export"], capabilities: ["read", "prepare", "approve"] } as GrantedSpace;

async function mount(query: string, overrides: Partial<BusinessDataSource> = {}) {
  search = query;
  window.history.replaceState(null, "", `/biz?${query}`);
  const { act, useEffect } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), mode: "live", spaces: async () => [OWN], spaceDirectory: async () => ({ spaces: [OWN], closed_spaces: [] }), ...overrides };
  const shell = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Shell() {
    const workspace = useChatWorkspace();
    const connect = workspace?.onShellChange;
    useEffect(() => { connect?.(shell as never); }, [connect]);
    return <main>{workspace?.panel(shell as never)}</main>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Shell />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 120 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  };
  const click = (element: Element) => act(async () => { (element as HTMLElement).click(); });
  return { host, settle, click, close: () => act(async () => root.unmount()) };
}

const item = (id: string, name: string, action: string, minutesAgo: number) => ({
  id, occurred_at: new Date(Date.now() - minutesAgo * 60_000).toISOString(), actor: { display_name: name, kind: "member" }, action, object: { kind: "draft", id: `d-${id}` },
});

describe("Actividad on a live Business", () => {
  test("lists the feed as it is: no filters, no Registro column, no record links, then Cargar más", async () => {
    feed = async (cursor) => cursor
      ? { items: [item("a3", "Carlos Méndez", "receipt_upload", 300)], next_cursor: null }
      : { items: [item("a1", "Lucía Peña", "approve_expense", 5), item("a2", "Lucía Peña", "a_new_action", 40)], next_cursor: "c-2" };
    const page = await mount("view=activity");
    try {
      await page.settle(() => page.host.textContent?.includes("Lucía Peña") === true);
      const text = page.host.textContent ?? "";
      assert.ok(text.includes("Lucía Peña"));
      assert.ok(text.includes("hizo un cambio"), "an action the screen does not know yet reads as other");
      const headers = [...(page.host.querySelector('[data-testid="business-activity-draft"] [class*="h-12"]')?.children ?? [])].map((cell) => cell.textContent);
      assert.deepEqual(headers, ["Quién", "Qué pasó", "Área", "Hora"], "no Registro column until the feed names records");
      assert.equal([...page.host.querySelectorAll("button")].some((button) => button.textContent?.includes("Filtros")), false);
      assert.equal(page.host.querySelector('[data-testid="business-activity-draft"] li button'), null, "rows open nothing");
      const more = [...page.host.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Cargar más");
      assert.ok(more, "Cargar más while the feed has a next cursor");
      await page.click(more);
      await page.settle(() => page.host.textContent?.includes("Carlos Méndez") === true);
      assert.deepEqual(requested, [null, "c-2"]);
      assert.equal([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Cargar más"), false);
    } finally { await page.close(); }
  });

  test("a failed first page names the server's reference and offers a way back", async () => {
    feed = async () => { throw Object.assign(new Error("Unavailable"), { status: 503, requestId: "req-7f3a" }); };
    const page = await mount("view=activity");
    try {
      await page.settle(() => page.host.textContent?.includes("No pudimos cargar la actividad") === true);
      const text = page.host.textContent ?? "";
      assert.ok(text.includes("req-7f3a"));
      assert.ok(text.includes("Reintentar"));
      assert.ok(text.includes("Ir a Inicio"));
    } finally { await page.close(); }
  });
});

describe("Inicio on a live Business", () => {
  test("a Business that fails to load says so, never an endless skeleton", async () => {
    const page = await mount("view=overview", { overview: async () => { throw Object.assign(new Error("Not found"), { status: 404, code: "business_unavailable" }); } });
    try {
      await page.settle(() => page.host.querySelector('[data-testid="home-needs-attention"] [role="status"]') === null && page.host.textContent?.includes("No pudimos cargar lo que necesita atención") === true);
      const card = page.host.querySelector('[data-testid="home-needs-attention"]');
      assert.equal(card?.querySelector('[aria-busy="true"]'), null);
      assert.ok(card?.textContent?.includes("No pudimos cargar lo que necesita atención"));
      assert.equal(card?.textContent?.includes("Reintentar"), false, "a refused Business offers no retry that cannot help");
    } finally { await page.close(); }
  });

  test("shows no sample recents or setup, and no count it could not read", async () => {
    const page = await mount("view=overview");
    try {
      await page.settle(() => page.host.querySelector('[data-testid="home-needs-attention"]') !== null);
      const text = page.host.textContent ?? "";
      for (const sample of ["Factura a Taller Brisa", "Configurar negocio", "Continuar trabajando", "registros por revisar", "facturas en borrador"]) {
        assert.ok(!text.includes(sample), `no "${sample}" on a live Business without its data`);
      }
    } finally { await page.close(); }
  });
});
