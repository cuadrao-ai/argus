import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import ReceiptEcfChecks, { ecfRows } from "../components/business-app/ReceiptEcfChecks";
import { createDossierFixtures, dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import type { EcfVerification } from "../lib/business-dossier";

async function i18n(lng: "es-419" | "en") {
  const instance = i18next.createInstance();
  await instance.init({ lng, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return instance;
}

async function render(verification: EcfVerification | null | undefined, lng: "es-419" | "en") {
  const instance = await i18n(lng);
  return renderToStaticMarkup(
    <I18nextProvider i18n={instance}>
      <ReceiptEcfChecks verification={verification} />
    </I18nextProvider>,
  );
}

async function rows(verification: EcfVerification, lng: "es-419" | "en" = "es-419") {
  const instance = await i18n(lng);
  return ecfRows(verification, instance.t.bind(instance) as never);
}

const BASE: EcfVerification = { encf: "E320000009999", tipo_ecf: "32", checked_at: new Date(Date.now() - 3 * 60_000).toISOString(), checks: [] };

describe("the electronic invoice verification card", () => {
  test("five rows in Spanish: signature, totals, read, certificate as two facts, DGII; captions by state; checked N minutes ago; no state pill", async () => {
    const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
    const dossier = await fixture.dossier(dossierFixtureIds.fiscal);
    const verification = { ...dossier.ecf_checks!, checked_at: BASE.checked_at };
    const html = await render(verification, "es-419");
    assert.ok(html.includes("Verificación de la factura electrónica"));
    assert.ok(html.includes("e-CF E310000000777 · tipo 31, crédito fiscal"));
    assert.equal((html.match(/<li /g) ?? []).length, 5);
    assert.ok(html.includes("Contenido sin cambios desde la firma"));
    assert.ok(!html.includes("firma verificada") && !html.includes("al firmar"));
    assert.ok(html.includes("Revisar: la lectura difiere del XML en ITBIS"));
    assert.ok(html.includes("Vigente en la fecha que declara el documento (09-10-2026 14:05:00); Vigente hoy. Revocación no comprobada."));
    assert.ok(html.includes("Emisor del certificado no comprobado (Autoridad Ficticia de Prueba)."));
    assert.ok(html.includes("El certificado nombra el RNC emisor; eso no prueba su identidad."));
    assert.ok(html.includes("Aceptación por la DGII no consultada. Código de seguridad esperado: AbC123."));
    assert.ok(html.includes("comprobado hace 3 minutos"));
    assert.ok(!html.includes("Comprobado</span>") && !html.includes("Sin comprobar</span>"));
    assert.ok(html.includes("text-[var(--rui-color-teal)]") && html.includes("text-[var(--rui-color-danger)]"));
    const states = [...html.matchAll(/data-row="([a-z]+)" data-state="([a-z_]+)"/g)].map((m) => [m[1], m[2]]);
    assert.deepEqual(states, [["signature", "verified"], ["totals", "verified"], ["read", "failed"], ["certificate", "verified"], ["dgii", "not_checked"]]);
  });

  test("English follows the same words", async () => {
    const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
    const dossier = await fixture.dossier(dossierFixtureIds.fiscal);
    const html = await render(dossier.ecf_checks, "en");
    assert.ok(html.includes("Electronic invoice verification"));
    assert.ok(html.includes("Content unchanged since it was signed"));
    assert.ok(html.includes("Valid on the date the document declares (09-10-2026 14:05:00); Valid today. Revocation not checked."));
    assert.ok(html.includes("RNC; that does not prove its identity."));
    assert.ok(html.includes("DGII acceptance not looked up."));
  });

  test("without an XML there is no card; an unsigned file and an unsupported transform read as their reasons", async () => {
    assert.equal(await render(null, "es-419"), "");
    assert.equal(await render(undefined, "es-419"), "");
    const unsigned = await rows({ ...BASE, checks: [{ name: "signature_integrity", state: "not_checked", code: "no_signature", detail: {} }, { name: "security_code", state: "not_checked", code: "no_signature", detail: {} }] });
    assert.equal(unsigned[0].caption, "Firma no comprobada: el archivo no trae firma");
    assert.equal(unsigned[4].caption, "Aceptación por la DGII no consultada. Código de seguridad no disponible.");
    const unsupported = await rows({ ...BASE, checks: [{ name: "signature_integrity", state: "not_checked", code: "unsupported_transform", detail: { transforms: "x" } }] });
    assert.equal(unsupported[0].caption, "Firma no comprobada: forma de firma no admitida");
    assert.equal(unsupported[0].state, "not_checked");
  });

  test("a tampered file, bad totals, a certificate outside its window and a foreign RNC read as review lines", async () => {
    const [signature, totals, , certificate] = await rows({ ...BASE, checks: [
      { name: "signature_integrity", state: "failed", code: "digest_mismatch", detail: {} },
      { name: "totals_arithmetic", state: "failed", code: "totals_mismatch", detail: { monto_total: "100.00", sum_of_parts: "99.00" } },
      { name: "certificate_validity", state: "failed", code: "certificate_not_valid_at_signature", detail: { signed_at: "01-01-2026 10:00:00", at_signature: "expired", today: "expired" } },
      { name: "subject_rnc", state: "failed", code: "subject_rnc_differs", detail: { subject_serial: "101000000" } },
    ] });
    assert.equal(signature.caption, "Revisar: el contenido cambió después de la firma");
    assert.equal(totals.caption, "Revisar: los totales no cuadran (total 100.00, suma 99.00)");
    assert.ok(certificate.caption.startsWith("Vencido en la fecha que declara el documento (01-01-2026 10:00:00); Vencido hoy."));
    assert.ok(certificate.caption.endsWith("Revisar: el certificado no nombra el RNC emisor (101000000)."));
    assert.equal(certificate.state, "failed");
  });

  test("missing checks, missing detail and an unknown state never crash and read as not checked", async () => {
    const odd = await rows({ encf: null, tipo_ecf: null, checked_at: "", checks: [
      { name: "signature_integrity", state: "weird" as never, code: null, detail: undefined as never },
      { name: "certificate_validity", state: "verified", code: null, detail: undefined as never },
      { name: "made_up" as never, state: "verified", code: null, detail: {} },
      null as never,
    ] });
    assert.equal(odd.length, 5);
    assert.deepEqual(odd.map((row) => row.state), ["not_checked", "not_checked", "not_checked", "verified", "not_checked"]);
    assert.equal(odd[0].caption, "Firma no comprobada: no se pudo leer la firma");
    assert.equal(odd[1].caption, "Totales no comprobados");
    assert.ok(odd[3].caption.startsWith("Sin fecha declarada en la fecha que declara el documento; Sin fecha declarada hoy."));
    const html = await render({ ...BASE, checked_at: "not a date", checks: [] }, "es-419");
    assert.ok(html.includes("Sin fecha") === false && html.includes("Firma no comprobada"));
    assert.ok(!html.includes("comprobado hace"));
  });
});
