import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { GrantedSpace, ReceiptReading } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const PHRASE = "Nada aquí es un gasto hasta que lo confirmes.";

const reading = (enabled: boolean): ReceiptReading => ({
  scope_version: 1,
  enabled,
  available: true,
  can_change: true,
  disclosure: "Permiso de prueba",
  disclosure_token: "a".repeat(64),
  route: null,
  consented_at: null,
  revoked_at: null,
});

async function mountInbox(overrides: Partial<BusinessDataSource> = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: false }), ...overrides };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as BusinessDataSource}>
            <BusinessInboxPanel />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 40; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
      if (done()) return;
    }
    assert.fail("the inbox did not settle");
  };
  const close = () => act(async () => { root.unmount(); host.remove(); });
  return { act, host, settle, close };
}

function ownText(element: Element) {
  return [...element.childNodes].filter((node) => node.nodeType === 3).map((node) => node.textContent ?? "").join("");
}

test("a turned-on reading stays off the first screen, and a turned-off reading still explains how to turn it on", async () => {
  const on = await mountInbox({ receiptReading: async () => reading(true) });
  try {
    await on.settle(() => on.host.querySelector('[data-testid="business-inbox-receipts"]') !== null);
    assert.equal(on.host.querySelector('[data-testid="receipt-reading-control"]'), null);
    assert.equal(on.host.textContent?.includes("La lectura de recibos está activada."), false);
  } finally { await on.close(); }

  const off = await mountInbox({ receiptReading: async () => reading(false) });
  try {
    await off.settle(() => off.host.querySelector('[data-testid="receipt-reading-control"]') !== null);
    assert.equal(off.host.querySelector('[data-testid="receipt-reading-control"]')?.textContent?.includes("Activar lectura de recibos"), true);
  } finally { await off.close(); }
});

test("Bandeja shows no subhead and no Agregar of its own on a desktop, and its email waits behind the Correos segment", async () => {
  const page = await mountInbox();
  try {
    await page.settle(() => page.host.querySelector('[data-testid="business-inbox-receipts"]') !== null);
    assert.equal([...page.host.querySelectorAll("p")].some((node) => ownText(node).includes(PHRASE)), false, "the counts live on the segments, not in a subhead");
    const segments = [...page.host.querySelectorAll<HTMLButtonElement>('[data-testid="bandeja-segments"] [data-segment]')];
    assert.deepEqual(segments.map((segment) => segment.dataset.segment), ["review", "problem", "all", "emails"]);
    assert.equal(segments[3].textContent, "Correos");
    assert.equal(page.host.querySelector('[data-testid="bandeja-emails-line"]'), null, "no Ver correos line under the receipts");
    assert.equal(document.querySelector('[data-testid="email-address"]'), null, "the receiving address waits behind Correos");
    assert.equal(page.host.querySelector('[data-testid="business-primary-upload"]'), null, "Agregar lives in the top bar");
    assert.equal(page.host.querySelector('[data-testid="add-menu-page"]'), null);
    await page.act(async () => { segments[3].click(); });
    await page.settle(() => page.host.querySelector('[data-testid="email-address"]') !== null);
    assert.ok(page.host.querySelector('[data-testid="email-address"]'), "Correos shows the receiving address");
    assert.equal(page.host.querySelector('[data-testid="business-inbox-receipts"]'), null, "Correos replaces the receipt rows");
  } finally { await page.close(); }
});

test("Entendido hides the access line after a reload, and only for that person and business", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const seen = new Map<string, Set<string>>();
  const fixture = createFixtureBusinessDataSource();
  const sourceFor = (owner: string) => ({
    ...fixture,
    spaces: async () => ["one", "two"].map((business): GrantedSpace => ({
      space_id: business,
      name: business === "one" ? "Colmado Peña" : "Taller Brito",
      grant_id: `${owner}-${business}`,
      role: "accountant",
      capabilities: ["read", "prepare"],
      access_seen: seen.get(owner)?.has(business) ?? false,
    })),
    markAccessSeen: async (grant: string) => {
      const business = grant.slice(owner.length + 1);
      const items = seen.get(owner) ?? new Set<string>();
      items.add(business);
      seen.set(owner, items);
    },
  });
  const sources = { a: sourceFor("a"), b: sourceFor("b") };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let generation = 0;
  const render = async (owner: "a" | "b", business = "one") => {
    setChosenGrant(`${owner}-${business}`);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <BusinessWorkspaceProvider key={`${owner}-${business}-${generation++}`} source={sources[owner] as BusinessDataSource}>
            <BusinessContextCue />
          </BusinessWorkspaceProvider>
        </I18nextProvider>,
      );
    });
    await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
  };
  const banner = () => host.querySelector('[data-testid="business-access-line"]');
  try {
    await render("a");
    assert.equal(banner()?.textContent?.includes("Ahora tienes acceso a Colmado Peña"), true);
    assert.equal(banner()?.querySelector("button")?.textContent, "Entendido");
    await act(async () => { banner()?.querySelector("button")?.click(); });
    await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
    assert.equal(banner(), null);
    await render("a", "one");
    assert.equal(banner(), null);
    await render("a", "two");
    assert.equal(banner()?.textContent?.includes("Ahora tienes acceso a Taller Brito"), true);
    await render("b", "one");
    assert.equal(banner()?.textContent?.includes("Ahora tienes acceso a Colmado Peña"), true);
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
    setChosenGrant(null);
  }
});

test("a failed Entendido leaves the access line up", async () => {
  const page = await mountCueThatFails();
  try {
    assert.equal(page.banner()?.textContent?.includes("Entendido"), true);
    await page.act(async () => { page.banner()?.querySelector("button")?.click(); });
    await page.act(async () => { await new Promise((done) => setTimeout(done, 50)); });
    assert.ok(page.banner());
  } finally { await page.close(); }
});

async function mountCueThatFails() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const fixture = createFixtureBusinessDataSource();
  const source = {
    ...fixture,
    spaces: async () => [{ space_id: "one", name: "Colmado Peña", grant_id: "a-one", role: "accountant" as const, capabilities: ["read" as const, "prepare" as const], access_seen: false }],
    markAccessSeen: async () => { throw new Error("synthetic failure"); },
  };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  setChosenGrant("a-one");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const view: ReactNode = (
    <I18nextProvider i18n={i18n}>
      <BusinessWorkspaceProvider source={source as BusinessDataSource}>
        <BusinessContextCue />
      </BusinessWorkspaceProvider>
    </I18nextProvider>
  );
  await act(async () => { root.render(view); });
  await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
  return {
    act,
    banner: () => host.querySelector('[data-testid="business-access-line"]'),
    close: async () => { await act(async () => { root.unmount(); }); host.remove(); setChosenGrant(null); },
  };
}
