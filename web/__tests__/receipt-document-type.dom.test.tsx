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

async function mount(dossier: BusinessDossier) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const context = { source: {}, reload() {} } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><dl><ReceiptDocumentType dossier={dossier} /></dl></BusinessContext.Provider></I18nextProvider>));
  return { host, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

const fixtures = () => createDossierFixtures([{ id: "account-fixture", nickname: "Caja", type: "cash", currency: "DOP" }]);

const hints = { recibo: /Lo detectamos como compra/, venta: /La detectamos por el RNC/ } as const;
const records = { open: dossierFixtureIds.ready, approved: dossierFixtureIds.recordedThenMarked } as const;

for (const [state, id] of Object.entries(records)) {
  for (const [documentType, hint] of Object.entries(hints)) {
    test(`a type read from the document ${state === "open" ? "says so while the record is open" : "says nothing once the record is approved"} (${documentType})`, async () => {
      const source = fixtures();
      const view = await mount({ ...await source.dossier(id), document_type: documentType as keyof typeof hints, document_type_detected: true });
      try {
        if (state === "open") assert.match(view.host.textContent ?? "", hint);
        else assert.doesNotMatch(view.host.textContent ?? "", hint);
      } finally { await view.close(); }
    });
  }
}

test("a record the server marks fixed shows its type as text, with no control", async () => {
  const source = fixtures();
  const view = await mount({ ...await source.dossier(dossierFixtureIds.ready), document_type: "venta" as const, document_type_editable: false });
  try {
    assert.equal(view.host.querySelector("button, select"), null);
    assert.match(view.host.textContent ?? "", /Venta/);
  } finally { await view.close(); }
});
