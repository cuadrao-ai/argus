import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import BusinessConsentGate from "@/components/business-app/BusinessConsentGate";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { getChosenGrant, setChosenGrant, synchronizeBusinessAccount } from "@/lib/business-grant";
import type { BusinessConsent } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

type ConsentSource = Pick<BusinessDataSource, "consent" | "acceptConsent" | "ensureSpace">;

const i18n = i18next.createInstance();
const GRANT = "44444444-4444-4444-8444-444444444444";

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
afterEach(() => { setChosenGrant(null); });

/** The server's memory of acceptances, outliving every mounted screen. */
function server() {
  const accepted = new Map<string, string>();
  const calls = { ensureSpace: 0, accept: [] as (string | null)[] };
  let failNext: unknown = null;
  let hold: Promise<void> | null = null;
  let readHold: Promise<void> | null = null;
  const held = () => {
    let release!: () => void;
    const promise = new Promise<void>((resolve) => { release = resolve; });
    return { promise, release };
  };
  const source: ConsentSource = {
    consent: async (version) => {
      await readHold;
      return { version, accepted_at: accepted.get(version) ?? null };
    },
    acceptConsent: async (version): Promise<BusinessConsent> => {
      calls.accept.push(getChosenGrant());
      await hold;
      if (failNext) {
        const error = failNext;
        failNext = null;
        throw error;
      }
      if (!accepted.has(version)) accepted.set(version, "2026-10-19T12:00:00.000Z");
      return { version, accepted_at: accepted.get(version) ?? null };
    },
    ensureSpace: async () => {
      calls.ensureSpace += 1;
      return { id: "own-space", name: "Mi negocio" };
    },
  };
  return {
    source,
    accepted,
    calls,
    failOnce: (error: unknown) => { failNext = error; },
    holdAccept: () => {
      const { promise, release } = held();
      hold = promise;
      return () => { hold = null; release(); };
    },
    holdRead: () => {
      const { promise, release } = held();
      readHold = promise;
      return () => { readHold = null; release(); };
    },
  };
}

async function settle() {
  await act(async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); await new Promise((r) => setTimeout(r, 0)); });
}

async function mount(source: ConsentSource): Promise<{ host: HTMLElement; root: Root }> {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentGate source={source}><p data-testid="inicio">Inicio</p></BusinessConsentGate>
      </I18nextProvider>,
    );
  });
  return { host, root };
}

const button = (host: HTMLElement) => host.querySelector('[data-testid="business-consent-continue"]') as HTMLButtonElement;
const checkbox = (host: HTMLElement) => host.querySelector('input[type="checkbox"]') as HTMLInputElement;

const alert = (host: HTMLElement) => host.querySelector('[data-testid="business-consent-screen"] [role="alert"]');

test("Continuar waits for the box, locks with a spinner while saving, and goes straight in", async () => {
  const world = server();
  const releaseRead = world.holdRead();
  const { host, root } = await mount(world.source);
  await settle();
  assert.ok(host.querySelector('[data-testid="business-consent-loading"] [data-layout="overview"]'), "the check paints Inicio's skeleton, not blank");
  releaseRead();
  await settle();

  const screen = host.querySelector('[data-testid="business-consent-screen"]');
  assert.ok(screen);
  assert.equal(screen.querySelector("h1")?.textContent, "Antes de empezar");
  assert.equal(screen.querySelector("h1 + p")?.textContent, spanish.business.consent.one_time);
  const privacy = host.querySelector('[data-testid="business-consent-privacy"]') as HTMLAnchorElement;
  assert.equal(privacy.getAttribute("href"), "https://cuadrao.ai/privacidad");
  assert.equal(privacy.getAttribute("target"), "_blank");
  assert.equal(privacy.textContent, "Ver aviso de privacidad");
  assert.equal(button(host).disabled, true);
  await act(async () => { checkbox(host).click(); });
  assert.equal(button(host).disabled, false);
  await act(async () => { checkbox(host).click(); });
  assert.equal(button(host).disabled, true);
  await act(async () => { checkbox(host).click(); });

  const release = world.holdAccept();
  await act(async () => { button(host).click(); });
  await settle();
  assert.ok(host.querySelector('[data-testid="business-consent-screen"]'), "the screen stays while it saves");
  assert.ok(host.querySelector('[data-testid="business-consent-saving"]'), "Continuar shows a spinner");
  assert.equal(button(host).getAttribute("aria-busy"), "true");
  assert.equal(checkbox(host).disabled, true, "the box is locked while saving");
  await act(async () => { button(host).click(); });
  await settle();
  assert.equal(world.calls.accept.length, 1, "a second press while saving sends nothing");
  assert.equal(host.querySelector('[data-testid="inicio"]'), null);
  release();
  await settle();
  assert.ok(host.querySelector('[data-testid="inicio"]'));
  assert.equal(world.calls.ensureSpace, 1, "the own Business is started before it is named");
  assert.equal(world.accepted.size, 1);
  await act(async () => root.unmount());
  host.remove();

  const again = await mount(world.source);
  await settle();
  assert.equal(again.host.querySelector('[data-testid="business-consent-screen"]'), null, "an accepted person never sees the screen again");
  assert.ok(again.host.querySelector('[data-testid="inicio"]'));
  await act(async () => again.root.unmount());
  again.host.remove();
});

test("a server failure says what failed inline, with its reference, and Reintentar saves", async () => {
  const world = server();
  world.failOnce(Object.assign(new Error("API error 503"), { status: 503, digest: "req_7f3a9c" }));
  const { host, root } = await mount(world.source);
  await settle();
  await act(async () => { checkbox(host).click(); });
  await act(async () => { button(host).click(); });
  await settle();
  const failure = alert(host);
  assert.ok(failure);
  assert.match(failure.textContent ?? "", /No pudimos guardar tu aceptación\. No cambió nada\./);
  assert.equal(failure.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), "req_7f3a9c", "the reference keeps its full id to copy");
  assert.equal(checkbox(host).checked, true, "the box stays ticked");
  assert.equal(host.querySelector('[data-testid="connection-banner"]'), null);
  assert.equal(host.querySelector('[data-testid="inicio"]'), null);
  assert.equal(world.accepted.size, 0);

  await act(async () => { (host.querySelector('[data-testid="business-consent-retry"]') as HTMLButtonElement).click(); });
  await settle();
  assert.ok(host.querySelector('[data-testid="inicio"]'), "Reintentar saves and goes straight in");
  assert.equal(world.accepted.size, 1);
  await act(async () => root.unmount());
  host.remove();
});

test("offline, the docked banner speaks and the screen claims no server failure", async () => {
  const world = server();
  const online = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(navigator), "onLine");
  const { host, root } = await mount(world.source);
  await settle();
  await act(async () => { checkbox(host).click(); });
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false });
  world.failOnce(new TypeError("Failed to fetch"));
  try {
    await act(async () => { window.dispatchEvent(new Event("offline")); });
    await act(async () => { button(host).click(); });
    await settle();
    assert.ok(host.querySelector('[data-testid="connection-banner"]'));
    assert.equal(alert(host), null);
    assert.equal(button(host).disabled, false, "Continuar is ready to try again");
    assert.equal(host.querySelector('[data-testid="inicio"]'), null);
  } finally {
    delete (navigator as { onLine?: boolean }).onLine;
    if (online) Object.defineProperty(Object.getPrototypeOf(navigator), "onLine", online);
    await act(async () => { window.dispatchEvent(new Event("online")); });
  }
  assert.equal(host.querySelector('[data-testid="connection-banner"]'), null);
  await act(async () => root.unmount());
  host.remove();
});

test("under a chosen client the acceptance names it; a dead grant falls back to the own Business", async () => {
  synchronizeBusinessAccount("accountant");
  setChosenGrant(GRANT);
  const world = server();
  world.failOnce(Object.assign(new Error("gone"), { code: "business_grant_not_live" }));
  const { host, root } = await mount(world.source);
  await settle();
  await act(async () => { checkbox(host).click(); });
  await act(async () => { button(host).click(); });
  await settle();
  assert.deepEqual(world.calls.accept, [GRANT, null]);
  assert.equal(world.calls.ensureSpace, 1, "the own Business starts only once the grant is gone");
  assert.equal(getChosenGrant(), null);
  assert.ok(host.querySelector('[data-testid="inicio"]'));
  await act(async () => root.unmount());
  host.remove();
  synchronizeBusinessAccount(null);
});
