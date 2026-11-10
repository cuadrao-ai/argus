import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];
const original = { fetch: globalThis.fetch, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };

beforeEach(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterEach(async () => {
  globalThis.fetch = original.fetch;
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
  await GlobalRegistrator.unregister();
});

test("a denied note keeps the typed text and says the current access does not allow it", async () => {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.ready);
  const captures: string[] = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith(`/business/drafts/${dossier.draft_id}/dossier`)) return Response.json(dossier);
    if (path.endsWith("/business/captures") && init?.method === "POST") {
      captures.push(String(init.body));
      return Response.json({ code: "permission_denied" }, { status: 403 });
    }
    return Response.json({ code: "not_found" }, { status: 404 });
  };
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  const context = {
    source: liveBusinessDataSource,
    reload: () => undefined,
    records: { inbox: [], notes: [], notesError: false, notesTruncated: false, error: false, workspace: null },
    openPanel: () => undefined,
    panel: { kind: "draft", draftId: dossier.draft_id },
    revision: 0,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const settle = async () => { for (let turn = 0; turn < 5; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  const button = (label: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent === label);
  try {
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Review draftId={dossier.draft_id} /></BusinessContext.Provider></I18nextProvider>); });
    await settle();
    const append = button("Agregar una nota a este registro");
    assert.ok(append, "the member can add a note");
    await act(async () => append.click());
    const typed = "Compré pintura para el taller";
    const field = document.body.querySelector("textarea");
    assert.ok(field, "the note dialog is open");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, typed);
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const save = button("Guardar nota");
    assert.ok(save, "the note can be saved");
    await act(async () => save.click());
    await settle();

    assert.equal(captures.length, 1, "the append reached the server once");
    assert.equal(document.body.querySelector("textarea")?.value, typed, "the typed text survives the denial");
    const alerts = [...document.body.querySelectorAll('[role="alert"]')].map((item) => item.textContent ?? "");
    assert.ok(alerts.some((text) => text.includes("Tu acceso actual no permite guardar esta nota. Conservamos tu texto.")), `the access alert shows: ${JSON.stringify(alerts)}`);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
