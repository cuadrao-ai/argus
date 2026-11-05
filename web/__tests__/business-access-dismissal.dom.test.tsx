import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace } from "@/lib/business-api";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push() {}, replace() {} }), usePathname: () => "/biz" }));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
function deferred() { let resolve!: () => void; const promise = new Promise<void>((done) => { resolve = done; }); return { promise, resolve }; }
async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const seen = new Map<string, Set<string>>();
  let hold: ReturnType<typeof deferred> | null = null;
  let listHold: ReturnType<typeof deferred> | null = null;
  let fail = false;
  let api!: BusinessContextValue;
  const fixture = createFixtureBusinessDataSource();
  const sourceFor = (owner: string) => ({
    ...fixture,
    spaces: async () => {
      const result: GrantedSpace[] = ["one", "two"].map((business) => ({ space_id: business, name: business, grant_id: `${owner}-${business}`, role: "accountant", capabilities: ["read", "prepare"], access_seen: seen.get(owner)?.has(business) ?? false }));
      const wait = listHold; listHold = null; if (wait) await wait.promise;
      return result;
    },
    markAccessSeen: async (grant: string) => {
      const wait = hold; hold = null; if (wait) await wait.promise;
      if (fail) throw new Error("synthetic failure");
      const business = grant.slice(owner.length + 1);
      const items = seen.get(owner) ?? new Set<string>(); items.add(business); seen.set(owner, items);
    },
  });
  const sources = { a: sourceFor("a"), b: sourceFor("b") };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  function Probe() { api = useBusiness(); return <BusinessContextCue />; }
  let generation = 0;
  const render = async (owner: "a" | "b", business = "one") => {
    await act(async () => { setChosenGrant(`${owner}-${business}`); root.render(<I18nextProvider i18n={i18n}><BusinessWorkspaceProvider key={`${owner}-${generation++}`} source={sources[owner]}><Probe /></BusinessWorkspaceProvider></I18nextProvider>); });
  };
  const settle = () => act(async () => { await new Promise((done) => setTimeout(done, 250)); });
  const banner = () => host.querySelector('[data-testid="business-access-line"]');
  const dismiss = () => act(async () => { (banner()?.querySelector("button") as HTMLButtonElement).click(); });
  const close = async () => { await act(async () => root.unmount()); host.remove(); setChosenGrant(null); };
  await render("a"); await settle();
  return { act, render, settle, banner, dismiss, close, api: () => api, seen, delay: () => (hold = deferred()), delayList: () => (listHold = deferred()), fail: () => { fail = true; } };
}
test("dismissal survives remount and remains separate for each account and Business", async () => {
  const page = await mount();
  try {
    assert.ok(page.banner()); await page.dismiss(); assert.equal(page.banner(), null);
    await page.render("a"); await page.settle(); assert.equal(page.banner(), null);
    await page.render("a", "two"); await page.settle(); assert.ok(page.banner());
    await page.render("b"); await page.settle(); assert.ok(page.banner());
    await page.render("a"); await page.settle(); assert.equal(page.banner(), null);
  } finally { await page.close(); }
});
test("a listing started before dismissal cannot restore the dismissed banner", async () => {
  const page = await mount();
  try {
    const hold = page.delayList(); await page.act(async () => page.api().reload());
    await page.dismiss(); assert.equal(page.banner(), null);
    await page.act(async () => hold.resolve()); await page.settle();
    assert.equal(page.banner(), null);
  } finally { await page.close(); }
});
test("a failed acknowledgement does not claim persisted dismissal", async () => {
  const page = await mount();
  try { page.fail(); await page.dismiss(); assert.ok(page.banner()); await page.render("a"); await page.settle(); assert.ok(page.banner()); }
  finally { await page.close(); }
});
