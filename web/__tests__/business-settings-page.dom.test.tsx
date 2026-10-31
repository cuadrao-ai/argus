import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, spyOn, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace, ReceiptReading } from "@/lib/business-api";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import type { BusinessDataSource } from "@/components/business-app/business-data";

// The Negocio page on the real workspace provider over the sample data: the
// address bar picks the tab, the tabs write it back, and only the owner sees
// who has access.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role:"owner",permissions:["read","prepare","approve","manage","assign_owner","download","export"],capabilities: ["read", "prepare", "approve"], access_seen: true };
const CLIENT: GrantedSpace = { space_id: "s-client", name: "Colmado Peña", grant_id: "g-client", role: "accountant", business_role:"editor",permissions:["read","prepare","download","export"],capabilities: ["read", "prepare"], access_seen: true };

async function mount(query: string, space: GrantedSpace, overrides: Partial<BusinessDataSource> = {}, rememberedGrant?: string) {
  search = query;
  window.history.replaceState(null, "", `/biz${query ? `?${query}` : ""}`);
  const { act, useEffect } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(rememberedGrant ?? (space.role === "owner" ? null : space.grant_id));
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), spaces: async () => [space], ...overrides };
  const shell = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined } as unknown as ChatShellBridge;
  let panel: BusinessPanelState = { kind: "overview" };
  let chosenReady = false;
  let selected:GrantedSpace|null=null;
  let reload=()=>{};
  function Shell() {
    const workspace = useChatWorkspace();
    const context = useBusiness();
    panel = context.panel;
    chosenReady = context.chosen?.grant_id === space.grant_id;
    selected=context.chosen;reload=context.reload;
    const connect = workspace?.onShellChange;
    useEffect(() => { connect?.(shell); }, [connect]);
    return <main>{workspace?.panel(shell)}</main>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Shell />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 80 && !done(); i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    }
  };
  const tabs = () => [...host.querySelectorAll<HTMLButtonElement>('[data-testid="business-settings-tabs"] [role="radio"]')];
  const chosenTab = () => tabs().find((tab) => tab.getAttribute("aria-checked") === "true")?.textContent?.trim();
  const choose = async (label: string) => {
    const tab = tabs().find((item) => item.textContent?.trim() === label);
    assert.ok(tab, `the ${label} tab`);
    await act(async () => tab.click());
  };
  await settle(() => chosenReady && host.querySelector('[data-testid="business-settings"]') !== null);
  const click = (element: Element) => act(async () => { (element as HTMLElement).click(); });
  return { host, settle, tabs, chosenTab, choose, click, panel: () => panel,chosen:()=>selected,reload:()=>act(async()=>reload()), close: () => act(async () => root.unmount()) };
}

const params = () => new URLSearchParams(window.location.search);

test("directory reload preserves the selected second Owner grant",async()=>{
 const second={...OWN,space_id:"second-owned",grant_id:"second-owner-grant",name:"Taller Sol"};
 const page=await mount("view=business",second,{spaces:async()=>[OWN,second]},second.grant_id);
 try{
  assert.equal(page.chosen()?.space_id,second.space_id);
  await page.reload();await page.settle(()=>page.chosen()?.space_id===second.space_id);
  const {getChosenGrant}=await import("@/lib/business-grant");
  assert.equal(getChosenGrant(),second.grant_id);assert.equal(page.chosen()?.grant_id,second.grant_id);
 }finally{await page.close();}
});

test("server Viewer permissions keep the approved live profile read only",async()=>{
 const previousFetch=globalThis.fetch,previousAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 const writes:string[]=[];
 const viewer:GrantedSpace={...CLIENT,business_role:"viewer",permissions:["read"],capabilities:["read"]};
 globalThis.fetch=async(url,init)=>{
  if(init?.method&&init.method!=="GET")writes.push(init.method);
  if(String(url).includes("fiscal-profile"))return Response.json({name:viewer.name,tax_id:null,can_edit:false});
  return Response.json({space_id:viewer.space_id,name:viewer.name,country:"DO",currency:"DOP",revision:7,details:{address:"Calle Sol 8"},appearance:{kind:"default"},image:null});
 };
 const page=await mount("view=business",viewer,{mode:"live",spaceDirectory:async()=>({spaces:[viewer],closed_spaces:[]})});
 try{
  await page.settle(()=>page.host.querySelector('[data-testid="business-profile-preview"]')!==null);
  assert.deepEqual(page.tabs().map(tab=>tab.textContent?.trim()),["Perfil","Recepción"]);
  assert.equal(page.host.querySelector('button[aria-label="Cambiar imagen"]'),null);
  const contact=[...page.host.querySelectorAll<HTMLButtonElement>("button")].find(button=>button.textContent?.includes("Ubicación y contacto"))!;
  await page.click(contact);
  const address=document.querySelector<HTMLInputElement>('[name="profile-address"]')!;
  assert.equal(address.value,"Calle Sol 8");assert.equal(address.disabled,true);
  assert.equal(document.querySelector('[data-testid="side-drawer"] button[type="submit"]'),null);
  assert.equal(document.querySelector('iframe[src*="invoicing"]'),null);
  assert.deepEqual(writes,[]);
 }finally{await page.close();globalThis.fetch=previousFetch;if(previousAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=previousAuth;}
});

describe("the Negocio page", () => {
  test("the owner sees Perfil, Acceso and Recepción, and each tab writes the address bar", async () => {
    const page = await mount("view=business", OWN);
    try {
      // The top bar carries the title on desktop, as on every main screen; Negocio has no Agregar of its own.
      assert.equal([...page.host.querySelectorAll('[data-testid="business-settings"] button')].some((button) => button.textContent?.includes("Agregar")), false);
      assert.deepEqual(page.tabs().map((tab) => tab.textContent?.trim()), ["Perfil", "Acceso", "Recepción"]);
      assert.equal(page.chosenTab(), "Perfil");
      assert.ok(page.host.querySelector('[data-testid="business-profile-preview"]'), "the approved profile overview is visible");
      const identity=[...page.host.querySelectorAll<HTMLButtonElement>("button")].find(button=>button.textContent?.includes("Identidad y datos fiscales"));
      assert.ok(identity);await page.click(identity);
      await page.settle(()=>document.querySelector('input[name="business-name"]')!==null);
      assert.equal(document.querySelector<HTMLInputElement>('input[name="business-name"]')?.value, OWN.name, "identity editing uses the chosen Business name");
      const close=[...document.querySelectorAll<HTMLButtonElement>("button")].find(button=>button.getAttribute("aria-label")==="Cerrar"&&button.closest('[data-testid="side-drawer"]'));
      assert.ok(close);await page.click(close);

      await page.choose("Acceso");
      assert.deepEqual(page.panel(), { kind: "business", tab: "equipo" });
      assert.equal(params().get("view"), "business");
      assert.equal(params().get("tab"), "equipo");
      assert.equal(page.chosenTab(), "Acceso");
      await page.settle(() => [...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Invita a un colaborador"));
      assert.ok([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Invita a un colaborador"), "the team tab holds the approved invitation control");

      await page.choose("Recepción");
      assert.equal(params().get("tab"), "correo");
      assert.equal(page.chosenTab(), "Recepción");

      await page.choose("Perfil");
      assert.equal(params().get("view"), "business");
      assert.equal(params().get("tab"), "datos");
    } finally {
      await page.close();
    }
  });

  test("an accountant sees Perfil and Recepción only, and a team link shows Perfil", async () => {
    const page = await mount("view=business&tab=equipo", CLIENT);
    try {
      await page.settle(() => page.tabs().length === 2);
      assert.deepEqual(page.tabs().map((tab) => tab.textContent?.trim()), ["Perfil", "Recepción"]);
      assert.equal(page.chosenTab(), "Perfil");
      assert.equal([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Dar acceso"), false);
    } finally {
      await page.close();
    }
  });

  test("an old ?view=access link lands on Acceso under the new address", async () => {
    const page = await mount("view=access", OWN);
    try {
      assert.deepEqual(page.panel(), { kind: "business", tab: "equipo" });
      assert.equal(page.chosenTab(), "Acceso");
      assert.equal(params().get("view"), "business");
      assert.equal(params().get("tab"), "equipo");
    } finally {
      await page.close();
    }
  });

  test("a failed read of the name and RNC says so, and Reintentar reads again", async () => {
    const previousFetch=globalThis.fetch,previousAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
    process.env.NEXT_PUBLIC_MOCK_AUTH="true";
    let reads = 0;
    globalThis.fetch=async url=>{
      if(String(url).includes("fiscal-profile")){
        reads++;
        if(reads===1)return Response.json({code:"unavailable"},{status:503});
        return Response.json({name:OWN.name,tax_id:{type:"rnc",value:"131245678"},can_edit:true});
      }
      if(String(url).includes("/profile"))return Response.json({space_id:OWN.space_id,name:OWN.name,country:"DO",currency:"DOP",revision:0,details:{},appearance:{kind:"default"},image:null});
      return Response.json({spaces:[]});
    };
    const page = await mount("view=business", OWN, { mode:"live",spaceDirectory:async()=>({spaces:[OWN],closed_spaces:[]}) });
    try {
      await page.settle(() => page.host.querySelector('[role="alert"]') != null);
      const alert = page.host.querySelector('[role="alert"]');
      assert.ok(alert?.textContent?.includes("No pudimos cargar tu negocio"));
      const retry = [...page.host.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Reintentar");
      assert.ok(retry, "a Reintentar button");
      await page.click(retry);
      await page.settle(() => page.host.querySelector('[data-testid="business-profile-preview"]') != null);
      assert.equal(reads, 2);
      assert.equal(page.host.querySelector('[role="alert"]'), null);
      assert.ok(page.host.textContent?.includes("RNC 131245678"), "the approved profile summary uses accepted fiscal facts");
      assert.equal(page.host.querySelector("input"), null);
    } finally {
      await page.close();globalThis.fetch=previousFetch;if(previousAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=previousAuth;
    }
  });

  describe("Lectura de recibos", () => {
    const reading = (over: Partial<ReceiptReading> = {}): ReceiptReading => ({ scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Texto del servidor", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null, ...over });
    const row = (page: Awaited<ReturnType<typeof mount>>) => page.host.querySelector('[data-testid="receipt-reading-inline"]');
    const toggle = (page: Awaited<ReturnType<typeof mount>>) => row(page)?.querySelector<HTMLButtonElement>('[role="switch"]');

    test("Reception has the inline switch and disclosure, while Profile has neither", async () => {
      const page = await mount("view=business", OWN, { receiptReading: async () => reading({ enabled: true }), setReceiptReading: async (_snapshot,enabled) => reading({enabled}) });
      try {
        assert.equal(row(page),null);
        await page.choose("Recepción");
        await page.settle(() => toggle(page)?.getAttribute("aria-checked") === "true");
        assert.equal(toggle(page)?.getAttribute("aria-checked"),"true");
        assert.ok(row(page)?.textContent?.includes("Texto del servidor"));
        assert.equal(document.querySelector('[data-testid="receipt-reading-sheet"]'),null);
        await page.click(toggle(page)!);
        await page.settle(() => toggle(page)?.getAttribute("aria-checked") === "false");
        assert.equal(toggle(page)?.getAttribute("aria-checked"),"false");
      } finally { await page.close(); }
    });
    test("an off setting stays off when an update fails and offers inline retry", async () => {
      const page = await mount("view=business&tab=correo", OWN, { receiptReading: async () => reading(), setReceiptReading: async () => {throw new Error("offline");} });
      try {
        await page.settle(() => toggle(page) != null);
        await page.click(toggle(page)!);
        await page.settle(() => row(page)?.querySelector('[role="alert"]') != null);
        assert.equal(toggle(page)?.getAttribute("aria-checked"),"false");
        assert.ok(row(page)?.querySelector('[role="alert"]')?.textContent?.includes("Reintentar"));
      } finally { await page.close(); }
    });
    test("a failed load shows unavailable and no switch rather than guessing off", async () => {
      const page = await mount("view=business&tab=correo", OWN, { receiptReading: async () => { throw new Error("offline"); } });
      try {
        await page.settle(() => row(page) != null);
        assert.equal(row(page)?.getAttribute("data-enabled"), "unknown");
        assert.ok(row(page)?.textContent?.includes("No disponible"));
        assert.equal(toggle(page),null);
      } finally { await page.close(); }
    });
    test("a member without change access sees a disabled switch", async () => {
      const page = await mount("view=business&tab=correo", CLIENT, { receiptReading: async () => reading({ can_change: false }) });
      try {
        await page.settle(() => toggle(page) != null);
        assert.equal(toggle(page)?.getAttribute("aria-checked"),"false");
        assert.equal(toggle(page)?.disabled,true);
      } finally { await page.close(); }
    });
    test("reception shows the sender list and leaves received-mail history closed", async () => {
      const errors=spyOn(console,"error");
      const page=await mount("view=business&tab=correo",OWN);
      try {
        await page.settle(() => page.host.querySelector('[data-testid="email-senders"]') !== null);
        assert.ok(page.host.querySelector('[data-testid="email-senders"]'));
        assert.equal(errors.mock.calls.some(call=>String(call[0]).includes("same key")),false);
        assert.equal(page.host.textContent?.includes("Ver correos recibidos"), false);
        assert.equal(page.host.querySelector('[data-testid="email-history"]'), null);
      }finally{errors.mockRestore();await page.close();}
    });
  });});


test("a remembered closed membership shows closure rather than removed access", async () => {
  const held = { space_id: CLIENT.space_id, grant_id: CLIENT.grant_id, name: CLIENT.name, role: "accountant" as const, closed_at: "2026-10-21T17:45:00Z", reopen_until: "2026-11-20T17:45:00Z" };
  let creates = 0;
  const page = await mount("view=business", CLIENT, {
    mode: "live", spaceDirectory: async () => ({ spaces: [OWN], closed_spaces: [held] }),
    ensureSpace: async () => { creates += 1; throw new Error("closed membership must not create a workspace"); },
  });
  try {
    assert.ok(page.host.querySelector('[data-testid="business-member-closed"]'));
    assert.ok(page.host.textContent?.includes("Colmado Peña está cerrado."));
    assert.equal(page.host.textContent?.includes("Ya no tienes acceso"), false);
    assert.equal(page.host.querySelector('[data-testid="business-settings"]'), null);
    assert.equal(creates, 0);
  } finally { await page.close(); }
});

test("a live workspace offers a dismissible recovery banner for an owned closed business", async () => {
  const page = await mount("view=business", CLIENT, { mode: "live", spaceDirectory: async () => ({ spaces: [CLIENT], closed_spaces: [{ space_id: "s-closed", grant_id: "g-closed", name: "Taller Nube", role: "owner", closed_at: "2026-10-21T17:45:00Z", reopen_until: "2026-11-20T17:45:00Z" }] }) });
  try {
    const banner = page.host.querySelector('[data-testid="business-closed-owner-banner"]');
    assert.ok(banner);
    assert.ok(banner.textContent?.includes("Taller Nube"));
    assert.ok(banner.textContent?.includes("hora de RD"));
    assert.ok(banner.querySelector('a[href*="lifecycle=manage"]'));
    await page.click(banner.querySelector('button')!);
    assert.equal(page.host.querySelector('[data-testid="business-closed-owner-banner"]'), null);
    assert.ok(page.host.querySelector('[data-testid="business-settings"]'));
  } finally { await page.close(); }
});


test("an absent remembered membership still shows removed access", async () => {
  const page = await mount("view=business", CLIENT, { mode: "live", spaceDirectory: async () => ({ spaces: [OWN], closed_spaces: [] }) });
  try {
    assert.ok(page.host.querySelector('[data-testid="removed-member-screen"]'));
    assert.equal(page.host.querySelector('[data-testid="business-member-closed"]'), null);
  } finally { await page.close(); }
});


test("only the owner finds lifecycle controls in Datos, and Acceso has none", async () => {
  const previousFetch = globalThis.fetch; const previousAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async url => Response.json({ spaces: String(url).includes("owned-spaces") ? [{ space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", name: OWN.name, grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0", member_count: 0, reopen_until: "2026-11-20T17:45:00Z", export_windows: [], members: [] }] : [] });
  const owner = { ...OWN, space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438" };
  const page = await mount("view=business", owner, { mode: "live", spaceDirectory: async () => ({ spaces: [owner], closed_spaces: [] }) });
  try {
    await page.settle(() => page.host.querySelector('[data-testid="business-lifecycle-controls"]') !== null);
    assert.ok(page.host.querySelector('a[href*="lifecycle=close"]'));
    assert.ok(page.host.querySelector('a[href*="lifecycle=transfer"]'));
    await page.choose("Acceso");
    assert.equal(page.host.querySelector('[data-testid="business-lifecycle-controls"]'), null);
  } finally { await page.close(); globalThis.fetch = previousFetch; if (previousAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = previousAuth; }
});


test("returning from an owner lifecycle action does not report removed access", async () => {
  const page = await mount("view=business", OWN, { spaces: async () => [OWN] }, OWN.grant_id);
  try {
    assert.equal(page.host.querySelector('[data-testid="removed-member-screen"]') !== null, false, "owner return must not show removed access");
    assert.ok(page.host.querySelector('[data-testid="business-settings"]'));
  } finally { await page.close(); }
});
