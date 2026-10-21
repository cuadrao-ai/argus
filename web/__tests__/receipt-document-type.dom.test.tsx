import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ReceiptDocumentType from "@/components/business-app/ReceiptDocumentType";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import type { BusinessDossier } from "@/lib/business-dossier";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(dossier: BusinessDossier, setDocumentType: (id: string, version: number, type: "recibo" | "venta", key: string) => Promise<BusinessDossier>) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const changed: BusinessDossier[] = [];
  const context = { source: { setDocumentType }, reload() {} } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ReceiptDocumentType dossier={dossier} onChanged={(next) => changed.push(next)} /></BusinessContext.Provider></I18nextProvider>));
  const segment = (type: string) => host.querySelector<HTMLButtonElement>(`[data-segment="${type}"]`);
  return { host, changed, segment, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

const fixtures = () => createDossierFixtures([{ id: "account-fixture", nickname: "Caja", type: "cash", currency: "DOP" }]);

test("an open record retypes a detected purchase as a sale through the review", async () => {
  const source = fixtures();
  const dossier = { ...await source.dossier(dossierFixtureIds.ready), document_type_detected: true };
  assert.equal(dossier.document_type_editable, true);
  const sent: unknown[][] = [];
  const view = await mount(dossier, async (...args) => { sent.push(args); return source.setDocumentType(args[0], args[1], args[2], args[3]); });
  try {
    assert.match(view.host.textContent ?? "", /Lo detectamos como compra/);
    assert.equal(view.segment("recibo")?.getAttribute("aria-checked"), "true");
    await act(async () => { view.segment("venta")!.click(); });
    assert.deepEqual(sent.map((args) => args.slice(0, 3)), [[dossier.draft_id, dossier.version, "venta"]]);
    assert.equal(view.changed.at(-1)?.document_type, "venta");
    assert.equal(view.changed.at(-1)?.document_type_detected, undefined);
  } finally { await view.close(); }
});

test("a record the server marks fixed shows its type as text, with no control", async () => {
  const source = fixtures();
  const dossier = { ...await source.dossier(dossierFixtureIds.ready), document_type: "venta" as const, document_type_editable: false };
  const view = await mount(dossier, async () => { throw new Error("a fixed type never sends"); });
  try {
    assert.equal(view.segment("venta"), null);
    assert.match(view.host.textContent ?? "", /Venta/);
  } finally { await view.close(); }
});

test("a refusal after approval says the type is fixed and keeps the shown type", async () => {
  const source = fixtures();
  const dossier = await source.dossier(dossierFixtureIds.ready);
  const view = await mount(dossier, async () => { throw Object.assign(new Error("locked"), { status: 422, code: "document_type_locked" }); });
  try {
    await act(async () => { view.segment("venta")!.click(); });
    assert.match(view.host.querySelector('[role="alert"]')?.textContent ?? "", /ya está aprobado/);
    assert.equal(view.segment("recibo")?.getAttribute("aria-checked"), "true");
    assert.equal(view.changed.length, 0);
  } finally { await view.close(); }
});
