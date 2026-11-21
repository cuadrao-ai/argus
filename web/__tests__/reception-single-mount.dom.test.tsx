import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { useEffect, useState } from "react";
import { useBusiness } from "@/components/business-app/business-context";
import type { GrantedSpace } from "@/lib/business-api";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("view=inbox"),
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/dev/business-preview",
}));

// Observe the lifecycle inside ReceptionPreview's keyed list, preserving its real
// preferences hook and every component. No StrictMode replay is enabled here.
const realColumns = { ...await import("@/components/business-app/recepcion/reception-columns") };
const mountedScopes: (string | null)[] = [];
mock.module("@/components/business-app/recepcion/reception-columns", () => ({
  ...realColumns,
  useReceptionPreferences() {
    const { chosen } = useBusiness();
    const [scope] = useState(chosen?.space_id ?? null);
    useEffect(() => { mountedScopes.push(scope); }, [scope]);
    return realColumns.useReceptionPreferences();
  },
}));

let cleanup = async () => {};
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/dev/business-preview?view=inbox", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => { await cleanup(); cleanup = async () => {}; window.localStorage.clear(); });
afterAll(async () => { await GlobalRegistrator.unregister(); });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

async function mount(paged = false) {
  mountedScopes.length = 0;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const { setChosenGrant, getChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const [workspace, overview, rows] = await Promise.all([fixture.workspace(), fixture.overview("", null), fixture.receipts("all")]);
  const spaces: GrantedSpace[] = ["a", "b"].map(id => ({
    space_id: `business-${id}`, grant_id: `grant-${id}`, name: `Business ${id}`, role: "owner", business_role: "owner",
    permissions: ["read", "prepare", "approve"], capabilities: ["read", "prepare", "approve"], access_seen: true,
  }));
  let directory = deferred<GrantedSpace[]>();
  const inbox = deferred<typeof rows>();
  const requests: (string | null)[] = [];
  const read = async (view: "inbox" | "all") => {
    if (view === "all") { requests.push(getChosenGrant()); return rows; }
    return inbox.promise;
  };
  const source = {
    ...fixture,
    ensureSpace: async () => ({ id: "business-a", name: "Business a" }),
    spaces: () => directory.promise,
    workspace: async () => workspace,
    overview: async () => overview,
    receipts: read,
    captures: async () => ({ items: [] }),
    emailDeliveries: async () => [],
    receiptActivity: undefined,
    receiptPage: paged ? async (view: "inbox" | "all") => ({ items: await read(view), activity: { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 0, ready_to_review_count: 0 }, version: "version-1" }) : undefined,
  };
  let context!: BusinessContextValue;
  const scopes: (string | null)[] = [];
  function Main() {
    context = useBusiness();
    const scope = context.chosen?.space_id ?? null;
    if (scopes.at(-1) !== scope) scopes.push(scope);
    return <BusinessPanel />;
  }
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted>
      <BusinessWorkspaceProvider source={source}><Main /></BusinessWorkspaceProvider>
    </BusinessConsentTestProvider></I18nextProvider>,
  ));
  const commit = async (action: () => void) => { await act(async () => action()); };
  return {
    scopes, requests, host,
    mounts: () => mountedScopes.length,
    settleDirectory: () => commit(() => directory.resolve(spaces)),
    settleInbox: () => commit(() => inbox.resolve(rows)),
    switchBusiness: () => commit(() => { context.chooseBusiness("grant-b"); context.openPanel({ kind: "inbox" }); }),
    reload: () => commit(() => context.reload()),
    failDirectory: () => commit(() => directory.reject(new Error("Synthetic directory outage"))),
    retryDirectory: () => commit(() => {
      directory = deferred<GrantedSpace[]>();
      [...host.querySelectorAll<HTMLButtonElement>('[data-testid="server-error-screen"] button')].find(button => button.textContent === i18n.t("auth.screen.try_again"))!.click();
    }),
  };
}

for (const paged of [false, true]) for (const directoryFirst of [false, true]) {
  test(`plain Bandeja mounts and requests all once (${paged ? "versioned page" : "unversioned fixture"}; ${directoryFirst ? "directory" : "inbox"} answers first)`, async () => {
    const page = await mount(paged);
    if (directoryFirst) { await page.settleDirectory(); await page.settleInbox(); }
    else { await page.settleInbox(); await page.settleDirectory(); }
    assert.equal(page.mounts(), 1, `scopes=${JSON.stringify(page.scopes)}; mounted=${JSON.stringify(mountedScopes)}; all requests=${page.requests.length}`);
    assert.equal(page.requests.length, 1);
    assert.ok(page.host.querySelector('[data-testid="reception-row"]'));
  });
}

test("switching Business mounts the new list once; a directory refresh keeps that mount", async () => {
  const page = await mount();
  await page.settleInbox(); await page.settleDirectory();
  const before = page.mounts();
  page.requests.length = 0;
  await page.switchBusiness();
  assert.equal(page.mounts() - before, 1);
  assert.deepEqual(page.requests, ["grant-b"]);
  assert.equal(page.scopes.at(-1), "business-b");
  await page.reload();
  assert.equal(page.mounts() - before, 1, "refreshing the directory must not unmount a settled scope");
});

test("an unresolved scope makes no list request; directory failure offers retry", async () => {
  const page = await mount();
  await page.settleInbox();
  assert.equal(page.mounts(), 0);
  assert.equal(page.requests.length, 0);
  await page.failDirectory();
  assert.equal(page.mounts(), 0);
  assert.ok(page.host.querySelector('[data-testid="server-error-screen"]'));
  await page.retryDirectory();
  await page.settleDirectory();
  assert.equal(page.mounts(), 1);
  assert.equal(page.requests.length, 1);
  assert.equal(page.host.querySelector('[data-testid="server-error-screen"]'), null);
});
