import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ReceiptDocumentType from "@/components/business-app/ReceiptDocumentType";
import ReceiptEditRow, { type RowShown } from "@/components/business-app/ReceiptEditRow";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import type { BusinessDossier } from "@/lib/business-dossier";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(dossier: BusinessDossier, row?: (shown: RowShown) => ReactNode) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const context = { source: {}, reload() {} } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><dl><ReceiptDocumentType dossier={dossier} row={row} /></dl></BusinessContext.Provider></I18nextProvider>));
  return { host, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

const fixtures = () => createDossierFixtures([{ id: "account-fixture", nickname: "Caja", type: "cash", currency: "DOP" }]);

const records = { open: dossierFixtureIds.ready, approved: dossierFixtureIds.recordedThenMarked } as const;
const picker = (shown: RowShown) => <ReceiptEditRow {...shown} open={false} saving={false} locked={false} onOpen={() => undefined} onSave={() => undefined} onCancel={() => undefined}>{null}</ReceiptEditRow>;

for (const [state, id] of Object.entries(records)) {
  test(`a purchase read from the document shows Compra with no 'Lo detectamos como compra' line (${state})`, async () => {
    const view = await mount({ ...await fixtures().dossier(id), document_type: "recibo", document_type_detected: true });
    try {
      assert.equal(view.host.querySelector('[data-testid="receipt-document-type"] dd')?.textContent, "Compra");
      assert.doesNotMatch(view.host.textContent ?? "", /Lo detectamos|Cámbialo si es una venta/);
    } finally { await view.close(); }
  });

  test(`a sale read from the business's RNC ${state === "open" ? "asks for the client's RNC while the record is open" : "says nothing once the record is approved"}`, async () => {
    const view = await mount({ ...await fixtures().dossier(id), document_type: "venta", document_type_detected: true });
    try {
      const asked = /La detectamos por el RNC de tu negocio\. Completa el RNC del cliente\./;
      if (state === "open") assert.match(view.host.textContent ?? "", asked);
      else assert.doesNotMatch(view.host.textContent ?? "", asked);
    } finally { await view.close(); }
  });
}

test("the Compra picker on an open draft keeps its edit control, with no line under it", async () => {
  const view = await mount({ ...await fixtures().dossier(dossierFixtureIds.ready), document_type: "recibo", document_type_detected: true }, picker);
  try {
    const row = view.host.querySelector('[data-testid="receipt-document-type"]')!;
    assert.equal(row.querySelector("dt")?.textContent, "Tipo");
    assert.equal(row.querySelector('button[aria-label="Editar detalles · Tipo"]')?.textContent, "Compra");
    assert.equal(row.querySelector("dd p")?.textContent, undefined);
  } finally { await view.close(); }
});

test("a record the server marks fixed shows its type as text, with no control", async () => {
  const source = fixtures();
  const view = await mount({ ...await source.dossier(dossierFixtureIds.ready), document_type: "venta" as const, document_type_editable: false });
  try {
    assert.equal(view.host.querySelector("button, select"), null);
    assert.match(view.host.textContent ?? "", /Venta/);
  } finally { await view.close(); }
});
