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

let registeredFetch: typeof globalThis.fetch;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  registeredFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("Unavailable"); };
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  requested.length = 0;
});
afterAll(async () => {
  globalThis.fetch = registeredFetch;
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage", "assign_owner", "download", "export"], capabilities: ["read", "prepare", "approve"] } as GrantedSpace;

async function mount(query: string, overrides: Partial<BusinessDataSource> = {}, userId: string | null = null) {
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
          <BusinessWorkspaceProvider source={source as never} userId={userId}>
            <Shell />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 120 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  };
  const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
  const click = (element: Element) => act(async () => { (element as HTMLElement).click(); });
  return { host, settle, wait, click, close: () => act(async () => root.unmount()) };
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

for (const action of ["delete_document", "restore_document"] as const) {
  test(`Actividad links ${action} to the document's current surface`, async () => {
    feed = async () => ({ items: [{ ...item("document-event", "Lucía Peña", action, 5), object: { kind: "receipt", id: "rcpt-blurry", label: "Documento equivocado" } }], next_cursor: null });
    const page = await mount("view=activity");
    try {
      const label = action === "delete_document" ? "Ver en Eliminados" : "Abrir";
      await page.settle(() => page.host.textContent?.includes(label) === true);
      const row = [...page.host.querySelectorAll<HTMLButtonElement>('[data-testid="business-activity-draft"] button')].find(button => button.textContent?.includes(label));
      assert.ok(row);
      assert.match(row.textContent ?? "", action === "delete_document" ? /eliminó Documento equivocado/ : /restauró Documento equivocado/);
      await page.click(row);
      if (action === "delete_document") {
        await page.settle(() => !!page.host.querySelector('#reception-tab-eliminados[aria-selected="true"]'));
        assert.ok(page.host.querySelector('#reception-tab-eliminados[aria-selected="true"]'));
      } else {
        await page.settle(() => !!document.querySelector('[data-testid="receipt-original-source"]'));
        assert.ok(document.querySelector('[data-testid="receipt-original-source"]'));
      }
    } finally { await page.close(); }
  });
}

for (const [action, words] of [["purge_document", "eliminó definitivamente un documento."], ["expire_document", "eliminó definitivamente un documento después de 7 días en Eliminados."]] as const) {
  test(`Actividad shows ${action} with no name and no link`, async () => {
    const actor = action === "expire_document" ? { display_name: "Cuadrao", kind: "extractor" } : { display_name: "Lucía Peña", kind: "member" };
    feed = async () => ({ items: [{ ...item("purge-event", "Lucía Peña", action, 5), actor, object: null }], next_cursor: null });
    const page = await mount("view=activity");
    try {
      await page.settle(() => page.host.textContent?.includes(words) === true);
      const surface = page.host.querySelector('[data-testid="business-activity-draft"]');
      assert.ok(surface);
      assert.ok(surface.textContent?.includes(action === "expire_document" ? "Cuadrao" : "Lucía Peña"));
      assert.equal([...surface.querySelectorAll("button")].filter(button => button.textContent?.includes("eliminó definitivamente")).length, 0);
    } finally { await page.close(); }
  });
}

describe("Actividad failures carry a reference", () => {
  const failWith = (requestId?: string) => async () => { throw Object.assign(new Error("Unavailable"), { status: 503, ...(requestId ? { requestId } : {}) }); };

  test("a failed first page without a request id still shows a Ref. and Reintentar", async () => {
    feed = failWith();
    const page = await mount("view=activity");
    try {
      await page.settle(() => page.host.textContent?.includes("No pudimos cargar la actividad") === true);
      const text = page.host.textContent ?? "";
      assert.match(text, /Ref\. c[0-9a-f]{7}/);
      assert.ok(text.includes("Reintentar"));
      assert.ok(text.includes("Ir a Inicio"));
    } finally { await page.close(); }
  });

  for (const [label, requestId, expected] of [["the server's request id", "req-5b21c9de", /Ref\. req-5b21/], ["a generated reference when the server sent none", undefined, /Ref\. c[0-9a-f]{7}/]] as const) {
    test(`a failed Cargar más keeps the rows and shows ${label}`, async () => {
      feed = async (cursor) => {
        if (cursor) return failWith(requestId)();
        return { items: [item("a1", "Lucía Peña", "approve_expense", 5)], next_cursor: "c-2" };
      };
      const page = await mount("view=activity");
      try {
        await page.settle(() => page.host.textContent?.includes("Lucía Peña") === true);
        const more = [...page.host.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Cargar más");
        assert.ok(more);
        await page.click(more);
        await page.settle(() => page.host.textContent?.includes("No pudimos cargar más actividad") === true);
        const text = page.host.textContent ?? "";
        assert.match(text, expected);
        assert.ok(text.includes("Lucía Peña"), "the rows already shown stay");
        assert.ok([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Cargar más"), "and so does the way to try again");
      } finally { await page.close(); }
    });
  }
});

describe("Inicio on a live Business", () => {
  test("a Business that fails to load says so, never an endless skeleton", async () => {
    const page = await mount("view=overview", { overview: async () => { throw Object.assign(new Error("Not found"), { status: 404, code: "business_unavailable" }); } });
    try {
      await page.settle(() => page.host.querySelector('[data-testid="home-attention"] [role="status"]') === null && page.host.textContent?.includes("No pudimos cargar lo pendiente.") === true);
      const card = page.host.querySelector('[data-testid="home-attention"]');
      assert.equal(card?.querySelector('[aria-busy="true"]'), null);
      assert.ok(card?.textContent?.includes("No pudimos cargar lo pendiente."));
      assert.equal(card?.textContent?.includes("Reintentar"), false, "a refused Business offers no retry that cannot help");
    } finally { await page.close(); }
  });

  const failedCard = (page: { host: HTMLElement }) => page.host.querySelector('[data-testid="home-attention"] [role="status"]') === null && page.host.textContent?.includes("No pudimos cargar lo pendiente.") === true;
  const cardReference = (page: { host: HTMLElement }) => page.host.querySelector('[data-testid="home-attention"] [data-testid="error-reference"]')?.getAttribute("title") ?? "";

  test("a refused Business's failed card shows the server's request id", async () => {
    const page = await mount("view=overview", { overview: async () => { throw Object.assign(new Error("Not found"), { status: 404, code: "business_unavailable", requestId: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" }); } });
    try {
      await page.settle(() => failedCard(page));
      assert.equal(cardReference(page), "4ea79978-ce17-4853-b232-b2a72f4c9ce7");
    } finally { await page.close(); }
  });

  test("a failed card with no request id shows a generated Ref. beside Reintentar", async () => {
    const page = await mount("view=overview", { overview: async () => { throw Object.assign(new Error("Conflict"), { status: 409, code: "conflict" }); } });
    try {
      await page.settle(() => failedCard(page));
      assert.match(cardReference(page), /^c[0-9a-f]{8}$/);
      assert.ok(page.host.querySelector('[data-testid="home-attention"]')?.textContent?.includes("Reintentar"));
    } finally { await page.close(); }
  });

  const emptyBandeja = async (count = 0): Promise<Partial<BusinessDataSource>> => {
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const base = createFixtureBusinessDataSource({ chatAvailable: true });
    return { receipts: async () => [], receiptPage: async (...args: Parameters<NonNullable<typeof base.receiptPage>>) => {
      const page = await base.receiptPage!(...args);
      return { items: [], activity: { ...page.activity, pending_review_count: count, bandeja_attention_count: 0, bandeja_listo_count: count } };
    } };
  };
  const card = (page: { host: HTMLElement }) => page.host.querySelector('[data-testid="home-attention"]');

  test("shows a skeleton while the review count loads, never Todo al día", async () => {
    const page = await mount("view=overview", { receiptPage: () => new Promise(() => undefined) }, "u-1");
    try {
      await page.settle(() => card(page) !== null);
      await page.wait(600);
      assert.ok(card(page)?.querySelector('[aria-busy="true"]'), "a skeleton stands where the count will");
      assert.equal(page.host.textContent?.includes("Todo al día"), false);
    } finally { await page.close(); }
  });

  test("a failed shared receipt load shows its reference and retry, then recovers", async () => {
    const recovered = await emptyBandeja(3);
    let failedRead = true;
    const page = await mount("view=overview", { receiptPage: async (...args) => {
      if (failedRead) throw Object.assign(new Error("Unavailable"), { status: 500, requestId: "req-9c2d41ab" });
      return recovered.receiptPage!(...args);
    } }, "u-1");
    try {
      await page.settle(() => page.host.querySelector('[data-testid="server-error-screen"]') !== null);
      const failed = page.host.querySelector('[data-testid="server-error-screen"]');
      assert.ok(failed, "the count's failure is shown");
      assert.ok(failed.textContent?.includes("req-9c2d"), "the server's reference");
      assert.equal(page.host.textContent?.includes("Todo al día"), false, "a failed count is not zero");
      failedRead = false;
      const retry = [...failed.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Intentar de nuevo");
      assert.ok(retry);
      await page.click(retry);
      await page.settle(() => page.host.querySelector('[data-testid="home-attention-count"]') !== null);
      assert.equal(page.host.querySelector('[data-testid="home-attention-count"]')?.textContent, page.host.querySelector('[data-testid="business-inbox-count"]')?.textContent ?? "3", "the sidebar's one count");
      assert.equal(page.host.querySelector('[data-testid="server-error-screen"]'), null);
    } finally { await page.close(); }
  });

  test("an unknown review count keeps the Bandeja rows the server did send", async () => {
    const page = await mount("view=overview", { receiptPage: undefined }, "u-1");
    try {
      await page.settle(() => (card(page)?.querySelectorAll("li[data-kind]").length ?? 0) > 0);
      assert.ok((card(page)?.querySelectorAll("li[data-kind]").length ?? 0) > 0, "the rows the server sent");
      assert.equal(card(page)?.querySelector('[data-testid="home-attention-count"]'), null, "no count it could not read");
    } finally { await page.close(); }
  });

  test("a failed shared receipt load without a request id still shows a reference", async () => {
    const page = await mount("view=overview", { receiptPage: async () => { throw Object.assign(new Error("Unavailable"), { status: 500 }); } }, "u-1");
    try {
      await page.settle(() => page.host.querySelector('[data-testid="server-error-screen"]') !== null);
      assert.match(page.host.querySelector('[data-testid="server-error-screen"]')?.textContent ?? "", /Ref\. c[0-9a-f]{7}/);
      assert.equal(page.host.textContent?.includes("Todo al día"), false);
    } finally { await page.close(); }
  });

  test("says Todo al día only when the server counted zero", async () => {
    const page = await mount("view=overview", await emptyBandeja(), "u-1");
    try {
      await page.settle(() => card(page)?.textContent?.includes("Todo al día") === true);
      assert.ok(card(page)?.textContent?.includes("Todo al día"));
      assert.equal(page.host.querySelector('[data-testid="home-attention-count"]'), null);
    } finally { await page.close(); }
  });

  test("shows no sample recents or setup, and no count it could not read", async () => {
    const page = await mount("view=overview", { receiptPage: undefined, setup: undefined });
    try {
      await page.settle(() => (card(page)?.querySelectorAll("li[data-kind]").length ?? 0) > 0);
      const text = page.host.textContent ?? "";
      for (const sample of ["Factura a Taller Brisa", "Configurar negocio", "Continuar trabajando", "facturas en borrador"]) {
        assert.ok(!text.includes(sample), `no "${sample}" on a live Business without its data`);
      }
    } finally { await page.close(); }
  });
});
