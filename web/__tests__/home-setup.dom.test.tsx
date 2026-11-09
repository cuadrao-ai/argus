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
const UNDER_WAY: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", false), step("receipt_reading", true), step("first_document", true, false), step("team", false, false)];
const DONE: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", true), step("team", false, false)];

/** The sidebar's setup card, fed from the server once, as the rail's footer mounts it. */
async function mount(answer: BusinessSetupStep[] | Error, { permissions = ["read", "manage"], collapsed = false, role = "owner" } = {}) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { SidebarSetup } = await import("@/components/business-app/inicio/HomeSetup");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let reads = 0;
  let uploads = 0;
  let steps = answer;
  const opened: unknown[] = [];
  const source = { mode: "live", setup: async () => { reads += 1; if (steps instanceof Error) throw steps; return { steps }; } };
  const context = (revision: number) => ({
    source,
    openPanel: (panel: unknown) => { opened.push(panel); },
    actions: { create: role === "accountant" ? [] : [{ id: "upload_receipt", label: "Subir", run: () => { uploads += 1; } }] },
    chosen: { space_id: "space-setup", name: "Taller Nuevo", grant_id: "g", role, capabilities: ["read"], permissions },
    revision,
  }) as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = async (revision: number) => {
    await act(async () => { root.render(createElement(I18nextProvider, { i18n }, createElement(BusinessContext.Provider, { value: context(revision) }, createElement(SidebarSetup, { collapsed })))); });
    await act(async () => { await Promise.resolve(); });
  };
  await render(0);
  return {
    act, host, opened, reads: () => reads, uploads: () => uploads,
    /** The server answers again (a reload after a step is finished). */
    answer: async (next: BusinessSetupStep[]) => { steps = next; await render(1); },
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

const dossierSteps = () => [...document.querySelectorAll('[data-testid="home-setup-panel"] [data-testid^="home-setup-step-"]')].map((item) => item.getAttribute("data-testid")!.replace("home-setup-step-", ""));

describe("Configurar negocio lives in the sidebar, from the server's steps", () => {
  test("the card counts only required steps, names what is left, and opens the dossier highlighted", async () => {
    const page = await mount(UNDER_WAY);
    try {
      const card = page.host.querySelector('[data-testid="sidebar-setup"]') as HTMLButtonElement;
      assert.ok(card);
      assert.equal(card.getAttribute("aria-label"), "Configurar negocio, 2 de 3 pasos listos", "optional steps never count");
      assert.match(card.textContent ?? "", /2\/3/);
      assert.match(card.textContent ?? "", /Configurar negocio/);
      assert.match(card.textContent ?? "", /Falta 1 paso/);
      assert.equal(card.dataset.open, undefined);
      await page.act(async () => card.click());
      assert.equal(card.dataset.open, "true", "the card stays highlighted while its dossier is open");
      assert.ok(document.querySelector('[data-testid="home-setup-panel"]'));
    } finally { await page.close(); }
  });

  test("the dossier lists open required steps, then the optional ones, and every finished step last", async () => {
    const page = await mount(UNDER_WAY);
    try {
      await page.act(async () => (page.host.querySelector('[data-testid="sidebar-setup"]') as HTMLButtonElement).click());
      assert.deepEqual(dossierSteps(), ["fiscal_identity", "team", "created", "receipt_reading", "first_document"]);
      const panel = document.querySelector('[data-testid="home-setup-panel"]')!;
      assert.match(panel.textContent ?? "", /Opcional/);
      assert.match(panel.textContent ?? "", /Completa estos pasos para empezar a recibir y revisar documentos\./);
      assert.equal(panel.querySelector('[role="img"]')?.getAttribute("aria-label"), "Configurar negocio, 2 de 3 pasos listos");
      assert.equal(panel.querySelectorAll('[data-testid="home-setup-finished"] [data-done]').length, 3, "finished steps are muted cards with a check");
      await page.act(async () => (document.querySelector('[data-testid="home-setup-step-fiscal_identity"]') as HTMLButtonElement).click());
      assert.deepEqual(page.opened, [{ kind: "business", tab: "datos" }]);
      assert.equal(document.querySelector('[data-testid="home-setup-panel"]'), null);
    } finally { await page.close(); }
  });

  test("the first document step starts the upload Agregar already offers", async () => {
    const page = await mount([step("created", true), step("fiscal_identity", false), step("first_document", false, false)]);
    try {
      await page.act(async () => (page.host.querySelector('[data-testid="sidebar-setup"]') as HTMLButtonElement).click());
      await page.act(async () => (document.querySelector('[data-testid="home-setup-step-first_document"]') as HTMLButtonElement).click());
      assert.equal(page.uploads(), 1);
      assert.deepEqual(page.opened, []);
    } finally { await page.close(); }
  });

  test("on the closed rail the ring alone carries the name and progress", async () => {
    const page = await mount(UNDER_WAY, { collapsed: true });
    try {
      const card = page.host.querySelector('[data-testid="sidebar-setup"]')!;
      assert.equal(card.getAttribute("aria-label"), "Configurar negocio, 2 de 3 pasos listos");
      assert.doesNotMatch(card.textContent ?? "", /Configurar negocio|Falta/);
    } finally { await page.close(); }
  });

  test("the card leaves when the last required step is done, with no all-done card", async () => {
    const page = await mount(UNDER_WAY);
    try {
      assert.ok(page.host.querySelector('[data-testid="sidebar-setup"]'));
      await page.answer(DONE);
      assert.equal(page.reads(), 2);
      assert.equal(page.host.innerHTML, "");
    } finally { await page.close(); }
  });

  test("an unreadable answer shows no card: progress is never guessed", async () => {
    const page = await mount(new Error("setup unavailable"));
    try {
      assert.equal(page.host.innerHTML, "");
    } finally { await page.close(); }
  });

  test("someone who may not manage the Business is never asked and sees no card", async () => {
    const page = await mount(UNDER_WAY, { permissions: ["read", "prepare"] });
    try {
      assert.equal(page.reads(), 0);
      assert.equal(page.host.innerHTML, "");
    } finally { await page.close(); }
  });
});
