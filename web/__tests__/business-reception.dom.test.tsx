import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { GrantedSpace } from "@/lib/business-api";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const previous = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
});
afterAll(async () => {
  for (const [key, value] of Object.entries(previous)) {
    if (value === undefined) delete process.env[key];
    else Object.assign(process.env, { [key]: value });
  }
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage"], capabilities: ["read", "prepare", "approve"], access_seen: true };

test("the WhatsApp row waits for the Business it names", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { default: BusinessReception } = await import("@/components/business-app/BusinessReception");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const context = (chosen: GrantedSpace | null) => ({ source, chosen, revision: 0, reload: () => undefined }) as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = (chosen: GrantedSpace | null) => act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessContext.Provider value={context(chosen)}><BusinessReception /></BusinessContext.Provider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async () => { for (let turn = 0; turn < 5; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  const connect = (name: string) => spanish.business.reception.whatsapp_connect.replace("{{business}}", name);
  try {
    await render(null);
    await settle();
    assert.ok(host.querySelector("[data-testid='business-reception']"));
    assert.equal(host.textContent?.includes(connect("")), false);
    await render(OWN);
    await settle();
    assert.equal(host.textContent?.includes(connect(OWN.name)), true);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
