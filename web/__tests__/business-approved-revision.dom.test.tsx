import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDossier } from "@/lib/business-dossier";

// The real workspace and review page over the sample source. A Personal mark
// answers like the server: one more history revision, the approval untouched.
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

async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const source = {
    ...fixture,
    markPersonal: async (id: string, version: number, personal: boolean): Promise<BusinessDossier> => {
      const current = await fixture.dossier(id);
      assert.equal(version, current.version);
      const after = { ...current.facts, business_share: { state: "known" as const, value: { kind: personal ? "none" as const : "all" as const }, origin: "member_set" as const, verified: true, source_ids: [] } };
      return { ...current, version: current.version + 1, personal, facts: after, history: [...current.history, { ...current.history[current.history.length - 1], version: current.version + 1, before: current.facts, after, created_at: "2026-10-12T15:00:00Z" }] };
    },
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return <BusinessPanel />;
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
  const wait = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out: ${host.textContent?.slice(0, 300)}`);
  };
  const click = async (selector: string, done: () => boolean) => {
    const target = host.querySelector<HTMLButtonElement>(selector);
    assert.ok(target, `${selector} is on the page`);
    await act(async () => target.click());
    await wait(done);
  };
  const recorded = () => host.querySelector('[data-testid="receipt-review-fields"] [role="status"]')?.textContent ?? null;
  const revision = () => [...host.querySelectorAll("header span")].map((item) => item.textContent).find((text) => text?.startsWith("Revisión")) ?? null;
  return { act, root, host, wait, click, recorded, revision, open: (draftId: string) => act(async () => api!.openPanel({ kind: "draft", draftId })) };
}

describe("a recorded receipt names the revision that was approved", () => {
  test("approving revision 2 then marking it Personal keeps revisión 2 and the approval date", async () => {
    const page = await mount();
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    await page.open(dossierFixtureIds.ready);
    await page.wait(() => [...page.host.querySelectorAll("button")].some((item) => item.textContent === "Aprobar gasto"));
    const approve = [...page.host.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === "Aprobar gasto")!;
    await page.act(async () => approve.click());
    await page.wait(() => page.recorded() !== null);
    assert.equal(page.recorded(), "Se registró un gasto tras aprobar la revisión 2.Registrado el 10 oct 2026");

    await page.click('[data-testid="receipt-mark-personal"]', () => page.revision() === "Revisión 4");
    assert.equal(page.revision(), "Revisión 4", "the header names the latest revision the mark added");
    assert.equal(page.recorded(), "Se registró un gasto tras aprobar la revisión 2.Registrado el 10 oct 2026");
    await page.act(async () => page.root.unmount());
  });
});
