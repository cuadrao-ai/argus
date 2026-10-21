import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { Plus } from "lucide-react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import ChatCommandPalette from "@/components/sidebar/ChatCommandPalette";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { useBusinessSearch } from "@/components/business-app/useBusinessSearch";
import type { BusinessActions } from "@/components/business-app/business-actions";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { BusinessExpense } from "@/lib/business-api";
import type { BusinessSearchKind, BusinessSearchResult } from "@/lib/business-search-api";
import spanish from "@/public/locales/es-419/common.json";

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

const actions: BusinessActions = { create: [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: () => undefined }], composer: [], starterEntries: [] };

const NONE: BusinessSearchResult = { expenses: [], ventas: [], receipts: [], accounts: [], email_deliveries: [], email_senders: [], next_cursors: {} };
const sale = (n: number): BusinessExpense => ({ id: `venta-${n}`, merchant: `Cliente ${n}`, amount: "1000.00", currency: "DOP", category_id: null, account_id: null, occurred_on: "2026-10-01", receipt_id: null, draft_id: null });
const ventas = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, index) => sale(from + index));
const failure = (status: number, code = "unknown") => Object.assign(new Error(code), { status, code });

type Overrides = Partial<BusinessDataSource>;

async function mount(overrides: Overrides = {}) {
  const source: BusinessDataSource = { ...createFixtureBusinessDataSource(), ...overrides };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const opened: BusinessPanelState[] = [];
  function Harness() {
    const search = useBusinessSearch({ source, accounts: [], openPanel: (panel) => opened.push(panel), actions, owner: true, scope: "own", openExport: () => undefined });
    const [open, setOpen] = useState(false);
    const workspace = { id: "business", conversationSurface: "business", chatAvailable: false, search } as unknown as ChatWorkspace;
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
  const input = () => document.querySelector<HTMLInputElement>("input")!;
  const openSearch = async () => {
    const opener = document.querySelector<HTMLButtonElement>('[data-testid="opener"]')!;
    opener.focus();
    await act(async () => opener.click());
    await settle();
  };
  return { opened, input, openSearch, unmount: () => act(async () => root.unmount()) };
}

async function settle(ms = 500) {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
}

async function type(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await settle();
}

const group = (label: string) => document.querySelector(`[role="group"][aria-label="${label}"]`);
const ROW = "[data-workspace-hit]:not([data-group-reveal]):not([data-group-load]), [data-testid=workspace-hit-static]";
const titles = (label: string) => Array.from(group(label)?.querySelectorAll(ROW) ?? []).map((row) => row.querySelector("span span")?.textContent ?? "");
const button = (label: string, selector: string) => group(label)?.querySelector<HTMLButtonElement>(selector) ?? null;
const click = async (target: Element | null) => { assert.ok(target, "the control is there"); await act(async () => { target.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 0 })); }); await settle(50); };
const headers = () => Array.from(document.querySelectorAll("[data-workspace-group]")).map((node) => node.getAttribute("aria-label"));

test("six groups, in the order Gastos, Ventas, Recibos, Cuentas, Correos, Remitentes, each with a Spanish header and three rows", async () => {
  const everything: BusinessSearchResult = {
    ...NONE,
    expenses: [{ ...sale(1), id: "exp-1", merchant: "Ferretería uno" }],
    ventas: ventas(1, 4),
    receipts: [{ id: "rcpt-1", channel: "web", filename: "uno.jpg", media_type: "image/jpeg", size_bytes: 1, received_at: "2026-10-01T10:00:00Z", status: "review_ready", error_code: null, expense_id: null, merchant: "Recibo uno", occurred_on: null, amount: null, currency: null, category_id: null, account_id: null }],
    accounts: [{ id: "acct-1", nickname: "Caja", type: "cash", currency: "DOP" }],
    email_deliveries: [{ id: "mail-1", sender: null, subject: null, received_at: "2026-10-01T10:00:00Z", state: "received", inbox_group: null }],
    email_senders: [{ id: "snd-1", kind: "domain", value: "proveedor.example", status: "blocked" }],
  };
  const view = await mount({ search: async () => everything });
  try {
    await view.openSearch();
    await type(view.input(), "cliente");
    assert.deepEqual(headers(), ["Gastos", "Ventas", "Recibos", "Cuentas", "Correos", "Remitentes"]);
    assert.equal(titles("Ventas").length, 3, "three rows of four");
    assert.equal(button("Ventas", "[data-group-reveal]")?.textContent, "Ver más (1)");
    assert.equal(button("Ventas", "[data-group-load]"), null, "nothing to fetch while rows are hidden");
    const email = group("Correos")!.textContent ?? "";
    assert.ok(email.includes("—"), `an email with no subject or sender shows — : ${email}`);
    assert.ok(!/\b0\b/.test(group("Recibos")!.textContent ?? ""), "an unknown receipt amount is never 0");
    assert.ok((group("Recibos")!.textContent ?? "").includes("—"));
  } finally { await view.unmount(); }
});

test("Ver más shows loaded rows, Cargar más fetches the next cursor, and the labels never swap", async () => {
  const calls: [string, BusinessSearchKind, string][] = [];
  const view = await mount({
    search: async () => ({ ...NONE, ventas: ventas(1, 5), next_cursors: { ventas: "cur-1" } }),
    searchMore: async (query, kind, cursor) => {
      calls.push([query, kind, cursor]);
      return cursor === "cur-1" ? { ...NONE, ventas: ventas(6, 10), next_cursors: { ventas: "cur-2" } } : { ...NONE, ventas: ventas(11, 12), next_cursors: { ventas: null } };
    },
  });
  try {
    await view.openSearch();
    await type(view.input(), "cliente");
    assert.deepEqual(titles("Ventas"), ["Cliente 1", "Cliente 2", "Cliente 3"]);
    assert.equal(button("Ventas", "[data-group-reveal]")?.textContent, "Ver más (2)");
    assert.equal(calls.length, 0);

    await click(button("Ventas", "[data-group-reveal]"));
    assert.equal(titles("Ventas").length, 5);
    assert.equal(calls.length, 0, "Ver más never calls the server");
    assert.equal(button("Ventas", "[data-group-reveal]")?.textContent, "Ver menos");
    assert.equal(button("Ventas", "[data-group-load]")?.textContent, "Cargar más");

    await click(button("Ventas", "[data-group-load]"));
    assert.deepEqual(calls, [["cliente", "ventas", "cur-1"]]);
    assert.equal(titles("Ventas").length, 10);
    await click(button("Ventas", "[data-group-load]"));
    assert.deepEqual(calls[1], ["cliente", "ventas", "cur-2"]);
    assert.equal(titles("Ventas").length, 12);
    assert.equal(button("Ventas", "[data-group-load]"), null, "no cursor, no Cargar más");
  } finally { await view.unmount(); }
});

test("a failed load keeps the rows, says so inline with Reintentar, and the retry asks for the same page", async () => {
  let attempts = 0;
  const cursors: string[] = [];
  const view = await mount({
    search: async () => ({ ...NONE, ventas: ventas(1, 5), next_cursors: { ventas: "cur-1" } }),
    searchMore: async (_query, _kind, cursor) => {
      cursors.push(cursor);
      if (++attempts === 1) throw failure(500);
      return { ...NONE, ventas: ventas(6, 7) };
    },
  });
  try {
    await view.openSearch();
    await type(view.input(), "cliente");
    await click(button("Ventas", "[data-group-reveal]"));
    await click(button("Ventas", "[data-group-load]"));
    assert.equal(titles("Ventas").length, 5, "the rows stay");
    assert.ok((group("Ventas")!.querySelector("[data-group-load-error]")?.textContent ?? "").includes("No pudimos cargar más resultados"));
    assert.equal(button("Ventas", "[data-group-load]")?.textContent, "Reintentar");
    assert.equal(document.querySelector("[data-toast], [role=status][data-kind=error]"), null, "a failure is never a toast");
    await click(button("Ventas", "[data-group-load]"));
    assert.deepEqual(cursors, ["cur-1", "cur-1"]);
    assert.equal(titles("Ventas").length, 7);
    assert.equal(group("Ventas")!.querySelector("[data-group-load-error]"), null);
  } finally { await view.unmount(); }
});

test("a stale cursor silently searches again from page 1 and shows no error", async () => {
  let searches = 0;
  const view = await mount({
    search: async () => ({ ...NONE, ventas: searches++ === 0 ? ventas(1, 5) : ventas(21, 25), next_cursors: { ventas: "cur-new" } }),
    searchMore: async () => { throw failure(409, "business_search_stale_cursor"); },
  });
  try {
    await view.openSearch();
    await type(view.input(), "cliente");
    await click(button("Ventas", "[data-group-reveal]"));
    await click(button("Ventas", "[data-group-load]"));
    assert.equal(searches, 2);
    assert.equal(group("Ventas")!.querySelector("[data-group-load-error]"), null);
    assert.equal(document.querySelector("[role=alert]"), null);
    assert.deepEqual(titles("Ventas"), ["Cliente 21", "Cliente 22", "Cliente 23", "Cliente 24", "Cliente 25"]);
    assert.equal(button("Ventas", "[data-group-load]")?.textContent, "Cargar más", "the new first page has its own next page");
  } finally { await view.unmount(); }
});

test("an invalid cursor says it failed, and its retry starts from page 1 instead of repeating the bad cursor", async () => {
  let searches = 0;
  let loads = 0;
  const view = await mount({
    search: async () => { searches++; return { ...NONE, ventas: ventas(1, 5), next_cursors: { ventas: "bad" } }; },
    searchMore: async () => { loads++; throw failure(422, "business_search_invalid_cursor"); },
  });
  try {
    await view.openSearch();
    await type(view.input(), "cliente");
    await click(button("Ventas", "[data-group-reveal]"));
    await click(button("Ventas", "[data-group-load]"));
    assert.equal(button("Ventas", "[data-group-load]")?.textContent, "Reintentar");
    await click(button("Ventas", "[data-group-load]"));
    assert.deepEqual([loads, searches], [1, 2]);
    assert.equal(group("Ventas")!.querySelector("[data-group-load-error]"), null);
  } finally { await view.unmount(); }
});

test("a backend without cursors or the new lists keeps today's search: no Cargar más, no error", async () => {
  const view = await mount({
    search: async () => ({ ...NONE, expenses: [{ ...sale(1), id: "exp-1", merchant: "Ferretería uno" }] }),
    searchMore: undefined,
  });
  try {
    await view.openSearch();
    await type(view.input(), "ferreteria");
    assert.deepEqual(headers(), ["Gastos"]);
    assert.equal(document.querySelector("[data-group-load]"), null);
    assert.equal(document.querySelector("[role=alert]"), null);
  } finally { await view.unmount(); }
});

test("results open where they live and each open is recorded without waiting for the answer", async () => {
  const recorded: [BusinessSearchKind, string][] = [];
  const view = await mount({
    search: async () => ({
      ...NONE,
      ventas: [sale(1)],
      email_deliveries: [{ id: "mail-1", sender: "ventas@proveedor.example", subject: "Factura 12", received_at: "2026-10-01T10:00:00Z", state: "captured", inbox_group: "bandeja" }],
      email_senders: [{ id: "snd-1", kind: "address", value: "ventas@proveedor.example", status: "authorized" }],
    }),
    recordSearchOpen: async (kind, id) => { recorded.push([kind, id]); throw failure(404); },
  });
  try {
    for (const [label, expected] of [
      ["Ventas", { kind: "expense", expenseId: "venta-1" }],
      ["Correos", { kind: "email", emailId: "mail-1" }],
      ["Remitentes", { kind: "business", tab: "correo" }],
    ] as const) {
      await view.openSearch();
      await type(view.input(), "proveedor");
      await click(group(label)!.querySelector(ROW));
      assert.deepEqual(view.opened.at(-1), expected, label);
    }
    assert.deepEqual(recorded, [["ventas", "venta-1"], ["email_deliveries", "mail-1"], ["email_senders", "snd-1"]]);
  } finally { await view.unmount(); }
});

test("recents come from the server, one can be removed and all can be cleared", async () => {
  const removed: string[] = [];
  let cleared = 0;
  let rows = [{ id: "r1", q: "ferretería", searched_at: "2026-10-01T10:00:00Z" }, { id: "r2", q: "colmado", searched_at: "2026-10-01T09:00:00Z" }];
  const view = await mount({
    searchRecents: async () => rows,
    removeSearchRecent: async (id) => { removed.push(id); rows = rows.filter((row) => row.id !== id); },
    clearSearchRecents: async () => { cleared++; rows = []; },
  });
  try {
    await view.openSearch();
    const shown = () => Array.from(group("Búsquedas recientes")?.querySelectorAll("[data-recent-search]") ?? []).map((row) => row.textContent);
    assert.deepEqual(shown(), ["ferretería", "colmado"]);
    await click(group("Búsquedas recientes")!.querySelector('[aria-label="Quitar «ferretería» de las búsquedas recientes"]'));
    assert.deepEqual(removed, ["r1"]);
    assert.deepEqual(shown(), ["colmado"]);
    await click(group("Búsquedas recientes")!.querySelector("[data-recent-clear]"));
    assert.equal(cleared, 1);
    assert.equal(group("Búsquedas recientes"), null);
  } finally { await view.unmount(); }
});

test("a backend without recents answers 404 and the browser keeps its own, quietly", async () => {
  const missing = async () => { throw failure(404); };
  const view = await mount({ searchRecents: missing, addSearchRecent: missing, removeSearchRecent: missing, clearSearchRecents: missing });
  try {
    await view.openSearch();
    await type(view.input(), "ferreteria");
    await click(group("Recibos")!.querySelector(ROW));
    await view.openSearch();
    const shown = () => Array.from(group("Búsquedas recientes")?.querySelectorAll("[data-recent-search]") ?? []).map((row) => row.textContent);
    assert.deepEqual(shown(), ["ferreteria"]);
    assert.equal(document.querySelector("[role=alert]"), null);
    await click(group("Búsquedas recientes")!.querySelector("[data-recent-remove]"));
    assert.equal(group("Búsquedas recientes"), null);
  } finally { await view.unmount(); }
});

test("rows loaded by Cargar más count in the footer and preview like the first rows", async () => {
  const view = await mount({
    search: async () => ({ ...NONE, ventas: ventas(1, 5), next_cursors: { ventas: "cur-1" } }),
    searchMore: async () => ({ ...NONE, ventas: ventas(6, 7) }),
  });
  try {
    await view.openSearch();
    await type(view.input(), "cliente");
    await click(button("Ventas", "[data-group-reveal]"));
    assert.ok((document.body.textContent ?? "").includes("5 resultados"));
    await click(button("Ventas", "[data-group-load]"));
    assert.ok((document.body.textContent ?? "").includes("7 resultados"), "the footer counts what is listed");
    const sixth = Array.from(group("Ventas")!.querySelectorAll(ROW))[5] as HTMLElement;
    await act(async () => { sixth.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 1 })); });
    await settle(50);
    assert.ok(document.querySelector("[data-dossier-pane] h2, [data-dossier-pane]")?.textContent?.includes("Cliente 6"), "a loaded row opens its preview");
  } finally { await view.unmount(); }
});
