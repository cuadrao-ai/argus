import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import ReceiptEcfChecks from "../components/business-app/ReceiptEcfChecks";
import { createDossierFixtures, dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import type { EcfVerification } from "../lib/business-dossier";

async function render(verification: EcfVerification | null, lng: "es-419" | "en") {
  const i18n = i18next.createInstance();
  await i18n.init({ lng, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <ReceiptEcfChecks verification={verification} />
    </I18nextProvider>,
  );
}

describe("the electronic invoice verification card", () => {
  test("says what the file proved in Spanish, marks a failed line for review and names what was not checked", async () => {
    const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
    const dossier = await fixture.dossier(dossierFixtureIds.fiscal);
    const html = await render(dossier.ecf_checks ?? null, "es-419");
    assert.ok(html.includes("Verificación de la factura electrónica"));
    assert.ok(html.includes("e-CF E310000000777 · tipo 31, crédito fiscal"));
    assert.ok(html.includes("Contenido sin cambios desde la firma"));
    assert.ok(!html.includes("firma verificada"));
    assert.ok(html.includes("Revisar: la lectura difiere del XML en ITBIS"));
    assert.ok(html.includes("Certificado vigente al firmar (09-10-2026 14:05:00); revocación no comprobada"));
    assert.ok(html.includes("Emisor del certificado no comprobado: Autoridad Ficticia de Prueba"));
    assert.ok(html.includes("Aceptación por la DGII no consultada"));
    assert.ok(html.includes("Código de seguridad esperado: AbC123"));
    assert.ok(html.includes("Nada aquí confirma que la DGII aceptó la factura"));
    assert.equal((html.match(/data-state="verified"/g) ?? []).length, 4);
    assert.equal((html.match(/data-state="failed"/g) ?? []).length, 1);
    assert.equal((html.match(/data-state="not_checked"/g) ?? []).length, 3);
  });

  test("English follows the same words", async () => {
    const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
    const dossier = await fixture.dossier(dossierFixtureIds.fiscal);
    const html = await render(dossier.ecf_checks ?? null, "en");
    assert.ok(html.includes("Electronic invoice verification"));
    assert.ok(html.includes("Content unchanged since it was signed"));
    assert.ok(html.includes("Review: the read differs from the XML in ITBIS"));
    assert.ok(html.includes("DGII acceptance not looked up"));
  });

  test("an unsigned file, a tampered one and a certificate out of its window read as their reasons", async () => {
    const base: EcfVerification = { encf: "E320000009999", tipo_ecf: "32", checked_at: "2026-10-12T20:00:00Z", checks: [] };
    const unsigned = await render({ ...base, checks: [{ name: "signature_integrity", state: "not_checked", code: "no_signature", detail: {} }, { name: "security_code", state: "not_checked", code: "no_signature", detail: {} }] }, "es-419");
    assert.ok(unsigned.includes("Firma no comprobada: el archivo no trae firma"));
    assert.ok(unsigned.includes("Código de seguridad no disponible"));
    assert.ok(unsigned.includes("e-CF E320000009999 · tipo 32, consumo"));
    const tampered = await render({ ...base, checks: [{ name: "signature_integrity", state: "failed", code: "digest_mismatch", detail: {} }, { name: "totals_arithmetic", state: "failed", code: "totals_mismatch", detail: { monto_total: "100.00", sum_of_parts: "99.00" } }, { name: "certificate_validity", state: "failed", code: "certificate_not_valid_at_signature", detail: { signed_at: "01-01-2026 10:00:00" } }, { name: "subject_rnc", state: "failed", code: "subject_rnc_differs", detail: { subject_serial: "101000000" } }] }, "es-419");
    assert.ok(tampered.includes("Revisar: el contenido cambió después de la firma"));
    assert.ok(tampered.includes("Revisar: los totales no cuadran (total 100.00, suma 99.00)"));
    assert.ok(tampered.includes("Revisar: el certificado no estaba vigente al firmar (01-01-2026 10:00:00)"));
    assert.ok(tampered.includes("Revisar: el certificado no pertenece al RNC emisor (101000000)"));
  });

  test("renders nothing for a record that came from any other source", async () => {
    assert.equal(await render(null, "es-419"), "");
  });
});
