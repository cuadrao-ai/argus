import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { EmailDeliveryDetail, EmailDeliveryRow, EmailReceivingAddress, useEmailWords } from "../components/business-app/BusinessEmailDeliveries";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { businessReceivingAddress, emailDeliveriesNeedRefresh, type BusinessEmailDelivery } from "../lib/business-email";

const delivery = (overrides: Partial<BusinessEmailDelivery> = {}): BusinessEmailDelivery => ({
  id: "email-1", state: "captured", received_at: "2026-10-12T14:00:00Z", updated_at: "2026-10-12T14:01:00Z",
  original_document_id: "rcpt-eml", retryable: false, subject: "Factura 0041", sender: "ventas@proveedor.example", sent_at: null, error_code: null,
  standing: null, saved_receipt_count: 1, no_receipt_reason: null,
  parts: [{ id: "1.2", filename: "IMG_2214.jpg", media_type: "image/jpeg", state: "captured", document_id: "rcpt-ferreteria", error_code: null }],
  ...overrides,
});

describe("received emails in the Inbox", () => {
  test("refresh is needed only while a delivery is still moving; the address shows only when enabled", () => {
    assert.equal(emailDeliveriesNeedRefresh([delivery()]), false);
    assert.equal(emailDeliveriesNeedRefresh([delivery({ state: "partial" })]), true);
    assert.equal(emailDeliveriesNeedRefresh([delivery({ state: "received" })]), true);
    assert.equal(businessReceivingAddress({ enabled: false, receiving_address: "x@y.test" }), null);
    assert.equal(businessReceivingAddress({ enabled: true, receiving_address: "x@y.test" }), "x@y.test");
  });

  test("a row shows subject, sender, state and attachment count in Spanish; the opened email shows the parts and the original", async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const row = renderToStaticMarkup(
      <I18nextProvider i18n={i18n}><ul><EmailDeliveryRow delivery={delivery()} onOpen={() => undefined} /></ul></I18nextProvider>,
    );
    assert.ok(row.includes("Factura 0041") && row.includes("ventas@proveedor.example"));
    assert.ok(row.includes("1 adjunto") && row.includes(">Guardado<"));
    assert.ok(!row.includes("IMG_2214.jpg"));
    const open = renderToStaticMarkup(
      <I18nextProvider i18n={i18n}><EmailDeliveryDetail delivery={delivery()} loadDetail={async () => ({ ...delivery(), text_body: "hola" })} openReceipt={() => undefined} retryDelivery={async () => ({ id: "email-1" })} /></I18nextProvider>,
    );
    assert.ok(open.includes("IMG_2214.jpg") && open.includes("Abrir recibo") && open.includes("Abrir el correo original"));
  });

  test("what an email saved and why it brought nothing are the server's, not read from its parts", async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish }, en: { translation: english } } });
    const detail = (over: Partial<BusinessEmailDelivery>) => renderToStaticMarkup(
      <I18nextProvider i18n={i18n}><EmailDeliveryDetail delivery={delivery(over)} loadDetail={async () => ({ ...delivery(over), text_body: null })} openReceipt={() => undefined} retryDelivery={async () => ({ id: "email-1" })} /></I18nextProvider>,
    );
    // One captured part on the wire, three saved by the server's count: the count wins.
    assert.ok(detail({ saved_receipt_count: 3, original_document_id: null }).includes("3 recibos llegaron a la Bandeja."));
    assert.ok(!detail({ saved_receipt_count: 0 }).includes("Abrir el correo original"), "with nothing saved the original is the receipt to open");
    function Reason({ item }: { item: BusinessEmailDelivery }) { return <p>{useEmailWords().noReceipt(item)}</p>; }
    const reason = (over: Partial<BusinessEmailDelivery>, lng = "es-419") => {
      void i18n.changeLanguage(lng);
      return renderToStaticMarkup(<I18nextProvider i18n={i18n}><Reason item={delivery({ standing: "no_receipt", state: "rejected", ...over })} /></I18nextProvider>);
    };
    // The parts and error code point elsewhere; the server's reason is the one said.
    const refused = { error_code: "email_parts_rejected", parts: [{ id: "1.2", filename: "a.zip", media_type: "application/zip", state: "rejected" as const, document_id: null, error_code: "unsupported_media_type" }] };
    assert.equal(reason({ ...refused, no_receipt_reason: "email_sender_blocked" }), "<p>Bloqueaste a este remitente</p>");
    assert.equal(reason({ no_receipt_reason: "email_no_attachment", parts: [] }), "<p>No traía adjunto</p>");
    assert.equal(reason({ no_receipt_reason: "email_no_attachment", parts: [] }, "en"), "<p>It had no attachment</p>");
    assert.equal(reason({ ...refused, no_receipt_reason: "a_code_without_copy" }), "<p>No trajo un recibo que pudiéramos guardar</p>");
    assert.equal(reason({ ...refused, no_receipt_reason: undefined }), "<p>No trajo un recibo que pudiéramos guardar</p>", "an older server's email gets the plain line, not a guess from its parts");
    void i18n.changeLanguage("es-419");
  });

  test("every reason code the server names has copy in Spanish and English, and no em dash", () => {
    const es = (spanish as { business: { email: { no_receipt_reason: Record<string, string> } } }).business.email.no_receipt_reason;
    const en = (english as { business: { email: { no_receipt_reason: Record<string, string> } } }).business.email.no_receipt_reason;
    assert.deepEqual(Object.keys(es).sort(), Object.keys(en).sort());
    for (const code of ["email_no_attachment", "email_parts_rejected", "unsupported_media_type", "email_sender_blocked", "email_route_unavailable", "other"]) assert.ok(es[code] && en[code], code);
    assert.ok([...Object.values(es), ...Object.values(en)].every((line) => !line.includes("\u2014")));
  });

  test("without an address the owner is offered one; with it the address and copy button show", async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const render = (intake: { enabled: boolean; receiving_address: string | null }) => renderToStaticMarkup(
      <I18nextProvider i18n={i18n}><EmailReceivingAddress intake={intake} onActivate={async () => undefined} /></I18nextProvider>,
    );
    assert.ok(render({ enabled: false, receiving_address: null }).includes("Obtener una dirección"));
    // The address may break after the @; the reader still sees one address.
    const ready = render({ enabled: true, receiving_address: "recibos-7f3a9c21@recibos.cuadrao.example" }).replace(/<wbr\/?>/g, "");
    assert.ok(ready.includes("recibos-7f3a9c21@recibos.cuadrao.example") && ready.includes("Copiar dirección"));
  });

  test("the sample data source answers every email call", async () => {
    const source = createFixtureBusinessDataSource();
    assert.equal((await source.emailIntake()).enabled, true);
    const items = await source.emailDeliveries();
    assert.equal(items.length, 5);
    assert.equal("text_body" in items[0], false);
    assert.equal((await source.emailDelivery("email-ferreteria")).text_body?.startsWith("Buenas tardes"), true);
    const inbox = await source.receipts("all");
    const original = inbox.find((item) => item.id === "rcpt-saved");
    assert.equal(original?.email_original, true);
    assert.deepEqual(original?.email_delivery_ids, ["email-ferreteria"]);
    assert.deepEqual(await source.retryEmailDelivery("email-boletin"), { id: "email-boletin" });
  });
});


for (const [locale, resources, label, resume] of [
  ["es-419", spanish, "En espera hasta mañana", "Se procesará automáticamente"],
  ["en", english, "Waiting until tomorrow", "Processing resumes automatically"],
] as const) {
  test(`a capped row explains automatic resume in ${locale} without an error or immediate retry`, async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: locale, resources: { [locale]: { translation: resources } } });
    const waiting = delivery({ state: "received", retryable: true, error_code: "email_daily_message_budget", parts: [], original_document_id: null,
      waiting: { reason: "daily_budget", retry_at: "2026-10-15T00:00:00Z" } });
    const render = (item: BusinessEmailDelivery) => renderToStaticMarkup(
      <I18nextProvider i18n={i18n}>
        <ul><EmailDeliveryRow delivery={item} onOpen={() => undefined} /></ul>
        <EmailDeliveryDetail delivery={item} loadDetail={async () => ({ ...item, text_body: null })} openReceipt={() => undefined} retryDelivery={async () => ({ id: item.id })} />
      </I18nextProvider>,
    );
    for (const code of ["email_daily_message_budget", "email_daily_byte_budget"]) {
      const item = { ...waiting, error_code: code };
      const html = render(item);
      assert.ok(html.includes(label) && html.includes(resume) && html.includes("UTC"));
      assert.ok(!html.includes(resources.business.email.error.other));
      assert.ok(!html.includes(resources.business.email.no_body));
      assert.ok(!html.includes(resources.business.email.retry));
      assert.equal(emailDeliveriesNeedRefresh([item]), false);
      assert.equal(emailDeliveriesNeedRefresh([item, delivery({ state: "processing" })]), true);
    }
    const legacy = render(delivery({ state: "partial", error_code: "email_capture_incomplete", retryable: true }));
    assert.ok(legacy.includes(resources.business.email.error.email_capture_incomplete));
    assert.ok(legacy.includes(resources.business.email.retry));
    assert.equal(emailDeliveriesNeedRefresh([delivery({ state: "rejected" })]), false);
    assert.equal(emailDeliveriesNeedRefresh([delivery({ state: "received" })]), true);
  });
}
