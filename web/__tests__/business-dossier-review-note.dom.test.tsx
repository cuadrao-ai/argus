import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const SENTENCE = "No pudimos verificar este remitente.";
const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];

async function mount(reviewNote: string | null | undefined) {
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
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.ready);
  const shown: BusinessDossier = { ...dossier, fiscal_known: false, ...(reviewNote === undefined ? {} : { review_note: reviewNote }) };
  const context = {
    source: { mode: "fixture", dossier: async () => shown },
    reload: () => undefined,
    records: { inbox: [] },
    openPanel: () => undefined,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Review draftId={shown.draft_id} /></BusinessContext.Provider></I18nextProvider>));
  const approve = [...host.querySelectorAll("button")].find((button) => button.textContent === "Aprobar");
  const close = async () => { await act(async () => root.unmount()); host.remove(); await GlobalRegistrator.unregister(); };
  return { host, approve, close };
}

test("the Spanish draft review shows the server sentence beside the values and beside Aprobar", async () => {
  const page = await mount(SENTENCE);
  try {
    const footer = page.host.querySelector("[data-testid='receipt-review-footer']");
    const notes = page.host.querySelectorAll("[data-testid='dossier-review-note']");
    assert.equal(notes.length, 1);
    assert.equal(notes[0]?.textContent, SENTENCE);
    assert.ok(footer?.contains(notes[0] ?? null));
    assert.ok(page.approve);
    assert.equal(page.approve.disabled, false);
    assert.ok(footer?.contains(page.approve));
  } finally { await page.close(); }
});

test("a draft with no review note renders none, and Aprobar stays available", async () => {
  for (const reviewNote of [null, undefined] as const) {
    const page = await mount(reviewNote);
    try {
      assert.equal(page.host.querySelector("[data-testid='dossier-review-note']"), null);
      assert.ok(page.approve);
      assert.equal(page.approve.disabled, false);
    } finally { await page.close(); }
  }
});
