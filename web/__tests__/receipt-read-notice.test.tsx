import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import ReceiptReadNotice from "../components/business-app/ReceiptReadNotice";
import type { ReceiptStatus } from "../lib/business-api";

async function render(status: ReceiptStatus, readPending: boolean, lng: "es-419" | "en", can: { enterable: boolean; preparable: boolean } = { enterable: true, preparable: true }) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <ReceiptReadNotice status={status} readPending={readPending} enterable={can.enterable} preparable={can.preparable} />
    </I18nextProvider>,
  );
}

describe("what a saved receipt says is happening to it", () => {
  test("a pending read says the receipt is being read", async () => {
    const es = await render("queued", true, "es-419");
    assert.ok(es.includes("Leyendo tu recibo. Puedes salir de esta página; el resultado te esperará en la bandeja."));
    assert.ok(es.includes('role="status"'));
    const en = await render("preparing", true, "en");
    assert.ok(en.includes("Reading your receipt. You can leave this page; the result will wait in your inbox."));
  });

  test("a saved receipt that nothing will read says so and leaves the person to fill it in", async () => {
    const es = await render("saved", false, "es-419");
    assert.ok(es.includes("Guardado, sin leer. Pulsa «Preparar con IA» para que Cuadrao lo lea, o complétalo tú."));
    assert.ok(!es.includes("Leyendo tu recibo"));
    const en = await render("saved", false, "en");
    assert.ok(en.includes("Saved, unread. Press “Prepare with AI” so Cuadrao reads it, or fill it in yourself."));
  });

  test("the saved line names only what the person can do now", async () => {
    const byHand = await render("saved", false, "es-419", { enterable: true, preparable: false });
    assert.ok(byHand.includes("Guardado, sin leer. Complétalo tú."));
    assert.ok(!byHand.includes("lectura con IA"));
    const aiOnly = await render("saved", false, "es-419", { enterable: false, preparable: true });
    assert.ok(aiOnly.includes("Guardado, sin leer. Pulsa «Preparar con IA» para que Cuadrao lo lea."));
    assert.ok(!aiOnly.includes("a mano"));
    const neither = await render("saved", false, "es-419", { enterable: false, preparable: false });
    assert.ok(neither.includes("Guardado, sin leer."));
    assert.ok(!neither.includes("a mano") && !neither.includes("lectura con IA"));
    const en = await render("saved", false, "en", { enterable: false, preparable: true });
    assert.ok(en.includes("Saved, unread. Press “Prepare with AI” so Cuadrao reads it."));
  });

  test("any other state says nothing", async () => {
    assert.equal(await render("review_ready", false, "es-419"), "");
    assert.equal(await render("needs_attention", false, "en"), "");
  });
});
