import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace, ReceiptSummary } from "@/lib/business-api";

// A real DOM, the real workspace provider and the real account boundary side
// by side: switching the chosen Business is a change of scope inside one
// signed-in account, never a sign-out. The boundary must not notice twelve
// switches in a row; the open record, its address and the dialogs close; the
// typed composer draft stays.
const search = "receipt=rcpt-ferreteria";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));
type AuthListener = (event: string, session: { user: { id: string } } | null) => void;
let listener: AuthListener | null = null;
mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      onAuthStateChange: (next: AuthListener) => {
        listener = next;
        return { data: { subscription: { unsubscribe: () => { listener = null; } } } };
      },
      getSession: async () => ({ data: { session: { user: { id: "user-1" } } }, error: null }),
    },
  }),
}));

beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  GlobalRegistrator.register({ url: "http://localhost/biz?receipt=rcpt-ferreteria" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const A: GrantedSpace = { space_id: "s-a", name: "Colmado Peña", grant_id: "g-a", role: "accountant", capabilities: ["read", "prepare"], access_seen: true };
const B: GrantedSpace = { space_id: "s-b", name: "Taller Brito", grant_id: "g-b", role: "accountant", capabilities: ["read", "prepare"], access_seen: true };

async function mount(listed: GrantedSpace[] = [OWN, A, B]) {
  const React = await import("react");
  const { act, useState } = React;
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { useMonthCloseSource } = await import("@/components/business-app/BusinessMonthClosePanel");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatAccountBoundary } = await import("@/components/chat/useChatAccountBoundary");
  const { getChosenGrant, setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  // The fixture source, with the server's listing of three Businesses and a receipt list that names the grant it was read under.
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const reads: (string | null)[] = [];
  const source = {
    ...fixture,
    spaces: async () => listed,
    // Read the list through receipts so each read names the grant it ran under.
    receiptPage: undefined,
    receipts: async (view: "inbox" | "all") => {
      reads.push(getChosenGrant());
      const grant = getChosenGrant();
      const items = await fixture.receipts(view);
      return items.map((item) => ({ ...item, merchant: `${item.merchant ?? "Recibo"} · ${grant ?? "own"}` })) as ReceiptSummary[];
    },
  };
  let boundaryState: { expired: boolean } = { expired: false };
  let api: ReturnType<typeof useBusiness> | null = null;
  let cleared = 0;
  let monthClose: ReturnType<typeof useMonthCloseSource> | null = null;
  function Probe() {
    api = useBusiness();
    monthClose = useMonthCloseSource();
    const [typed, setTyped] = useState("");
    return (
      <div>
        <p data-testid="probe-panel">{api.panel.kind}</p>
        <p data-testid="probe-chosen">{api.chosen?.name ?? "none"}</p>
        <p data-testid="probe-inbox">{api.records.inbox ? api.records.inbox.map((r) => r.merchant).join("|") : "blank"}</p>
        <input data-testid="probe-input" value={typed} onChange={(event) => setTyped(event.target.value)} />
      </div>
    );
  }
  function Harness() {
    const boundary = useChatAccountBoundary("user-1", { synchronizeAccountScope: () => true } as never, () => { cleared += 1; });
    boundaryState = boundary;
    return (
      <I18nextProvider i18n={i18n}>
        {boundary.expired ? <p role="alert" data-testid="account-changed">Tu cuenta cambió</p> : null}
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Harness />); });
  // The fixture answers after a short simulated delay: wait on real time until the lists are back.
  const settle = async () => {
    for (let i = 0; i < 40; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (host.querySelector('[data-testid="probe-inbox"]')?.textContent !== "blank") return;
    }
  };
  await settle();
  const text = (id: string) => host.querySelector(`[data-testid="${id}"]`)?.textContent ?? null;
  return { act, root, host, settle, text, reads, api: () => api!, monthClose: () => monthClose!, boundary: () => boundaryState, cleared: () => cleared, fire: (session: { user: { id: string } } | null) => act(async () => { listener?.(session ? "SIGNED_IN" : "SIGNED_OUT", session); }) };
}

describe("switching Business inside one signed-in account", () => {
  test("preview names belong to every directory entry and remain correct after switching", async () => {
    const nodeEnv = process.env.NODE_ENV;
    const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
    localStorage.setItem("cuadrao-preview-business-names-v1", JSON.stringify({ "s-own": "La Palma", "s-a": "Colmado Nuevo" }));
    const page = await mount();
    try {
      assert.deepEqual(page.api().spaces?.map(space => space.name), ["La Palma", "Colmado Nuevo", "Taller Brito"]);
      assert.equal(page.api().chosen, page.api().spaces?.[0]);
      await page.act(async () => page.api().chooseBusiness(A.grant_id));
      assert.equal(page.api().chosen?.name, "Colmado Nuevo");
      assert.equal(page.api().spaces?.[0].name, "La Palma");
      assert.equal(OWN.name, "Ferretería Luna", "source directory is not mutated");
    } finally {
      await page.act(async () => page.root.unmount());
      localStorage.removeItem("cuadrao-preview-business-names-v1");
      Object.assign(process.env, { NODE_ENV: nodeEnv, NEXT_PUBLIC_MOCK_AUTH: mockAuth });
    }
  });

  test("twelve switches between A, B and the own Business with typed text never show the account-changed screen; the record, its address and the lists are cleared on each switch", async () => {
    const page = await mount();
    assert.equal(page.text("probe-panel"), "receipt", "landed on a receipt from the address");
    assert.equal(page.text("probe-chosen"), "Ferretería Luna");
    const input = page.host.querySelector('[data-testid="probe-input"]') as HTMLInputElement;
    await page.act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Pagué 850 en pintura");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(input.value, "Pagué 850 en pintura");
    const order = [A, B, null, B, A, null, A, B, null, A, B, null];
    for (const [index, target] of order.entries()) {
      const before = page.reads.length;
      await page.act(async () => { page.api().chooseBusiness(target?.grant_id ?? null); });
      // The moment of the switch: nothing of the old Business is on the page.
      assert.equal(page.text("probe-panel"), "overview", `switch ${index}: the open record closed`);
      assert.equal(page.text("probe-inbox"), "blank", `switch ${index}: the lists are blank while the new Business loads`);
      assert.ok(!/receipt=|expense=|draft=/.test(window.location.search), `switch ${index}: ${window.location.search}`);
      await page.settle();
      assert.equal(page.text("probe-chosen"), target?.name ?? "Ferretería Luna", `switch ${index}`);
      assert.ok(page.reads.length > before, `switch ${index}: the new Business was read`);
      assert.ok(page.text("probe-inbox")?.endsWith(`· ${target?.grant_id ?? "own"}`), `switch ${index}: the rows are the new Business's: ${page.text("probe-inbox")}`);
      assert.equal(page.host.querySelector('[data-testid="account-changed"]'), null, `switch ${index}: no account-changed screen`);
      assert.equal(page.boundary().expired, false);
      assert.equal(page.cleared(), 0);
      // Typed text in a form that stays mounted is kept: the switch is not a navigation.
      assert.equal((page.host.querySelector('[data-testid="probe-input"]') as HTMLInputElement).value, "Pagué 850 en pintura");
    }
    // The boundary still works for what it is for: a stranger's session ends the view.
    await page.fire({ user: { id: "user-2" } });
    assert.equal(page.boundary().expired, true);
    assert.equal(page.cleared(), 1);
    await page.act(async () => page.root.unmount());
  });

  test("one client grant is entered without a second Business to switch to", async () => {
    const page = await mount([A]);
    for (let i = 0; i < 40 && page.text("probe-chosen") !== "Colmado Peña"; i += 1) {
      await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    }
    const { getChosenGrant, chosenGrantHeader, GRANT_HEADER } = await import("@/lib/business-grant");
    assert.equal(getChosenGrant(), "g-a");
    assert.equal(page.text("probe-chosen"), "Colmado Peña");
    assert.deepEqual(chosenGrantHeader(), { [GRANT_HEADER]: "g-a" });
    await page.act(async () => { page.api().openPanel({ kind: "overview" }); });
    await page.settle();
    assert.ok(page.text("probe-inbox")?.includes("g-a"), page.text("probe-inbox") ?? "");
    await page.act(async () => page.root.unmount());
  });

  test("choosing the Business already chosen changes nothing: no reload, the open record stays", async () => {
    const page = await mount();
    const reads = page.reads.length;
    await page.act(async () => { page.api().chooseBusiness(null); });
    await page.settle();
    assert.equal(page.text("probe-panel"), "receipt");
    assert.equal(page.reads.length, reads);
    await page.act(async () => page.root.unmount());
  });
});

test("a newly created local owner business stays selected with empty scoped records",async()=>{
 const nodeEnv=process.env.NODE_ENV,mockAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
 Object.assign(process.env,{NODE_ENV:"development",NEXT_PUBLIC_MOCK_AUTH:"true"});
 const {createLocalBusiness,LOCAL_BUSINESS_KEY,LOCAL_BUSINESS_EVENT}=await import("@/app/design-workspace/localBusinessPreview");
 const page=await mount();
 const business=createLocalBusiness(localStorage,"Taller Vacío","CA",{kind:"default"},"local-business-empty-test");
 try{await page.act(async()=>{window.dispatchEvent(new Event(LOCAL_BUSINESS_EVENT));page.api().chooseBusiness(business.id);});assert.equal(page.api().chosen?.space_id,business.id);await page.settle();assert.equal(page.api().chosen?.space_id,business.id);assert.equal(page.api().chosen?.role,"owner");assert.equal(page.api().records.workspace?.country,"CA");assert.deepEqual(page.api().records.inbox,[]);assert.deepEqual(await page.api().source.access(),{grants:[],invites:[]});assert.equal(page.api().spaces?.find(space=>space.space_id===business.id)?.name,"Taller Vacío");assert.equal(page.api().source.mode,"fixture");assert.equal(page.api().records.error,false);assert.ok(page.api().spaces?.some(space=>space.space_id===OWN.space_id));await page.act(async()=>page.api().chooseBusiness(null));await page.settle();assert.equal(page.api().chosen?.space_id,OWN.space_id);}
 finally{await page.act(async()=>page.root.unmount());localStorage.removeItem(LOCAL_BUSINESS_KEY);localStorage.removeItem("cuadrao-identity-v1:business:local-business-empty-test");Object.assign(process.env,{NODE_ENV:nodeEnv,NEXT_PUBLIC_MOCK_AUTH:mockAuth});}
});


test("local selection survives a preview reload without sending a synthetic grant header", async () => {
  const nodeEnv = process.env.NODE_ENV;
  const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const { synchronizeBusinessAccount, setChosenGrant, getChosenGrant, chosenGrantHeader } = await import("@/lib/business-grant");
  const key = "argus:business-grant:v1";
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    synchronizeBusinessAccount("local-owner");
    setChosenGrant("local-business-persisted");
    const saved = localStorage.getItem(key)!;
    assert.deepEqual(chosenGrantHeader(), {});
    synchronizeBusinessAccount(null);
    localStorage.setItem(key, saved);
    synchronizeBusinessAccount("local-owner");
    assert.equal(getChosenGrant(), "local-business-persisted");
    synchronizeBusinessAccount(null);
    Object.assign(process.env, { NODE_ENV: "production" });
    localStorage.setItem(key, saved);
    synchronizeBusinessAccount("local-owner");
    assert.equal(getChosenGrant(), null);
  } finally {
    setChosenGrant(null);
    synchronizeBusinessAccount(null);
    Object.assign(process.env, { NODE_ENV: nodeEnv, NEXT_PUBLIC_MOCK_AUTH: mockAuth });
  }
});


test("preview settlement survives switching businesses without leaking to another business", async () => {
  const previousEnv = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  const { currentMonthKey } = await import("@/lib/business-month-close");
  const page = await mount();
  const month = currentMonthKey();
  try {
    await page.act(async () => page.api().chooseBusiness(A.grant_id));
    await page.settle();
    const selected = page.monthClose();
    const original = await selected.client.load(month, selected.scopeKey!);
    const pending = original.documents.find(item => item.kind === "receipt" && item.status === "pendiente")!;
    assert.ok(pending);
    await selected.client.markPagado(pending.id, selected.scopeKey!);
    await page.act(async () => page.api().chooseBusiness(B.grant_id));
    await page.settle();
    const other = page.monthClose();
    const otherBook = await other.client.load(month, other.scopeKey!);
    assert.equal(otherBook.documents.find(item => item.id === pending.id)?.status, "pendiente");
    await page.act(async () => page.api().chooseBusiness(A.grant_id));
    await page.settle();
    const returned = page.monthClose();
    const returnedBook = await returned.client.load(month, returned.scopeKey!);
    assert.equal(returnedBook.documents.find(item => item.id === pending.id)?.status, "pagado");
  } finally {
    await page.act(async () => page.root.unmount());
    page.host.remove();
    Object.assign(process.env, previousEnv);
  }
});
