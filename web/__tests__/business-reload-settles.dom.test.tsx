import { afterAll, afterEach, beforeAll, describe, expect, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";

// The Bandeja's pull waits on the workspace refresh; it settles only when every list it asks again has answered.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("view=inbox"),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?view=inbox", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});
const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
});

const later = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function mount(change: (source: BusinessDataSource) => Partial<BusinessDataSource>) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = { ...fixture, ...change(fixture) } as BusinessDataSource;
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return null;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <BusinessConsentTestProvider accepted>
        <BusinessWorkspaceProvider source={source}><Probe /></BusinessWorkspaceProvider>
      </BusinessConsentTestProvider>
    </I18nextProvider>,
  ));
  unmounts.push(async () => { await act(async () => root.unmount()); });
  await act(async () => { await later(600); });
  return { act, api: () => api! };
}

describe("a workspace refresh", () => {
  test("settles as updated only after the slowest list it asked again has answered", async () => {
    let hold = false;
    const held: (() => void)[] = [];
    const page = await mount((fixture) => ({
      emailDeliveries: () => (hold ? new Promise((resolve) => { held.push(() => resolve(fixture.emailDeliveries())); }) : fixture.emailDeliveries()),
    }));
    hold = true;
    let outcome: string | null = null;
    await page.act(async () => { void page.api().refresh().then((value) => { outcome = value; }); });
    await page.act(async () => { await later(600); });
    expect(held.length).toBeGreaterThan(0);
    expect(outcome).toBeNull();
    await page.act(async () => { held.forEach((answer) => answer()); await later(300); });
    expect(outcome as string | null).toBe("updated");
  });

  test("settles as failed when one list could not load, and that list shows its own failure", async () => {
    let down = false;
    const page = await mount((fixture) => ({
      captures: (...args: Parameters<BusinessDataSource["captures"]>) => (down ? Promise.reject(new Error("notes down")) : fixture.captures(...args)),
    }));
    down = true;
    let outcome: string | null = null;
    await page.act(async () => { void page.api().refresh().then((value) => { outcome = value; }); });
    await page.act(async () => { await later(900); });
    expect(outcome as string | null).toBe("failed");
    expect(page.api().records.notesFailure).not.toBeNull();
  });
});
