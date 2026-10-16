import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { ChatShellBridge, WorkspaceSearch } from "@/components/chat/ChatWorkspace";
import { useBusiness as useBusinessContext } from "@/components/business-app/BusinessWorkspace";

// Sprint map §1.8, the three locked polish lines, checked on the real
// Business components in Spanish over the sample data source.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

type Shell = Pick<ChatShellBridge, "currentView" | "conversationId" | "isBelowTablet" | "sidebarCollapsed" | "showWorkspace" | "newChat" | "prepareQuestion">;
const shell = (overrides: Partial<Shell> = {}): ChatShellBridge =>
  ({ currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined, ...overrides }) as ChatShellBridge;

function flatten(node: unknown, prefix = "", out = new Map<string, string>()) {
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object") flatten(value, path, out);
    else out.set(path, String(value));
  }
  return out;
}
const SPANISH = flatten(spanish);
const ENGLISH = flatten(english);
const SPANISH_VALUES = new Set(SPANISH.values());
/** Text that exists only in English: shown to a Spanish reader, it is a missed translation. */
const ENGLISH_ONLY = new Set([...ENGLISH.values()].filter((value) => !SPANISH_VALUES.has(value)));

type Mounted = Awaited<ReturnType<typeof mount>>;

async function mount(
  view: (api: { shell: ChatShellBridge }) => ReactNode,
  overrides: Partial<BusinessDataSource> = {},
) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), ...overrides };
  let business: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    business = useBusiness();
    return <>{view({ shell: shell() })}</>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessWorkspaceProvider source={source as never}>
          <Probe />
        </BusinessWorkspaceProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
  };
  const click = async (element: Element | null | undefined) => {
    assert.ok(element, "the control is on screen");
    await act(async () => { (element as HTMLElement).click(); });
  };
  const buttons = (name: string) => [...host.querySelectorAll("button")].filter((button) => button.textContent?.trim() === name);
  const close = () => act(async () => root.unmount());
  return { act, host, settle, click, buttons, close, business: () => business!, source };
}

const overviewTitle = (page: Mounted) => page.host.querySelector("#business-overview-title")?.textContent ?? null;

describe("§1.8 line 100: the Business is named by its name, and Argus is not named", () => {
  const ownSpace = (name: string): Partial<BusinessDataSource> => ({
    spaces: async () => [{ space_id: "own", name, grant_id: "own-grant", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true }],
  });

  test("the Resumen title is the owner's business name", async () => {
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    const page = await mount(() => <BusinessOverviewPanel />, ownSpace("Colmado Lucía"));
    await page.settle(() => overviewTitle(page) === "Colmado Lucía");
    assert.equal(overviewTitle(page), "Colmado Lucía");
    await page.close();
  });

  test("a Business without a name is called Mi negocio, never Tu negocio or My business", async () => {
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    const page = await mount(() => <BusinessOverviewPanel />, ownSpace(""));
    await page.settle(() => page.business().spaces !== null);
    assert.equal(overviewTitle(page), "Mi negocio");
    await page.close();
  });

  test("a saved English default uses the Spanish fallback without changing a custom name", async () => {
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    for (const [saved, displayed] of [["My business", "Mi negocio"], ["My business supplies", "My business supplies"]]) {
      const page = await mount(() => <BusinessOverviewPanel />, ownSpace(saved));
      await page.settle(() => page.business().spaces !== null);
      assert.equal(overviewTitle(page), displayed);
      assert.equal(page.business().chosen?.name, saved, "the saved name remains unchanged");
      await page.close();
    }
  });

  test("the name question asks how we should call you, in both languages", () => {
    assert.equal(SPANISH.get("settings.profile.preferred_name"), "¿Cómo quieres que te llamemos?");
    assert.equal(ENGLISH.get("settings.profile.preferred_name"), "What should we call you?");
  });

  test("no Business string names Argus or says My business in Spanish", () => {
    const business = [...SPANISH].filter(([key]) => /^(business|business_access)\./.test(key) || key === "settings.profile.preferred_name");
    assert.ok(business.length > 300, "the Business strings were found");
    assert.deepEqual(business.filter(([, value]) => /Argus|My business/.test(value)), []);
    const englishBusiness = [...ENGLISH].filter(([key]) => /^(business|business_access)\./.test(key) || key === "settings.profile.preferred_name");
    assert.deepEqual(englishBusiness.filter(([, value]) => /Argus/.test(value)), []);
  });
});

describe("§1.8 line 101: dates read 1 oct 2026 and the period label follows the period", () => {
  test("a fixed day reads 1 oct 2026 wherever a Business date is shown", async () => {
    const { formatDay, formatTimestamp } = await import("@/components/business-app/business-format");
    assert.equal(formatDay("2026-10-01", "es-419"), "1 oct 2026");
    assert.equal(formatDay("2026-10-01T23:30:00Z", "es-419"), "1 oct 2026");
    assert.match(formatTimestamp("2026-10-01T16:00:00Z", "es-419"), /^1 oct 2026, /);
    const { renderToStaticMarkup } = await import("react-dom/server");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const { AccessList } = await import("@/components/business-app/BusinessAccessPanel");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={i18n}>
        <AccessList access={{ grants: [{ id: "g", email: null, display_name: "Lucía", capabilities: ["read"], created_at: "2026-10-01T16:00:00Z", owner: true }], invites: [] }} busyId={null} onRemove={() => undefined} />
      </I18nextProvider>,
    );
    assert.ok(html.includes("Desde 1 oct 2026"));
  });

  test("changing the period changes the Resumen card labels and the covered dates", async () => {
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    const page = await mount(() => <BusinessOverviewPanel />);
    const label = () => page.host.querySelector('[data-testid="overview-real-expenses"] > span')?.textContent ?? null;
    const coverage = () => [...page.host.querySelectorAll("p")].map((p) => p.textContent ?? "").find((text) => text.startsWith("Cubre del")) ?? null;
    await page.settle(() => label() !== null);
    assert.equal(label(), "Gastos reales · este mes");
    await page.click(page.buttons("Mes pasado")[0]);
    await page.settle(() => label() === "Gastos reales · mes pasado");
    assert.equal(label(), "Gastos reales · mes pasado");
    await page.act(async () => page.business().setPeriod({ key: "custom", from: "2026-09-01", to: "2026-09-30" }));
    await page.settle(() => coverage()?.startsWith("Cubre del 1 sept 2026 al 30 sept 2026.") ?? false);
    assert.equal(label(), "Gastos reales · personalizado");
    assert.ok(coverage()?.startsWith("Cubre del 1 sept 2026 al 30 sept 2026."), coverage() ?? "no coverage line");
    await page.close();
  });
});

describe("§1.8 line 102: danger, Crear, sidebar labels, empty states, headings and Spanish labels", () => {
  test("removing access is a red action that asks first; only the confirmation removes", async () => {
    const BusinessAccessPanel = (await import("@/components/business-app/BusinessAccessPanel")).default;
    const revoked: string[] = [];
    const page = await mount(() => <BusinessAccessPanel />, { revokeAccessGrant: async (id: string) => { revoked.push(id); } });
    await page.settle(() => page.buttons("Quitar acceso").length === 1);
    const remove = page.buttons("Quitar acceso")[0];
    assert.match(remove.className, /text-\[#a8434c\]/);
    await page.click(remove);
    const dialog = page.host.querySelector('[role="alertdialog"]');
    assert.ok(dialog);
    assert.equal(dialog.querySelector("p")?.textContent, "¿Quitar el acceso de contadora@example.test? Deja de ver y preparar al instante.");
    const [confirm] = page.buttons("Sí, quitar");
    const [cancel] = page.buttons("Cancelar");
    assert.match(confirm.className, /bg-\[#a8434c\]/);
    assert.doesNotMatch(cancel.className, /a8434c/);
    assert.deepEqual(revoked, [], "nothing is removed before the confirmation");
    await page.click(confirm);
    assert.deepEqual(revoked, ["grant-contadora"]);
    await page.close();
  });

  test("Crear is a labeled button at least 44px tall, in the sidebar and on a phone", async () => {
    const BusinessCreateMenu = (await import("@/components/business-app/BusinessCreateMenu")).default;
    const page = await mount(({ shell }) => (
      <>
        <div data-testid="rail"><BusinessCreateMenu shell={shell} /></div>
        <div data-testid="phone"><BusinessCreateMenu shell={shell} compact /></div>
      </>
    ));
    for (const id of ["business-create", "business-create-compact"]) {
      const button = page.host.querySelector(`[data-testid="${id}"]`);
      assert.ok(button, id);
      assert.equal(button.textContent?.trim(), "Crear", `${id} shows the word Crear`);
      assert.match(button.className, /(^|\s)(min-)?h-11(\s|$)/, `${id} is at least 44px tall`);
    }
    await page.close();
  });

  test("every sidebar icon carries its Spanish name, also when the sidebar is collapsed", async () => {
    const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
    for (const sidebarCollapsed of [false, true]) {
      const page = await mount(() => <BusinessSidebarNav shell={shell({ sidebarCollapsed })} />);
      const nav = page.host.querySelector('[data-testid="business-sidebar-nav"]');
      assert.equal(nav?.getAttribute("aria-label"), "Negocio");
      const items = [...(nav?.querySelectorAll("button") ?? [])];
      assert.deepEqual(items.map((button) => button.textContent?.replace(/\d+$/, "").trim()), ["Resumen", "Bandeja", "Gastos", "Novedades", "Acceso"]);
      assert.ok(items.every((button) => button.querySelector("svg")), "each name sits with its icon");
      await page.close();
    }
  });

  test("Correos recibidos says so when no email has arrived", async () => {
    const BusinessEmailDeliveries = (await import("@/components/business-app/BusinessEmailDeliveries")).default;
    const page = await mount(() => <BusinessEmailDeliveries />, { emailDeliveries: async () => [] });
    await page.settle(() => (page.host.textContent ?? "").includes("Todavía no has recibido correos."));
    assert.ok(page.host.querySelector('section[aria-label="Correos recibidos"]'));
    assert.ok((page.host.textContent ?? "").includes("Todavía no has recibido correos."));
    await page.close();
  });

  test("Buscar finds nothing for an unknown word and gives the Spanish hint for the empty result", async () => {
    const { useBusinessSearch } = await import("@/components/business-app/useBusinessSearch");
    let built: WorkspaceSearch | null = null;
    const page = await mount(() => {
      function Probe() {
        const { source } = useBusinessContext();
        built = useBusinessSearch({ source, chatAvailable: true, accounts: [], openPanel: () => undefined, setPeriod: () => undefined });
        return null;
      }
      return <Probe />;
    });
    const search = built as WorkspaceSearch | null;
    assert.ok(search);
    assert.equal(search.copy.noResultsHint, "Prueba con el nombre de un comercio o de un archivo.");
    assert.equal(search.copy.placeholder, "Buscar gastos, recibos y chats");
    const groups = await search.find("zzqqxx");
    assert.deepEqual(groups.flatMap((group) => group.hits), []);
    await page.close();
  });

  test("the Business screens have no empty heading and no English label for a Spanish reader", async () => {
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
    const BusinessExpensesPanel = (await import("@/components/business-app/BusinessExpensesPanel")).default;
    const BusinessUpdatesPanel = (await import("@/components/business-app/BusinessUpdatesPanel")).default;
    const BusinessAccessPanel = (await import("@/components/business-app/BusinessAccessPanel")).default;
    const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
    const BusinessCreateMenu = (await import("@/components/business-app/BusinessCreateMenu")).default;
    const page = await mount(({ shell }) => (
      <>
        <BusinessSidebarNav shell={shell} />
        <BusinessCreateMenu shell={shell} />
        <BusinessCreateMenu shell={shell} compact />
        <BusinessOverviewPanel />
        <BusinessInboxPanel />
        <BusinessExpensesPanel />
        <BusinessUpdatesPanel />
        <BusinessAccessPanel />
      </>
    ));
    await page.settle(() => page.host.querySelectorAll('[data-testid="business-inbox-receipts"] > li').length > 0 && page.buttons("Quitar acceso").length > 0);
    const headings = [...page.host.querySelectorAll("h1,h2,h3,h4,h5,h6,[role=heading]")];
    assert.ok(headings.length >= 5);
    assert.deepEqual(headings.filter((heading) => !heading.textContent?.trim()).map((heading) => heading.outerHTML), []);
    const labels = [...page.host.querySelectorAll("[aria-label],[title],[placeholder]")].flatMap((element) =>
      ["aria-label", "title", "placeholder"].map((name) => element.getAttribute(name)).filter((value): value is string => Boolean(value)),
    );
    assert.ok(labels.length >= 5);
    assert.deepEqual(labels.filter((label) => ENGLISH_ONLY.has(label) || /Argus/.test(label)), []);
    assert.deepEqual([...page.host.querySelectorAll("*")].map((element) => element.childNodes).flatMap((nodes) => [...nodes]).filter((node) => node.nodeType === 3 && /Argus|My business/.test(node.textContent ?? "")).map((node) => node.textContent), []);
    await page.close();
  });
});
