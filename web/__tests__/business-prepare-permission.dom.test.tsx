import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace } from "@/lib/business-api";

// Who may add records is the server's prepare capability on the selected Business, never the legacy role label:
// every grantee is labelled "accountant", whether an admin who prepares or a viewer who only reads.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 390, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
let unmount = async () => {};
afterEach(async () => {
  await unmount();
  unmount = async () => {};
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const GRANTS = {
  admin: { space_id: "client-admin", name: "Ferretería sintética", grant_id: "grant-admin", role: "accountant", business_role: "admin", permissions: ["read", "prepare", "manage", "download", "export"], capabilities: ["read", "prepare"], access_seen: true },
  viewer: { space_id: "client-viewer", name: "Colmado sintético", grant_id: "grant-viewer", role: "accountant", business_role: "viewer", permissions: ["read"], capabilities: ["read"], access_seen: true },
} satisfies Record<string, GrantedSpace>;

async function mount(grant: GrantedSpace) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const BusinessHeader = (await import("@/components/business-app/foundation/BusinessHeader")).default;
  const { SetupDossier } = await import("@/components/business-app/inicio/HomeSetup");
  const { useRowCommands } = await import("@/components/business-app/transacciones/transacciones-commands");
  const { useState } = await import("react");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = { ...fixture, spaces: async () => [grant] };
  let searchActions: string[] | null = null;
  let rowCommands: string[] | null = null;
  let chosen: GrantedSpace | null = null;
  function Probe() {
    const business = useBusiness();
    const [setupOpen, setSetupOpen] = useState(true);
    chosen = business.chosen;
    searchActions = useChatWorkspace()?.search?.shortcuts?.find((group) => group.id === "actions")?.hits.map((hit) => hit.id) ?? null;
    const commands = useRowCommands({} as never);
    rowCommands = commands({ id: "movement", match: { state: "falta_comprobante" } } as never).map((command) => command.id);
    return (
      <div>
        <div data-testid="top-bar"><BusinessHeader home={false} name={null} title="Bandeja" screen="inbox" /></div>
        <div data-testid="registros-bar"><BusinessHeader home={false} name={null} title="Registros" screen="transactions" /></div>
        <div data-testid="bandeja"><BusinessInboxPanel /></div>
        {setupOpen ? <SetupDossier steps={[{ key: "first_document", required: true, done: false }]} onClose={() => setSetupOpen(false)} /> : null}
      </div>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  for (let i = 0; i < 60 && (chosen as GrantedSpace | null)?.grant_id !== grant.grant_id; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  }
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
  unmount = () => act(async () => root.unmount());
  const adds = (area: string) => host.querySelectorAll(`[data-testid="${area}"] [data-testid="business-primary-upload"]`).length;
  return { act, host, adds, searchActions: () => searchActions, rowCommands: () => rowCommands, chosen: () => chosen as GrantedSpace | null };
}

describe("adding records follows the server's prepare capability", () => {
  test("an admin grant with prepare sees Agregar in the top bar, Registros, the Bandeja, search, bank matching and setup", async () => {
    const page = await mount(GRANTS.admin);
    assert.equal(page.chosen()?.grant_id, "grant-admin");
    assert.equal(page.adds("top-bar"), 1, "the top bar holds Agregar");
    assert.equal(page.adds("registros-bar"), 1, "Registros holds Agregar");
    assert.equal(page.adds("bandeja"), 1, "a phone's Bandeja holds Agregar");
    assert.ok(page.searchActions()?.includes("add"), "search offers Agregar");
    assert.ok(page.rowCommands()?.includes("agregar"), "a movement missing its receipt offers Agregar");
    const step = document.querySelector<HTMLButtonElement>('[data-testid="home-setup-step-first_document"]');
    assert.ok(step);
    await page.act(async () => step.click());
    await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.equal(document.querySelector('[data-testid="home-setup-panel"]'), null, "the step closes the setup dossier");
    assert.ok([...document.querySelectorAll('[role="dialog"]')].some((dialog) => dialog.textContent?.startsWith("Agregar")), "the first-document step opens Agregar's upload");
  });

  test("a viewer grant without prepare sees no Agregar anywhere", async () => {
    const page = await mount(GRANTS.viewer);
    assert.equal(page.chosen()?.grant_id, "grant-viewer");
    for (const area of ["top-bar", "registros-bar", "bandeja"]) assert.equal(page.adds(area), 0, `${area} has no Agregar`);
    assert.equal(page.host.querySelector('[data-testid="business-primary-review"]'), null, "a viewer is not asked to review");
    assert.equal(page.searchActions()?.includes("add"), false, "search offers no Agregar");
    assert.equal(page.searchActions()?.includes("copy_forward"), false, "search hands out no forwarding address");
    assert.deepEqual(page.rowCommands(), ["sin_comprobante"], "bank matching offers no Agregar");
  });
});
