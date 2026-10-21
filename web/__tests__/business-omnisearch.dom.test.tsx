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
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
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

const source = createFixtureBusinessDataSource();
const added: string[] = [];
const actions: BusinessActions = { create: [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: () => added.push("add") }], composer: [], starterEntries: [] };

async function mount() {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const opened: (BusinessPanelState | "export")[] = [];
  function Harness() {
    const search = useBusinessSearch({ source, accounts: [], openPanel: (panel) => opened.push(panel), actions, owner: true, scope: "own", openExport: () => opened.push("export") });
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
  const opener = () => document.querySelector<HTMLButtonElement>('[data-testid="opener"]')!;
  const input = () => document.querySelector<HTMLInputElement>("input")!;
  const openSearch = async () => {
    opener().focus();
    await act(async () => opener().click());
    await settle();
  };
  return { opened, opener, input, openSearch, unmount: () => act(async () => root.unmount()) };
}

async function settle(ms = 450) {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
}

async function type(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await settle();
}

async function key(target: Element, name: string) {
  await act(async () => { target.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true })); });
}

const group = (label: string) => document.querySelector(`[role="group"][aria-label="${label}"]`);
const rows = (label: string) => Array.from(group(label)?.querySelectorAll("button, [data-testid=workspace-hit-static]") ?? []).map((row) => row.textContent ?? "");
const paletteText = () => (document.body.textContent ?? "") + Array.from(document.querySelectorAll("input")).map((field) => field.placeholder).join(" ");

test("on focus the search is not empty: it names what it reads and offers every screen and action, with a badge each", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    assert.equal(view.input().placeholder, "Busca comercio, monto o nota");
    assert.deepEqual(rows("Ir a"), ["InicioPantalla", "BandejaPantalla", "GastosPantalla", "NegocioPantalla", "Equipo y accesosPantalla", "Correo de recibosPantalla"]);
    assert.deepEqual(rows("Acciones"), ["AgregarAcción", "Exportar registrosAcción", "Copiar dirección de reenvíoAcción"]);
    assert.ok(!/Argus/.test(paletteText()), "no Argus words on a Business search");
  } finally { await view.unmount(); }
});

test("screens and actions match the query without accents or case, and open where they live", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    await type(view.input(), "gasto");
    assert.deepEqual(rows("Ir a"), ["GastosPantalla"]);
    await type(view.input(), "EXPORTAR");
    assert.deepEqual(rows("Acciones"), ["Exportar registrosAcción"]);
    await type(view.input(), "dirección");
    assert.deepEqual(rows("Acciones"), ["Copiar dirección de reenvíoAcción"]);
    await type(view.input(), "equipo");
    assert.deepEqual(rows("Ir a"), ["Equipo y accesosPantalla"]);
    await act(async () => (group("Ir a")!.querySelector("button") as HTMLButtonElement).click());
    assert.deepEqual(view.opened, [{ kind: "business", tab: "equipo" }]);
    assert.equal(document.querySelector("input"), null, "opening a screen closes the search");
    await view.openSearch();
    await type(view.input(), "exportar");
    await act(async () => (group("Acciones")!.querySelector("button") as HTMLButtonElement).click());
    assert.equal(view.opened.at(-1), "export", "Exportar opens the one export sheet over the current screen");
    await view.openSearch();
    await type(view.input(), "correos");
    await act(async () => (group("Ir a")!.querySelector("button") as HTMLButtonElement).click());
    assert.deepEqual(view.opened.at(-1), { kind: "business", tab: "correo" }, "the email history lives in Correo de recibos");
  } finally { await view.unmount(); }
});

test("record hits carry their kind, a receipt opens beside the Bandeja, and accounts show without a way to open", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    await type(view.input(), "ferreteria");
    const receipts = rows("Recibos");
    assert.ok(receipts.length > 0 && receipts.every((row) => row.includes("Recibo")), `receipt rows: ${receipts}`);
    await key(view.input(), "ArrowDown");
    const focused = document.activeElement as HTMLElement;
    assert.ok(group("Recibos")?.contains(focused), "Down moves from the field to the first record");
    assert.ok(!focused.className.includes("outline-none") && focused.className.includes("focus-visible:outline"), "the active row shows a focus ring");
    await act(async () => focused.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 0 })));
    assert.deepEqual(view.opened, [{ kind: "receipt", receiptId: "rcpt-ferreteria", list: "inbox" }]);

    await view.openSearch();
    await type(view.input(), "operating");
    assert.deepEqual(rows("Cuentas"), ["Operating accountDOPCuenta"]);
    assert.equal(group("Cuentas")!.querySelector("button"), null);
  } finally { await view.unmount(); }
});

test("a search that led to a record comes back as a recent search, and one click fills the bar", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    await type(view.input(), "ferreteria");
    await act(async () => group("Recibos")!.querySelector("button")!.dispatchEvent(new MouseEvent("click", { bubbles: true, detail: 0 })));
    await view.openSearch();
    assert.deepEqual(rows("Búsquedas recientes"), ["ferreteria"]);
    await act(async () => (group("Búsquedas recientes")!.querySelector("button") as HTMLButtonElement).click());
    await settle();
    assert.equal(view.input().value, "ferreteria");
    assert.ok(rows("Recibos").length > 0, "the filled query searches");
  } finally { await view.unmount(); }
});

test("zero results say so, say what to search by, and still offer the screens and actions", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    await type(view.input(), "zzqx");
    const empty = document.querySelector('[data-testid="workspace-search-no-match"]');
    assert.ok(empty?.textContent?.includes("No encontramos nada con «zzqx»."));
    assert.ok(empty?.textContent?.includes("Busca por comercio, monto, categoría, cuenta o el texto de una nota."));
    assert.equal(rows("Ir a").length, 6);
    assert.ok(rows("Acciones").length >= 3);
    assert.ok(!/Argus|ticker/.test(paletteText()));
    await type(view.input(), "z");
    assert.ok(document.querySelector('[data-testid="workspace-search-no-match"]')?.textContent?.includes("Escribe al menos 3 letras"));
    assert.ok(!/Argus|ticker/.test(paletteText()));
  } finally { await view.unmount(); }
});

test("Escape closes the search and focus returns to the control that opened it", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    assert.equal(document.activeElement, view.input());
    await key(view.input(), "Escape");
    assert.equal(document.querySelector("input"), null);
    assert.equal(document.activeElement, view.opener());
  } finally { await view.unmount(); }
});

test("the search sits as a flat sheet: no blur and no dimming behind it", async () => {
  const view = await mount();
  try {
    await view.openSearch();
    const backdrop = document.querySelector<HTMLButtonElement>('button[tabindex="-1"]')!;
    assert.ok(!/blur|bg-black/.test(backdrop.className), backdrop.className);
  } finally { await view.unmount(); }
});
