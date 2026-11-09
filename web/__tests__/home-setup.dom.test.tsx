import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessSetupStep } from "@/lib/business-setup-api";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const step = (key: BusinessSetupStep["key"], done: boolean, required = true): BusinessSetupStep => ({ key, required, done });
const NEW: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", false), step("team", false, false)];
const UNDER_WAY: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", true), step("receipt_reading", false)];
const DONE: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", true), step("team", false, false)];

/** Inicio's two setup places, fed once from the server as BusinessOverviewPanel feeds them. */
async function mount(answer: BusinessSetupStep[] | Error, permissions: string[] = ["read", "manage"]) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { HomeSetupLead, HomeWork } = await import("@/components/business-app/inicio/HomeOverviewDraft");
  const { useBusinessSetup } = await import("@/components/business-app/inicio/useBusinessSetup");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let reads = 0;
  const opened: unknown[] = [];
  const value = {
    source: { mode: "live", setup: async () => { reads += 1; if (answer instanceof Error) throw answer; return { steps: answer }; } },
    records: { inbox: [], notes: [], emails: [], error: false, receiptActivity: { pending_review_count: 0 } },
    openPanel: (panel: unknown) => { opened.push(panel); },
    reload: () => undefined,
    chosen: { space_id: "space-setup", name: "Taller Nuevo", grant_id: "g", role: "owner", capabilities: ["read"], permissions },
    userId: "person",
    revision: 0,
    invoicing: "unavailable",
    panel: { kind: "overview" },
  } as unknown as BusinessContextValue;
  function Inicio() {
    const setup = useBusinessSetup();
    return createElement("div", null, createElement(HomeSetupLead, { steps: setup }), createElement(HomeWork, { setup }));
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(createElement(I18nextProvider, { i18n }, createElement(BusinessContext.Provider, { value }, createElement(Inicio)))); });
  await act(async () => { await Promise.resolve(); });
  return { act, host, opened, reads: () => reads, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

describe("Inicio's setup guide is the server's", () => {
  test("a brand-new Business leads with its open required steps, counted from what the server sent", async () => {
    const page = await mount(NEW);
    try {
      const lead = page.host.querySelector('[data-testid="home-setup-new"]');
      assert.ok(lead);
      assert.equal(lead.querySelector('[role="img"]')?.getAttribute("aria-label"), "1 de 2 listos", "optional steps never count");
      assert.deepEqual([...lead.querySelectorAll('[data-testid^="home-setup-step-"]')].map((item) => item.getAttribute("data-testid")), ["home-setup-step-fiscal_identity"]);
      assert.equal(page.host.querySelector('[data-testid="home-setup-entry"]'), null);
      await page.act(async () => (lead.querySelector('[data-testid="home-setup-step-fiscal_identity"]') as HTMLButtonElement).click());
      assert.deepEqual(page.opened, [{ kind: "business", tab: "datos" }]);
    } finally { await page.close(); }
  });

  test("a Business under way keeps a compact entry beside the work, and only the steps the server sent", async () => {
    const page = await mount(UNDER_WAY);
    try {
      const entry = page.host.querySelector('[data-testid="home-setup-entry"]');
      assert.ok(entry);
      assert.match(entry.textContent ?? "", /Falta 1 paso/);
      assert.equal(page.host.querySelector('[data-testid="home-setup-new"]'), null);
      await page.act(async () => (entry as HTMLButtonElement).click());
      const steps = [...document.querySelectorAll('[data-testid="home-setup-panel"] [data-testid^="home-setup-step-"]')].map((item) => item.getAttribute("data-testid"));
      assert.deepEqual(steps, ["home-setup-step-created", "home-setup-step-fiscal_identity", "home-setup-step-receipt_reading"], "a step whose feature is off is not sent, so it is not shown");
      assert.match(document.querySelector('[data-testid="home-setup-step-receipt_reading"]')?.textContent ?? "", /Activar lectura de documentos/);
    } finally { await page.close(); }
  });

  test("when every required step is done the guide is gone, with no gap and no all-done card", async () => {
    const page = await mount(DONE);
    try {
      assert.equal(page.reads(), 1);
      assert.equal(page.host.querySelector('[data-testid^="home-setup"]'), null);
      assert.equal(page.host.querySelector('[data-testid="home-work"]')?.className, "", "Resumen del negocio is one column again");
      assert.doesNotMatch(page.host.textContent ?? "", /Configurar negocio|listos/);
    } finally { await page.close(); }
  });

  test("an unreadable answer shows no guide: progress is never guessed", async () => {
    const page = await mount(new Error("setup unavailable"));
    try {
      assert.equal(page.host.querySelector('[data-testid^="home-setup"]'), null);
    } finally { await page.close(); }
  });

  test("someone who may not configure the Business is never asked and sees no guide", async () => {
    const page = await mount(NEW, ["read", "prepare"]);
    try {
      assert.equal(page.reads(), 0);
      assert.equal(page.host.querySelector('[data-testid^="home-setup"]'), null);
    } finally { await page.close(); }
  });
});
