import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessWorkspaceInfo } from "@/lib/business-api";

let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const original = { node: process.env.NODE_ENV, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/biz");
  if (original.node === undefined) Reflect.deleteProperty(process.env, "NODE_ENV"); else Reflect.set(process.env, "NODE_ENV", original.node);
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Source = ReturnType<typeof import("@/components/business-app/fixture-data").createFixtureBusinessDataSource>;

/**
 * Mounts the real provider over the fixture source, with the server's workspace answer under this test's control,
 * and the desktop top bar the shell would draw from `headerSearch`.
 */
async function mount(answer: { available: boolean } | "hold", url = "/biz", overrides: Partial<Source> = {}) {
  search = url.includes("?") ? url.slice(url.indexOf("?")) : "";
  window.history.replaceState(null, "", url);
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { default: BusinessReception } = await import("@/components/business-app/BusinessReception");
  const { useForwardAddress } = await import("@/components/business-app/useForwardAddress");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  Reflect.set(process.env, "NODE_ENV", "development");
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  let release: ((workspace: BusinessWorkspaceInfo) => void) | null = null;
  const source = {
    ...fixture,
    workspace: async (): Promise<BusinessWorkspaceInfo> => {
      const workspace = await fixture.workspace();
      if (answer === "hold") return new Promise((resolve) => { release = resolve; });
      return { ...workspace, receiving_channels: { email: { available: answer.available }, whatsapp: { available: answer.available } } };
    },
    ...overrides,
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    const address = useForwardAddress();
    return <p data-testid="forward-address">{address}</p>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never} userId="user-1">
            <Probe />
            <BusinessReception />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 40 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(done(), "the provider never settled");
  };
  // A held workspace answer holds the whole first load, so that case waits on the directory alone; a failed read settles on its error.
  await settle(() => api !== null && (answer === "hold" ? api.spaces !== null : api.records.inbox !== null || api.records.error));
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const navItems = () => [...host.querySelectorAll('[data-testid="business-sidebar-nav"] button')].map((node) => node.textContent?.trim() ?? "");
  const text = () => host.textContent ?? "";
  const heading = () => host.querySelector('[data-testid="top-bar"] h1')?.textContent?.trim() ?? null;
  return {
    act, host, settle, navItems, text, heading,
    api: () => api!,
    // Waits for the read in flight to hold before answering it, so a reload's fresh read is the one released.
    release: async (workspace: Partial<BusinessWorkspaceInfo>) => {
      await settle(() => release !== null);
      const answer = release!;
      release = null;
      await act(async () => { answer({ ...(await fixture.workspace()), ...workspace }); });
    },
  };
}


test("off and unanswered channels make no address or delivery request and expose no email offer", async () => {
  for (const answer of [{ available: false }, "hold"] as const) {
    let addressRequests = 0;
    let deliveryRequests = 0;
    const page = await mount(answer, "/biz", {
      emailIntake: async () => { addressRequests += 1; return { enabled: true, receiving_address: "inbox@cuadrao.example" }; },
      emailDeliveries: async () => { deliveryRequests += 1; return []; },
    });
    assert.equal(addressRequests, 0);
    assert.equal(deliveryRequests, 0);
    assert.equal(page.host.querySelector('[data-testid="email-address"]'), null);
    assert.ok(!page.text().includes("Remitentes"));
    assert.equal(page.host.querySelector('[data-testid="forward-address"]')?.textContent, "");
  }
});

test("available email without an address offers setup, independently of address activation", async () => {
  const page = await mount({ available: true }, "/biz", {
    emailIntake: async () => ({ enabled: false, receiving_address: null }),
    emailDeliveries: async () => [],
  });
  await page.settle(() => page.text().includes("Obtener una dirección"));
  assert.ok(page.text().includes("Remitentes"));
});

test("a Business switch drops channel capabilities and the old forwarding address before the next workspace answer", async () => {
  let addressRequests = 0;
  let deliveryRequests = 0;
  const page = await mount("hold", "/biz", {
    emailIntake: async () => { addressRequests += 1; return { enabled: true, receiving_address: "inbox@cuadrao.example" }; },
    emailDeliveries: async () => { deliveryRequests += 1; return []; },
  });
  await page.release({ receiving_channels: { email: { available: true }, whatsapp: { available: true } } } as Partial<BusinessWorkspaceInfo>);
  await page.settle(() => page.host.querySelector('[data-testid="forward-address"]')?.textContent === "inbox@cuadrao.example");
  const before = { addressRequests, deliveryRequests };
  const other = page.api().spaces?.find(space => space.grant_id !== page.api().chosen?.grant_id);
  assert.ok(other, "the fixture offers another Business");
  await page.act(async () => page.api().chooseBusiness(other!.grant_id));
  assert.equal(page.host.querySelector('[data-testid="forward-address"]')?.textContent, "");
  assert.equal(page.host.querySelector('[data-testid="email-address"]'), null);
  assert.equal(addressRequests, before.addressRequests);
  assert.equal(deliveryRequests, before.deliveryRequests);
});
