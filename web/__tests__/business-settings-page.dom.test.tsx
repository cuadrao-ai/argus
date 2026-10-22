import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace, ReceiptReading } from "@/lib/business-api";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { FiscalProfile } from "@/lib/business-dgii";

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

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const CLIENT: GrantedSpace = { space_id: "s-client", name: "Colmado Peña", grant_id: "g-client", role: "accountant", capabilities: ["read", "prepare"], access_seen: true };

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
  function Shell() {
    const workspace = useChatWorkspace();
    const context = useBusiness();
    panel = context.panel;
    chosenReady = context.chosen?.grant_id === space.grant_id;
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
  return { host, settle, tabs, chosenTab, choose, click, panel: () => panel, close: () => act(async () => root.unmount()) };
}

const params = () => new URLSearchParams(window.location.search);

describe("the Negocio page", () => {
  test("the owner sees Datos, Equipo y accesos and Correo de recibos, and each tab writes the address bar", async () => {
    const page = await mount("view=business", OWN);
    try {
      assert.equal(page.host.querySelector('[data-testid="business-settings"] h2')?.textContent, "Negocio");
      assert.deepEqual(page.tabs().map((tab) => tab.textContent?.trim()), ["Datos", "Equipo y accesos", "Correo de recibos"]);
      assert.equal(page.chosenTab(), "Datos");
      await page.settle(() => page.host.querySelector('input[name="business-name"]') !== null);
      assert.equal(page.host.querySelector<HTMLInputElement>('input[name="business-name"]')?.value, "Mi negocio", "the owner names the business in Datos");
      assert.equal(page.host.querySelector<HTMLInputElement>('input[name="tax-id-value"]')?.value, "131245678");
      assert.equal(page.host.textContent?.includes("Mi negocio · RNC"), false, "an editable profile shows no summary line");

      await page.choose("Equipo y accesos");
      assert.deepEqual(page.panel(), { kind: "business", tab: "equipo" });
      assert.equal(params().get("view"), "business");
      assert.equal(params().get("tab"), "equipo");
      assert.equal(page.chosenTab(), "Equipo y accesos");
      await page.settle(() => [...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Dar acceso"));
      assert.ok([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Dar acceso"), "the team tab holds the access controls");

      await page.choose("Correo de recibos");
      assert.equal(params().get("tab"), "correo");
      assert.equal(page.chosenTab(), "Correo de recibos");

      await page.choose("Datos");
      assert.equal(params().get("view"), "business");
      assert.equal(params().get("tab"), "datos");
    } finally {
      await page.close();
    }
  });

  test("an accountant sees Datos and Correo de recibos only, and a team link shows Datos", async () => {
    const page = await mount("view=business&tab=equipo", CLIENT);
    try {
      await page.settle(() => page.tabs().length === 2);
      assert.deepEqual(page.tabs().map((tab) => tab.textContent?.trim()), ["Datos", "Correo de recibos"]);
      assert.equal(page.chosenTab(), "Datos");
      assert.equal([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Dar acceso"), false);
    } finally {
      await page.close();
    }
  });

  test("an old ?view=access link lands on Equipo y accesos under the new address", async () => {
    const page = await mount("view=access", OWN);
    try {
      assert.deepEqual(page.panel(), { kind: "business", tab: "equipo" });
      assert.equal(page.chosenTab(), "Equipo y accesos");
      assert.equal(params().get("view"), "business");
      assert.equal(params().get("tab"), "equipo");
    } finally {
      await page.close();
    }
  });

  test("a failed read of the name and RNC says so, and Reintentar reads again", async () => {
    let reads = 0;
    const fiscalProfile = async (): Promise<FiscalProfile> => {
      reads += 1;
      if (reads === 1) throw new Error("offline");
      return { name: "Ferretería Luna", tax_id: { type: "rnc", value: "131245678" }, can_edit: false };
    };
    const page = await mount("view=business", OWN, { fiscalProfile });
    try {
      const datos = () => page.host.querySelector('[data-testid="business-fiscal-profile"]');
      await page.settle(() => datos()?.querySelector('[role="alert"]') != null);
      const alert = datos()?.querySelector('[role="alert"]');
      assert.ok(alert?.textContent?.includes("No pudimos cargar el nombre y el RNC."));
      const retry = [...(alert?.querySelectorAll("button") ?? [])].find((button) => button.textContent?.trim() === "Reintentar");
      assert.ok(retry, "a Reintentar button");
      await page.click(retry);
      await page.settle(() => datos()?.querySelector('[role="alert"]') == null);
      assert.equal(reads, 2);
      assert.equal(datos()?.querySelector('[role="alert"]'), null);
      assert.ok(datos()?.textContent?.includes("Ferretería Luna · RNC 131245678"), "a read-only profile shows its summary line");
      assert.equal(datos()?.querySelector("input"), null);
    } finally {
      await page.close();
    }
  });

  describe("Lectura de recibos", () => {
    const reading = (over: Partial<ReceiptReading> = {}): ReceiptReading => ({ scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Texto del servidor", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null, ...over });
    const row = (page: Awaited<ReturnType<typeof mount>>) => page.host.querySelector('[data-testid="receipt-reading-row"]');
    const state = (page: Awaited<ReturnType<typeof mount>>) => row(page)?.querySelector('[data-testid="receipt-reading-state"]')?.textContent?.trim();

    test("Datos holds one row with the state in words, and its button opens the same sheet", async () => {
      const page = await mount("view=business", OWN, { receiptReading: async () => reading({ enabled: true }) });
      try {
        await page.settle(() => state(page) === "Activada");
        assert.equal(state(page), "Activada");
        assert.equal(row(page)?.querySelector("p")?.textContent, "Lectura de recibos");
        assert.equal(page.host.querySelector('[data-testid="receipt-reading-control"]'), null, "the row is not the notice");
        const change = [...(row(page)?.querySelectorAll("button") ?? [])].find((button) => button.textContent?.trim() === "Cambiar");
        assert.ok(change);
        await page.click(change);
        assert.ok(document.body.querySelector('[data-testid="receipt-reading-sheet"]')?.textContent?.includes("Texto del servidor"), "the server's words sit in the sheet");
        assert.ok(document.body.querySelector('[data-testid="receipt-reading-switch"]'));
      } finally {
        await page.close();
      }
    });

    test("an off setting reads Desactivada", async () => {
      const page = await mount("view=business", OWN, { receiptReading: async () => reading() });
      try {
        await page.settle(() => state(page) === "Desactivada");
        assert.equal(state(page), "Desactivada");
      } finally {
        await page.close();
      }
    });

    test("a setting that failed to load shows a dash and no button, never a guess", async () => {
      const page = await mount("view=business", OWN, { receiptReading: async () => { throw new Error("offline"); } });
      try {
        await page.settle(() => row(page) !== null);
        await page.settle(() => false);
        assert.equal(row(page)?.getAttribute("data-enabled"), "unknown");
        assert.ok(state(page)?.startsWith("-"));
        assert.ok(!/Activada|Desactivada/.test(state(page) ?? ""));
        assert.equal(row(page)?.querySelector("button"), null);
      } finally {
        await page.close();
      }
    });

    test("whoever may not change it sees the state and no button", async () => {
      const page = await mount("view=business", CLIENT, { receiptReading: async () => reading({ can_change: false }) });
      try {
        await page.settle(() => state(page) === "Desactivada");
        assert.equal(state(page), "Desactivada");
        assert.equal(row(page)?.querySelector("button"), null);
      } finally {
        await page.close();
      }
    });
  });
});


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


test("only the owner finds lifecycle controls in Datos, and Equipo has none", async () => {
  const previousFetch = globalThis.fetch; const previousAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async url => Response.json({ spaces: String(url).includes("owned-spaces") ? [{ space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", name: OWN.name, grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0", member_count: 0, reopen_until: "2026-11-20T17:45:00Z", export_windows: [], members: [] }] : [] });
  const owner = { ...OWN, space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438" };
  const page = await mount("view=business", owner, { mode: "live", spaceDirectory: async () => ({ spaces: [owner], closed_spaces: [] }) });
  try {
    await page.settle(() => page.host.querySelector('[data-testid="business-lifecycle-controls"]') !== null);
    assert.ok(page.host.querySelector('a[href*="lifecycle=close"]'));
    assert.ok(page.host.querySelector('a[href*="lifecycle=transfer"]'));
    await page.choose("Equipo y accesos");
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
