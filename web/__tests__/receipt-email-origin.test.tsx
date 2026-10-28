import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import ReceiptSourcePreview from "@/components/business-app/ReceiptSourcePreview";

async function i18n(lng: "es-419" | "en") {
  const instance = i18next.createInstance();
  await instance.init({ lng, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return instance;
}

async function render(detail: Parameters<typeof ReceiptSourcePreview>[0]["detail"], lng: "es-419" | "en" = "es-419") {
  const instance = await i18n(lng);
  const value = { source: { receiptSource: () => new Promise<Blob>(() => undefined), mode: "live" }, openPanel: () => undefined } as unknown as BusinessContextValue;
  return renderToStaticMarkup(
    createElement(I18nextProvider, { i18n: instance }, createElement(BusinessContext.Provider, { value }, createElement(ReceiptSourcePreview, { detail }))),
  );
}

const base = { id: "rcpt-1", media_type: "application/pdf", filename: "recibo-prueba-ferreteria.pdf", received_at: "2026-10-13T17:14:00Z" };

describe("where a receipt arrived from, on its own page", () => {
  test("a receipt that arrived by email says Llegó por correo · Ver correo, never Carga web", async () => {
    const html = await render({ ...base, channel: "email", email_delivery_ids: ["d1"] });
    assert.ok(html.includes('data-testid="receipt-source-channel"'));
    assert.ok(html.includes("Llegó por correo"));
    assert.ok(html.includes('data-testid="receipt-see-email"') && html.includes(">Ver correo<"));
    assert.ok(!html.includes("Ver el primer correo"));
    assert.ok(!html.includes("Carga web"));
    assert.ok(!html.includes('data-testid="receipt-email-times"'));
  });

  test("a file that arrived in two emails says so, by count; one uploaded first on the web keeps Carga web and still points at the first email", async () => {
    const html = await render({ ...base, channel: "email", email_delivery_ids: ["d1", "d2"] });
    assert.ok(html.includes("Este archivo llegó 2 veces por correo."));
    const webFirst = await render({ ...base, channel: "web", email_delivery_ids: ["d1"] });
    assert.ok(webFirst.includes("Carga web") && !webFirst.includes("Llegó por correo"));
    const webThenTwice = await render({ ...base, channel: "web", email_delivery_ids: ["d1", "d2"] });
    assert.ok(webThenTwice.includes("Carga web") && webThenTwice.includes("Este archivo llegó 2 veces por correo.") && webThenTwice.includes("Ver el primer correo"));
  });

  test("WhatsApp and web keep their words; English follows", async () => {
    assert.ok((await render({ ...base, channel: "whatsapp" })).includes("WhatsApp"));
    assert.ok((await render({ ...base, channel: "web" })).includes("Carga web"));
    const en = await render({ ...base, channel: "email", email_delivery_ids: ["d1", "d2"] }, "en");
    assert.ok(en.includes("Arrived by email") && en.includes("See email") && en.includes("This file arrived 2 times by email."));
  });
});
