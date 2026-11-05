import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ComponentType } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import BusinessAccessPanel from "@/components/business-app/BusinessAccessPanel";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { liveBusinessDataSource } from "@/components/business-app/business-data";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { setChosenGrant } from "@/lib/business-grant";
import spanish from "@/public/locales/es-419/common.json";

const original = { fetch: globalThis.fetch, auth: process.env.NEXT_PUBLIC_MOCK_AUTH };
const held = new Map<string, (response: Response) => void>();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  setChosenGrant(null);
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const path = new URL(String(input)).pathname.replace(/^.*\/api\/v1/, "");
    return new Promise<Response>((resolve) => held.set(path, resolve));
  }) as typeof fetch;
});
afterAll(async () => {
  globalThis.fetch = original.fetch;
  if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth;
  await GlobalRegistrator.unregister();
});

const fixture = createFixtureBusinessDataSource();
const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });

type Screen = {
  name: string;
  Panel: ComponentType;
  path: string;
  layout: string;
  title: string;
  errorTitle: string;
  errorTestId: string;
  loaded: () => Promise<unknown>;
  rows: string;
  empty?: { body: unknown; kind: string; title: string };
};

const screens: Screen[] = [
  {
    name: "Acceso",
    Panel: BusinessAccessPanel,
    path: "/business/access",
    layout: "access",
    title: spanish.business_access.title,
    errorTitle: spanish.business.empty.access_error,
    errorTestId: "business-access-error",
    loaded: () => fixture.access(),
    rows: "[data-testid=business-access-grants] > li",
  },
];

async function mount(Panel: ComponentType) {
  held.clear();
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let context = {
    source: liveBusinessDataSource,
    chosen: null,
    revision: 0,
    period: { key: "custom", from: "2026-10-01", to: "2026-10-17" },
    setPeriod: () => undefined,
    records: { workspace: null, overview: null, error: false },
    panel: { kind: "overview" },
    openPanel: () => undefined,
    actions: { create: [] },
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = async (patch: Partial<BusinessContextValue> = {}) => {
    context = { ...context, ...patch };
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Panel /></BusinessContext.Provider></I18nextProvider>));
  };
  await render();
  const skeleton = () => host.querySelector("[data-testid=business-loading]");
  const answer = async (path: string, response: Response) => {
    const resolve = held.get(path);
    assert.ok(resolve, `${path} was requested`);
    held.delete(path);
    await act(async () => { resolve(response); });
    for (let tries = 0; skeleton() && tries < 40; tries += 1) await wait(25);
  };
  return { host, render, answer, skeleton, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

for (const screen of screens) {
  describe(`${screen.name} first load`, () => {
    test("shows its own row skeleton under the heading, never a blank page or a spinner", async () => {
      const view = await mount(screen.Panel);
      try {
        await wait(SKELETON_DELAY_MS + 20);
        assert.equal(view.host.querySelector("h1, h2")?.textContent, screen.title);
        const skeleton = view.skeleton();
        assert.ok(skeleton, "the skeleton is on screen while the list is pending");
        assert.equal(skeleton.getAttribute("data-layout"), screen.layout);
        assert.equal(skeleton.getAttribute("role"), "status");
        assert.equal(skeleton.querySelector("[aria-hidden=true] > div")?.children.length, 3);
        assert.equal(view.host.querySelector(".animate-spin, [class*=lucide-loader]"), null);
      } finally { await view.close(); }
    });

    test("swaps the skeleton for the loaded rows", async () => {
      const view = await mount(screen.Panel);
      try {
        await wait(SKELETON_DELAY_MS + 20);
        await view.answer(screen.path, Response.json(await screen.loaded()));
        assert.equal(view.skeleton(), null);
        assert.ok(view.host.querySelectorAll(screen.rows).length > 0);
      } finally { await view.close(); }
    });

    if (screen.empty) {
      const empty = screen.empty;
      test("swaps the skeleton for the empty state", async () => {
        const view = await mount(screen.Panel);
        try {
          await wait(SKELETON_DELAY_MS + 20);
          await view.answer(screen.path, Response.json(empty.body));
          assert.equal(view.skeleton(), null);
          const state = view.host.querySelector(`[data-empty-kind=${empty.kind}]`);
          assert.ok(state, `the ${empty.kind} empty state replaces the skeleton`);
          assert.equal(state.querySelector("h3")?.textContent, empty.title);
        } finally { await view.close(); }
      });
    }

    test("swaps the skeleton for the error state", async () => {
      const view = await mount(screen.Panel);
      try {
        await wait(SKELETON_DELAY_MS + 20);
        await view.answer(screen.path, Response.json({ detail: "boom" }, { status: 500 }));
        assert.equal(view.skeleton(), null);
        const error = view.host.querySelector(`[data-testid=${screen.errorTestId}]`);
        assert.ok(error, "the error state replaces the skeleton");
        assert.equal(error.getAttribute("role"), "alert");
        assert.equal(error.getAttribute("data-empty-kind"), "error");
        assert.equal(error.querySelector("h3")?.textContent, screen.errorTitle);
        assert.deepEqual([...error.querySelectorAll("button")].map((button) => button.textContent?.trim()), ["Reintentar"]);
      } finally { await view.close(); }
    });

    test("a background reload keeps the loaded rows instead of the skeleton", async () => {
      const view = await mount(screen.Panel);
      try {
        await view.answer(screen.path, Response.json(await screen.loaded()));
        const count = view.host.querySelectorAll(screen.rows).length;
        await view.render({ revision: 1 });
        await wait(SKELETON_DELAY_MS + 20);
        assert.equal(view.skeleton(), null);
        assert.equal(view.host.querySelectorAll(screen.rows).length, count);
      } finally { await view.close(); }
    });
  });
}
