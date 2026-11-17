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
import type { BusinessActivityPage } from "@/lib/business-activity-api";
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

type ActivityServer = (query: string, cursor?: string) => Promise<BusinessActivityPage>;

async function mount(list: SearchableList | null, search: () => Promise<BusinessSearchResult>, chatPalette = false, activity: ActivityServer = async () => ({ items: [], next_cursor: null })) {
  const queries: string[] = [];
  const applied: string[] = [];
  const activityReads: [string, string | undefined][] = [];
  const source = {
    ...createFixtureBusinessDataSource(),
    search: async (query: string) => { queries.push(query); return search(); },
    searchActivity: async (query: string, cursor?: string) => { activityReads.push([query, cursor]); return activity(query, cursor); },
  };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  function Harness() {
    const workspaceSearch = useBusinessSearch({ emailAvailable: true,
      source, accounts: [], openPanel: () => undefined, actions, canAdd: true, scope: "own", canExport: true, openExport: () => undefined,
      listScope: list ? { list, apply: list === "activity" ? undefined : (query) => applied.push(query) } : null,
    });
    const [open, setOpen] = useState(false);
    const workspace = { id: "business", conversationSurface: "business", chatAvailable: false, search: chatPalette ? null : workspaceSearch } as unknown as ChatWorkspace;
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
  return { queries, applied, activityReads, unmount: () => act(async () => root.unmount()) };
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

const panel = () => document.querySelector('[data-testid="workspace-search-panel"]');
const headerButton = (name: string) => [...document.querySelectorAll<HTMLButtonElement>(`button[aria-label="${name}"]`)].find((button) => button.tabIndex !== -1);

test("the X closes the Business search window, with text in the box or without", async () => {
  for (const text of ["Brisa", ""]) {
    const view = await mount("inbox", async () => NONE);
    try {
      if (text) await type(text);
      assert.ok(panel());
      assert.equal(headerButton("Borrar búsqueda"), undefined, "nothing here only clears the text");
      await act(async () => headerButton("Cerrar búsqueda")!.click());
      assert.equal(panel(), null, `closed with ${text ? "text" : "an empty box"}`);
    } finally { await view.unmount(); }
  }
});

test("Esc still closes the Business search window", async () => {
  const view = await mount("inbox", async () => NONE);
  try {
    await type("Brisa");
    await act(async () => { document.querySelector("input")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
    assert.equal(panel(), null);
  } finally { await view.unmount(); }
});

test("the chat palette's X still only clears the text", async () => {
  const view = await mount(null, async () => NONE, true);
  try {
    await type("Brisa");
    await act(async () => headerButton("Borrar búsqueda")!.click());
    assert.equal(document.querySelector("input")?.value, "", "the text is gone");
    assert.ok(document.querySelector("input"), "the window stays");
    assert.equal(headerButton("Borrar búsqueda"), undefined, "an empty box has no X");
  } finally { await view.unmount(); }
});

const change = (id: string, who: string, action: string, label?: string) => ({ id, occurred_at: "2026-11-10T14:00:00Z", actor: { display_name: who, shown_as: "name" as const, kind: "member" as const }, action, object: label ? { kind: "draft" as const, id: `draft-${id}`, label } : null });
const ACCOUNT: BusinessSearchResult = { ...NONE, accounts: [{ id: "account-1", nickname: "Cuenta de Lucía", type: "checking", currency: "DOP" }] };
const rows = () => [...document.querySelectorAll('[data-testid="workspace-search-results"] [data-workspace-group] :is([data-testid="workspace-hit-static"], [data-workspace-hit]:not([data-group-reveal], [data-group-load]))')].map((row) => row.textContent ?? "");
const removeChip = () => act(async () => document.querySelector<HTMLButtonElement>('[data-testid="workspace-search-scope"] button')!.click());

test("Actividad's window opens with its chip and lists the rows the server matched, with no list to filter", async () => {
  const view = await mount("activity", async () => ACCOUNT, false, async () => ({ items: [change("a1", "Lucía Peña", "approve_expense", "Ferretería La Esquina")], next_cursor: null }));
  try {
    assert.equal(window_().chip?.trim(), "En Actividad");
    await type("Lucía");
    await wait(500);
    assert.deepEqual(view.activityReads, [["Lucía", undefined]], "the server matches the query");
    assert.equal(rows().length, 1, "only Actividad's rows");
    assert.ok(rows()[0].includes("Lucía Peña aprobó un gasto"), rows()[0]);
    assert.ok(rows()[0].includes("Ferretería La Esquina"), rows()[0]);
    assert.equal(window_().filterRow, null, "Actividad has no filter to hand the query to");
  } finally { await view.unmount(); }
});

test("removing the Actividad chip searches the whole Business, as removing a list's chip does", async () => {
  for (const list of ["activity", "inbox"] as const) {
    const view = await mount(list, async () => ACCOUNT, false, async () => ({ items: [change("a1", "Lucía Peña", "receipt_upload")], next_cursor: null }));
    try {
      await type("Lucía");
      await wait(500);
      assert.ok(rows().every((row) => !row.includes("Cuenta de Lucía")), `${list}: the account is outside the scope`);
      await removeChip();
      await wait(500);
      assert.equal(window_().chip, null, list);
      assert.ok(rows().some((row) => row.includes("Cuenta de Lucía")), `${list}: the whole Business is searched`);
      assert.equal(rows().some((row) => row.includes("Lucía Peña subió un documento")), list === "activity", `${list}: Actividad's rows stay only on its screen`);
    } finally { await view.unmount(); }
  }
});

test("an Actividad search with no match says so in the search's own empty state", async () => {
  const view = await mount("activity", async () => ACCOUNT);
  try {
    await type("Brisa");
    await wait(500);
    assert.deepEqual(view.activityReads, [["Brisa", undefined]]);
    assert.ok(window_().noMatch?.includes("Brisa"));
    assert.equal(window_().chip?.trim(), "En Actividad");
  } finally { await view.unmount(); }
});

test("an Actividad search the server fails says the activity did not load", async () => {
  const view = await mount("activity", async () => NONE, false, async () => { throw Object.assign(new Error("unavailable"), { status: 503 }); });
  try {
    await type("Brisa");
    await wait(500);
    assert.equal(document.querySelector('[data-testid="workspace-search-results"] [role="alert"]')?.textContent, "No pudimos cargar la actividad");
    assert.equal(window_().noMatch, null);
  } finally { await view.unmount(); }
});

test("Cargar más reads Actividad's next rows by the server's cursor", async () => {
  const view = await mount("activity", async () => NONE, false, async (_query, cursor) => cursor
    ? { items: [change("a2", "Lucía Peña", "review_draft")], next_cursor: null }
    : { items: [change("a1", "Lucía Peña", "receipt_upload")], next_cursor: "next" });
  try {
    await type("Lucía");
    await wait(500);
    await act(async () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="workspace-search-results"] button')].find((button) => button.textContent?.trim() === "Cargar más")!.click());
    await wait(50);
    assert.deepEqual(view.activityReads, [["Lucía", undefined], ["Lucía", "next"]]);
    assert.deepEqual(rows().map((row) => row.includes("revisó un registro")), [false, true]);
  } finally { await view.unmount(); }
});
