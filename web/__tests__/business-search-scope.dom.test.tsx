import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import ChatCommandPalette from "@/components/sidebar/ChatCommandPalette";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { useBusinessSearch } from "@/components/business-app/useBusinessSearch";
import type { SearchableList } from "@/components/business-app/foundation/list-search";
import type { BusinessActions } from "@/components/business-app/business-actions";
import type { BusinessSearchResult } from "@/lib/business-search-api";
import spanish from "@/public/locales/es-419/common.json";

// The search window asks the server only for the kinds of results its scope keeps. A Facturación section keeps none,
// so its window offers "Filtrar <lista> por …" and never claims the whole Business has nothing.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/business" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterEach(async () => {
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
  localStorage.clear();
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const actions: BusinessActions = { create: [], composer: [], starterEntries: [] };
const NONE: BusinessSearchResult = { expenses: [], ventas: [], receipts: [], accounts: [], email_deliveries: [], email_senders: [], next_cursors: {} };

async function mount(list: SearchableList | null, search: () => Promise<BusinessSearchResult>) {
  const queries: string[] = [];
  const applied: string[] = [];
  const source = { ...createFixtureBusinessDataSource(), search: async (query: string) => { queries.push(query); return search(); } };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  function Harness() {
    const workspaceSearch = useBusinessSearch({
      source, accounts: [], openPanel: () => undefined, actions, owner: true, scope: "own", canExport: true, openExport: () => undefined,
      listScope: list ? { list, apply: (query) => applied.push(query) } : null,
    });
    const [open, setOpen] = useState(false);
    const workspace = { id: "business", conversationSurface: "business", chatAvailable: false, search: workspaceSearch } as unknown as ChatWorkspace;
    return (
      <ChatWorkspaceProvider value={workspace}>
        <button type="button" data-testid="opener" onClick={() => setOpen(true)}>Buscar</button>
        {open ? <ChatCommandPalette onClose={() => setOpen(false)} onOpenConversation={() => undefined} onRetest={() => undefined} activeConversationId={null} /> : null}
      </ChatWorkspaceProvider>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>));
  await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="opener"]')!.click());
  return { queries, applied, unmount: () => act(async () => root.unmount()) };
}

const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
async function type(value: string) {
  const input = document.querySelector<HTMLInputElement>("input")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
const window_ = () => ({
  searching: document.querySelector('[data-testid="workspace-search-results"] [role="status"]') !== null,
  failed: document.querySelector('[data-testid="workspace-search-results"] [role="alert"]') !== null,
  noMatch: document.querySelector('[data-testid="workspace-search-no-match"] p')?.textContent ?? null,
  filterRow: document.querySelector('[data-testid="workspace-search-filter-list"]')?.textContent ?? null,
  chip: document.querySelector('[data-testid="workspace-search-scope"]')?.textContent ?? null,
});

test("a Facturación section's window sends no Business search and shows no searching, failure or no-match", async () => {
  for (const list of ["invoices", "customers", "schedules"] as const) {
    const view = await mount(list, async () => { throw new Error("search must not run"); });
    try {
      await type("Brisa");
      const seen: ReturnType<typeof window_>[] = [];
      for (let i = 0; i < 12; i++) { seen.push(window_()); await wait(50); }
      seen.push(window_());
      assert.deepEqual(view.queries, [], `${list}: no request`);
      assert.ok(seen.every((state) => !state.searching), `${list}: never "Buscando"`);
      assert.ok(seen.every((state) => !state.failed), `${list}: no failure alert`);
      assert.ok(seen.every((state) => state.noMatch === null), `${list}: no "No encontramos nada"`);
      assert.ok(window_().filterRow?.includes("Brisa"), `${list}: the filter row stays`);
      assert.ok(window_().chip?.startsWith("En "), `${list}: the scope chip stays`);
    } finally { await view.unmount(); }
  }
});

test("removing a Facturación scope searches the whole Business", async () => {
  const view = await mount("invoices", async () => NONE);
  try {
    await type("Brisa");
    await wait(400);
    assert.deepEqual(view.queries, []);
    await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="workspace-search-scope"] button')!.click());
    await wait(500);
    assert.deepEqual(view.queries, ["Brisa"], "the unscoped window asks the server");
    assert.equal(window_().chip, null);
    assert.ok(window_().noMatch?.includes("Brisa"));
  } finally { await view.unmount(); }
});

test("a scope that keeps results (Bandeja, Registros) and chat search still search and say when nothing matched", async () => {
  for (const list of ["inbox", "transactions", null] as const) {
    const view = await mount(list, async () => NONE);
    try {
      await type("Brisa");
      await wait(500);
      assert.deepEqual(view.queries, ["Brisa"], `${list}: one request`);
      assert.ok(window_().noMatch?.includes("Brisa"), `${list}: no-match copy`);
      assert.equal(window_().chip !== null, list !== null, `${list}: chip`);
    } finally { await view.unmount(); }
  }
});

test("a Bandeja window whose search fails shows the failure alert", async () => {
  const view = await mount("inbox", async () => { throw Object.assign(new Error("unavailable"), { status: 500 }); });
  try {
    await type("Brisa");
    await wait(500);
    assert.deepEqual(view.queries, ["Brisa"]);
    assert.equal(window_().failed, true);
  } finally { await view.unmount(); }
});
