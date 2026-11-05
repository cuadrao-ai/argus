import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const cell = { count: 0, before_itbis_minor: 0 };
const pendingInvoice = { count: 1, before_itbis_minor: 100000 };

function liveMonth(month: string) {
  return {
    month,
    from: `${month}-01`,
    to: `${month}-28`,
    closed: false,
    reasons: [],
    currencies: [{ currency: "DOP", by_status: { invoices: { pendiente: pendingInvoice, cobrado: cell }, receipts: { pendiente: cell, pagado: cell } } }],
    missing_rnc: [],
    missing_ncf: [],
    cuentas_por_cobrar: [],
    cuentas_por_pagar: [],
  };
}

async function inicioFor(env: { NODE_ENV: string; NEXT_PUBLIC_MOCK_AUTH: string }, hold: string) {
  const original = { fetch: globalThis.fetch, windowFetch: window.fetch, env: { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH } };
  Object.assign(process.env, env);
  window.history.replaceState(null, "", `/biz?monthClose=${hold}`);
  const urls: string[] = [];
  const respond = async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    urls.push(url);
    if (url.includes("/business/month-close?")) return Response.json(liveMonth(new URL(url, "http://localhost").searchParams.get("month") ?? ""));
    if (url.includes("/business/open-items")) return Response.json({ today: "2026-10-18", cuentas_por_cobrar: [], cuentas_por_pagar: [] });
    return new Response("{}", { status: 404 });
  };
  globalThis.fetch = respond;
  window.fetch = respond;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("../components/business-app/BusinessWorkspace");
  const { default: MonthClosePanel, useMonthCloseSource } = await import("../components/business-app/BusinessMonthClosePanel");
  function Panel() {
    return <MonthClosePanel monthClose={useMonthCloseSource()} />;
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const value = { source: { mode: "live" }, chosen: { grant_id: "own-grant", capabilities: ["approve"], role: "owner", name: "Taller" }, actions: { create: [] } } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><Panel /></BusinessContext.Provider></I18nextProvider>);
  });
  for (let i = 0; i < 20; i += 1) await act(async () => { await Promise.resolve(); });
  const page = { host, urls, read: (testId: string) => host.querySelector(`[data-testid="${testId}"]`) };
  const close = async () => {
    await act(async () => root.unmount());
    host.remove();
    globalThis.fetch = original.fetch;
    window.fetch = original.windowFetch;
    window.history.replaceState(null, "", "/");
    for (const [key, saved] of Object.entries(original.env)) {
      if (saved === undefined) delete process.env[key];
      else process.env[key] = saved;
    }
  };
  return { ...page, close };
}

const production = { NODE_ENV: "production", NEXT_PUBLIC_MOCK_AUTH: "true" };
const preview = { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" };

describe("Inicio ?monthClose= review hold", () => {
  test("a production build ignores every hold and reads the live month and open items", async () => {
    for (const hold of ["loading", "empty", "error"]) {
      const page = await inicioFor(production, hold);
      try {
        assert.ok(page.urls.some((url) => url.includes("/business/month-close?")), `${hold}: the live month was read`);
        assert.ok(page.urls.some((url) => url.includes("/business/open-items")), `${hold}: the live open items were read`);
        assert.ok(page.read("month-close"), `${hold}: live Inicio is shown`);
        assert.equal(page.read("month-close-error"), null, `${hold}: no invented error`);
        assert.equal(page.read("month-close-loading"), null, `${hold}: no held loading`);
        assert.equal(page.read("month-close-empty"), null, `${hold}: no invented empty month`);
      } finally {
        await page.close();
      }
    }
  });

  test("a development build with mock auth still honors the hold", async () => {
    const loading = await inicioFor(preview, "loading");
    try {
      assert.equal(loading.urls.some((url) => url.includes("/business/month-close?")), false);
      assert.ok(loading.read("month-close-loading"));
    } finally {
      await loading.close();
    }
    const error = await inicioFor(preview, "error");
    try {
      assert.ok(error.read("month-close-error"));
    } finally {
      await error.close();
    }
    const empty = await inicioFor(preview, "empty");
    try {
      assert.equal(empty.urls.some((url) => url.includes("/business/open-items")), false);
    } finally {
      await empty.close();
    }
  });
});
