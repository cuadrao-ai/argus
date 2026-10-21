import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { useBusinessKeyboardShortcuts } from "@/components/business-app/business-keyboard-shortcuts";
import type { BusinessActions } from "@/components/business-app/business-actions";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

const actions: BusinessActions = { create: [], composer: [], starterEntries: [] };

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function ShortcutList() {
  const shortcuts = useBusinessKeyboardShortcuts({ openPanel: () => {}, actions, chosen: null });
  return <ul>{shortcuts.map((shortcut) => <li key={shortcut.id} data-shortcut={shortcut.id}>{shortcut.label}</li>)}</ul>;
}

async function labels(language: "es-419" | "en"): Promise<Record<string, string>> {
  const i18n = createInstance();
  await i18n.init({ lng: language, resources: { en: { translation: english }, "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ShortcutList /></I18nextProvider>));
  const shown = Object.fromEntries([...host.querySelectorAll("[data-shortcut]")].map((item) => [item.getAttribute("data-shortcut"), item.textContent ?? ""]));
  await act(async () => root.unmount());
  host.remove();
  return shown;
}

const SHORTCUTS = ["approve", "previous", "next", "edit", "overview", "inbox", "transactions", "sidebar", "settings"];

test("the shortcut list reads its words from the catalog in Spanish and in English", async () => {
  const es = await labels("es-419");
  const en = await labels("en");
  const pick = (shown: Record<string, string>) => Object.fromEntries(SHORTCUTS.map((id) => [id, shown[id]]));
  assert.deepEqual(pick(es), {
    approve: "Aprobar",
    previous: "Recibo anterior",
    next: "Recibo siguiente",
    edit: "Editar dato",
    overview: "Ir a Inicio",
    inbox: "Ir a Bandeja",
    transactions: "Ir a Transacciones",
    sidebar: "Mostrar u ocultar barra lateral",
    settings: "Ajustes",
  });
  assert.deepEqual(pick(en), {
    approve: "Approve expense",
    previous: "Previous receipt",
    next: "Next receipt",
    edit: "Edit a detail",
    overview: "Go to Home",
    inbox: "Go to Inbox",
    transactions: "Go to Transactions",
    sidebar: "Show or hide the sidebar",
    settings: "Settings",
  });
});
