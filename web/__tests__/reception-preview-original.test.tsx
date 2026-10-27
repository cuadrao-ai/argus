import assert from "node:assert/strict";
import { test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ReceiptSourcePreview from "@/components/business-app/ReceiptSourcePreview";

test("original preview preserves collapsed dossier default and supports immediate file viewing", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const value = { source: { mode: "live" }, openPanel: () => {} } as unknown as BusinessContextValue;
  const detail = { id: "original", media_type: "application/pdf", filename: "original.pdf", received_at: "2026-10-26T12:00:00Z", channel: "email" as const, email_delivery_ids: ["delivery", "repeat"] };
  const render = (initialExpanded?: boolean, showArrivalContext?: boolean) => renderToStaticMarkup(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><ReceiptSourcePreview detail={detail} initialExpanded={initialExpanded} showArrivalContext={showArrivalContext} /></BusinessContext.Provider></I18nextProvider>);
  assert.match(render(), /aria-expanded="false"/);
  assert.match(render(true), /aria-expanded="true"/);
  assert.match(render(true), /original.pdf/);
  assert.match(render(true), /data-testid="receipt-see-email"/);
  assert.match(render(), /Llegó por correo/);
  assert.match(render(), /Recibido/);
  const contextual = render(true, false);
  assert.doesNotMatch(contextual, /Llegó por correo/);
  assert.doesNotMatch(contextual, /Recibido/);
  assert.match(contextual, /data-testid="receipt-see-email"/);
  assert.match(contextual, /data-testid="receipt-email-times"/);
  assert.match(contextual, /original.pdf/);
});
