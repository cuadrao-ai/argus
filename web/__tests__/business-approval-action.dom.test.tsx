import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessApprovalAction, BusinessDossier } from "@/lib/business-dossier";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];

async function mountReview(dossier: BusinessDossier, mode: "live" | "fixture") {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  const sent: (BusinessApprovalAction | undefined)[] = [];
  const context = {
    source: { mode, dossier: async () => dossier, approveDraft: async (_id: string, _version: number, _key: string, action?: BusinessApprovalAction) => { sent.push(action); return dossier; } },
    reload: () => undefined,
    records: { inbox: [] },
    openPanel: () => undefined,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Review draftId={dossier.draft_id} /></BusinessContext.Provider></I18nextProvider>));
  const approve = (label: string) => [...host.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === label);
  const close = async () => { await act(async () => root.unmount()); host.remove(); await GlobalRegistrator.unregister(); };
  return { act, approve, sent, close };
}

async function ready(over: Partial<BusinessDossier>): Promise<BusinessDossier> {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.ready);
  // No fiscal number, so approval asks no RNC question first.
  return { ...dossier, fiscal_known: false, ...over };
}

for (const mode of ["live", "fixture"] as const) {
  test(`approval sends the action the server names, not one read from the kind (${mode})`, async () => {
    // The facts say expense; the server's approval_action is the one that approves.
    const page = await mountReview(await ready({ approval_action: "record_income" }), mode);
    try {
      const button = page.approve("Aprobar ingreso");
      assert.ok(button, "the label follows the server's action");
      assert.equal(button.disabled, false);
      await page.act(async () => button.click());
      assert.deepEqual(page.sent, ["record_income"]);
    } finally { await page.close(); }
  });
}

test("with no approval action from the server there is nothing to approve", async () => {
  for (const approval_action of [null, undefined]) {
    const page = await mountReview(await ready({ approval_action }), "live");
    try {
      const button = page.approve("Aprobar");
      assert.ok(button);
      assert.equal(button.disabled, true);
      await page.act(async () => button.click());
      assert.deepEqual(page.sent, []);
    } finally { await page.close(); }
  }
});
