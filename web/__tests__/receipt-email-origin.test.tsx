import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { ReceiptRow } from "@/components/business-app/BusinessInboxPanel";
import ReceiptSourcePreview from "@/components/business-app/ReceiptSourcePreview";
import type { ReceiptSummary } from "@/lib/business-api";

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
  test("a receipt that arrived by email says Correo with a way to Correos recibidos, never Carga web", async () => {
    const html = await render({ ...base, channel: "email", email_delivery_ids: ["d1"] });
    assert.ok(html.includes('data-testid="receipt-source-channel"'));
    assert.ok(html.includes("Correo"));
    assert.ok(html.includes("Ver en Correos recibidos"));
    assert.ok(!html.includes("Carga web"));
    assert.ok(!html.includes('data-testid="receipt-email-times"'));
  });

  test("a file that arrived in two emails says so, by count", async () => {
    const html = await render({ ...base, channel: "email", email_delivery_ids: ["d1", "d2"] });
    assert.ok(html.includes("Este archivo llegó 2 veces por correo."));
  });

  test("in the Inbox list an email receipt carries the mail mark, as a WhatsApp one carries its own; a web upload carries none", async () => {
    const instance = await i18n("es-419");
    const row = (channel: ReceiptSummary["channel"]) => renderToStaticMarkup(
      createElement(I18nextProvider, { i18n: instance }, createElement(ReceiptRow, { receipt: { ...base, channel, status: "saved", attention: null, received_at: base.received_at, amount: null, currency: "DOP", merchant: "Ferretería La Esquina" } as unknown as ReceiptSummary, onOpen: () => undefined })),
    );
    const email = row("email");
    assert.ok(email.includes('data-testid="inbox-channel-email"') && email.includes('aria-label="Correo"'));
    assert.ok(row("whatsapp").includes('aria-label="WhatsApp"') && !row("whatsapp").includes("inbox-channel-email"));
    assert.ok(!row("web").includes("aria-label=\"Correo\"") && !row("web").includes('aria-label="WhatsApp"'));
  });

  test("WhatsApp and web keep their words; English follows", async () => {
    assert.ok((await render({ ...base, channel: "whatsapp" })).includes("WhatsApp"));
    assert.ok((await render({ ...base, channel: "web" })).includes("Carga web"));
    const en = await render({ ...base, channel: "email", email_delivery_ids: ["d1", "d2"] }, "en");
    assert.ok(en.includes(">Email") && en.includes("See in Received emails") && en.includes("This file arrived 2 times by email."));
  });
});
