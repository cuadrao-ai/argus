import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessSetupStep } from "@/lib/business-setup-api";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => { localStorage.clear(); document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const step = (key: BusinessSetupStep["key"], done: boolean, required = true): BusinessSetupStep => ({ key, required, done });
const NEW: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", false), step("team", false, false)];
const UNDER_WAY: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", true), step("receipt_reading", false)];
const DONE: BusinessSetupStep[] = [step("created", true), step("fiscal_identity", true), step("team", false, false)];
const EVERY: BusinessSetupStep[] = [
  step("created", true), step("fiscal_identity", false), step("receiving_address", false), step("receipt_reading", false),
  step("team", false, false), step("whatsapp", false, false),
];

type Mount = { business?: string; permissions?: string[]; answer?: BusinessSetupStep[] | Error };

/** Inicio as BusinessOverviewPanel arranges it: the guide over Resumen del negocio, fed once from the server. */
async function mount({ business = "space-setup", permissions = ["read", "manage"], answer = NEW }: Mount = {}) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { HomeWork } = await import("@/components/business-app/inicio/HomeOverviewDraft");
  const { SetupGuide } = await import("@/components/business-app/inicio/SetupGuide");
  const { useBusinessSetup } = await import("@/components/business-app/inicio/useBusinessSetup");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let reads = 0;
  const opened: unknown[] = [];
  const value = {
    source: {
      mode: "live",
      setup: async () => { reads += 1; if (answer instanceof Error) throw answer; return { steps: answer }; },
      emailIntake: async () => ({ enabled: true, receiving_address: "taller@recibos.example.test" }),
      receiptReading: async () => new Promise(() => undefined),
    },
    records: { workspace: { country: "DO" }, inbox: [], notes: [], emails: [], error: false, receiptActivity: { pending_review_count: 0 } },
    receivingChannels: { email: { available: true }, whatsapp: { available: true } },
    openPanel: (panel: unknown) => { opened.push(panel); },
    reload: () => undefined,
    chosen: { space_id: business, name: "Taller Nuevo Horizonte", grant_id: "g", role: "owner", capabilities: ["read"], permissions },
    userId: "person",
    revision: 0,
    invoicing: "unavailable",
    panel: { kind: "overview" },
  } as unknown as BusinessContextValue;
  function Inicio() {
    const setup = useBusinessSetup();
    return createElement("div", { "data-testid": "home-overview" }, createElement(SetupGuide, { setup }), createElement(HomeWork));
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(createElement(I18nextProvider, { i18n }, createElement(BusinessContext.Provider, { value }, createElement(Inicio)))); });
  await act(async () => { await Promise.resolve(); });
  const guide = () => host.querySelector<HTMLElement>('[data-testid="home-setup"]');
  const click = async (selector: string) => {
    const target = document.querySelector<HTMLElement>(selector);
    assert.ok(target, `missing ${selector}`);
    await act(async () => target.click());
    await act(async () => { await Promise.resolve(); });
  };
  return { host, guide, click, opened, reads: () => reads, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

const rows = (guide: HTMLElement) => [...guide.querySelectorAll('[data-testid^="home-setup-step-"]')].map((item) => item.getAttribute("data-testid")?.replace("home-setup-step-", ""));

describe("Inicio's setup guide is Lucas's sketch, fed by the server", () => {
  test("it renders the server's steps only, in order, in the sketch's words", async () => {
    const page = await mount({ answer: UNDER_WAY });
    try {
      const guide = page.guide();
      assert.ok(guide);
      assert.deepEqual(rows(guide), ["created", "fiscal_identity", "receipt_reading"], "a step whose feature is off is not sent, so it is not shown");
      assert.match(guide.textContent ?? "", /Configura tu espacio de trabajo/);
      assert.match(guide.querySelector('[data-testid="home-setup-step-created"]')?.textContent ?? "", /Tu espacio de trabajo.*Completado/);
    } finally { await page.close(); }
  });

  test("progress is the required steps done over the required steps; an optional step is labeled and never counted", async () => {
    const page = await mount({ answer: NEW });
    try {
      const progress = page.guide()?.querySelector('[data-testid="home-setup-progress"]');
      assert.match(progress?.textContent ?? "", /1 \/ 2/);
      assert.match(progress?.textContent ?? "", /Acciones de la guía completadas: 1 de 2\./);
      assert.match(page.guide()?.querySelector('[data-testid="home-setup-step-team"]')?.textContent ?? "", /Invita a un colaborador.*Opcional/);
      assert.doesNotMatch(page.guide()?.querySelector('[data-testid="home-setup-step-fiscal_identity"]')?.textContent ?? "", /Opcional|Completado/);
    } finally { await page.close(); }
  });

  test("a brand-new Business opens it, one under way folds it, and each Business keeps its own choice", async () => {
    const fresh = await mount({ business: "space-a", answer: NEW });
    try {
      assert.equal(fresh.guide()?.dataset.collapsed, "false");
      await fresh.click('[data-testid="home-setup-toggle"]');
      assert.equal(fresh.guide()?.dataset.collapsed, "true");
      assert.match(fresh.guide()?.textContent ?? "", /Mostrar/);
    } finally { await fresh.close(); }
    const again = await mount({ business: "space-a", answer: NEW });
    try { assert.equal(again.guide()?.dataset.collapsed, "true", "the choice survives a reload"); } finally { await again.close(); }
    const other = await mount({ business: "space-b", answer: NEW });
    try { assert.equal(other.guide()?.dataset.collapsed, "false", "another Business keeps its own state"); } finally { await other.close(); }
    const underWay = await mount({ business: "space-c", answer: UNDER_WAY });
    try { assert.equal(underWay.guide()?.dataset.collapsed, "true"); } finally { await underWay.close(); }
  });

  test("when every required step is done the guide is gone, with no gap and no all-done card", async () => {
    const page = await mount({ answer: DONE });
    try {
      assert.equal(page.reads(), 1);
      assert.equal(page.host.querySelector('[data-testid^="home-setup"]'), null);
      assert.equal(page.host.querySelector('[data-testid="home-overview"]')?.firstElementChild?.tagName, "SECTION", "Resumen del negocio comes first");
      assert.doesNotMatch(page.host.textContent ?? "", /Configura tu espacio|Completado/);
    } finally { await page.close(); }
  });

  test("an unreadable answer shows no guide: progress is never guessed", async () => {
    const page = await mount({ answer: new Error("setup unavailable") });
    try { assert.equal(page.guide(), null); } finally { await page.close(); }
  });

  test("someone who may not configure the Business is never asked and sees no guide", async () => {
    const page = await mount({ permissions: ["read", "prepare"] });
    try {
      assert.equal(page.reads(), 0);
      assert.equal(page.guide(), null);
    } finally { await page.close(); }
  });

  test("each step opens in place and its action is the live place that does the work", async () => {
    const page = await mount({ answer: EVERY });
    try {
      await page.click('[data-testid="home-setup-step-created"] button');
      assert.match(page.guide()?.textContent ?? "", /Taller Nuevo Horizonte.*República Dominicana/);
      await page.click('[data-testid="home-setup-action-created"]');
      await page.click('[data-testid="home-setup-step-fiscal_identity"] button');
      await page.click('[data-testid="home-setup-action-fiscal_identity"]');
      assert.deepEqual(page.opened, [{ kind: "business", tab: "datos" }, { kind: "business", tab: "datos" }]);
      await page.click('[data-testid="home-setup-step-receiving_address"] button');
      assert.ok(page.guide()?.querySelector('[data-testid="email-address"]'), "the Business's own receiving address, as Negocio shows it");
      await page.click('[data-testid="home-setup-step-receipt_reading"] button');
      assert.ok(page.guide()?.querySelector('[data-testid="receipt-reading-inline"]'), "the live reading switch");
      assert.equal(page.guide()?.querySelector('[data-testid="email-address"]'), null, "one step is open at a time");
      await page.click('[data-testid="home-setup-step-team"] button');
      await page.click('[data-testid="home-setup-action-team"]');
      assert.ok(document.querySelector("[data-invitation-modal]"), "the live invitation form");
      await page.click('[data-testid="home-setup-step-whatsapp"] button');
      assert.match(page.guide()?.querySelector('[data-testid="home-setup-step-whatsapp"]')?.textContent ?? "", /Taller Nuevo Horizonte.*WhatsApp sin conectar.*Conectar WhatsApp/);
      await page.click('[data-testid="home-setup-action-whatsapp"]');
      assert.ok([...document.querySelectorAll('[role="dialog"]')].some((dialog) => /WhatsApp/.test(dialog.textContent ?? "")), "the live WhatsApp link, in its dossier");
    } finally { await page.close(); }
  });

  test("the old card is gone", () => {
    assert.equal(existsSync(resolve(import.meta.dir, "../components/business-app/inicio/HomeSetup.tsx")), false);
  });
});
