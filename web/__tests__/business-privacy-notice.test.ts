import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { describe, test } from "bun:test";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import {
  BUSINESS_CONSENT_I18N_KEYS,
  canEnterBusiness,
  consentCopyVersion,
  privacyNoticePublished,
} from "../lib/business-privacy-notice";

const SPANISH = {
  title: "Antes de empezar",
  body: "Cuadrao guarda los recibos, facturas y datos que subes para leerlos, organizarlos y preparar tus reportes. Solo tú y las personas que invites a tu negocio pueden verlos. Puedes pedir que borremos tus datos cuando quieras.",
  opt_in: "Entiendo y acepto que Cuadrao use mis datos para esto.",
  continue: "Continuar",
  privacy_link: "Ver aviso de privacidad",
};

const ENGLISH = {
  title: "Before you start",
  body: "Cuadrao keeps the receipts, invoices and data you upload to read them, organize them and prepare your reports. Only you and the people you invite to your business can see them. You can ask us to delete your data whenever you want.",
  opt_in: "I understand and agree that Cuadrao uses my data for this.",
  continue: "Continue",
  privacy_link: "View privacy notice",
};

describe("business consent copy", () => {
  test("the screen says exactly the approved words, and nothing else", () => {
    assert.deepEqual(es.business.consent, SPANISH);
    assert.deepEqual(en.business.consent, ENGLISH);
    assert.deepEqual(BUSINESS_CONSENT_I18N_KEYS, Object.keys(SPANISH).map((key) => `business.consent.${key}`));
  });

  test("the wording version names what the screen shows, so any edit asks everyone again", async () => {
    const version = await consentCopyVersion();
    assert.match(version, /^[0-9a-f]{16}$/);
    assert.equal(await consentCopyVersion(), version);
    for (const catalog of [es, en]) {
      const before = catalog.business.consent.opt_in;
      catalog.business.consent.opt_in = `${before} `;
      try {
        assert.notEqual(await consentCopyVersion(), version);
      } finally {
        catalog.business.consent.opt_in = before;
      }
    }

    const link = es.business.consent.privacy_link;
    es.business.consent.privacy_link = `${link} `;
    try {
      assert.equal(await consentCopyVersion(), version, "a hidden link is not part of what was accepted");
    } finally {
      es.business.consent.privacy_link = link;
    }
    const business = es.business as Record<string, unknown>;
    business.privacy_notice = { title: "Aviso", close: "Cerrar", paragraphs: ["Texto."] };
    try {
      assert.notEqual(await consentCopyVersion(), version, "publishing the notice asks again");
    } finally {
      delete business.privacy_notice;
    }
  });

  test("no placeholder copy is left anywhere in the repository", () => {
    const root = path.resolve(import.meta.dir, "../..");
    const marker = ["[", "BORRADOR", "]"].join("");
    const english = ["[", "DRAFT", "]"].join("");
    for (const needle of [marker, english]) {
      let found = "";
      try {
        found = execFileSync("git", ["grep", "-n", "-F", needle], { cwd: root, encoding: "utf8" });
      } catch (error) {
        if ((error as { status?: number }).status !== 1) throw error;
      }
      assert.equal(found, "", `${needle} is still in the repository`);
    }
  });
});

describe("business privacy notice", () => {
  test("the notice is a draft until its text is in the catalog, and nothing links to a draft", () => {
    assert.equal(privacyNoticePublished("es-419"), false);
    assert.equal(privacyNoticePublished("en"), false);
    const business = es.business as Record<string, unknown>;
    business.privacy_notice = { title: "Aviso", close: "Cerrar", paragraphs: ["Texto."] };
    try {
      assert.equal(privacyNoticePublished("es-419"), true);
      assert.equal(privacyNoticePublished("en"), false);
    } finally {
      delete business.privacy_notice;
    }
  });

  test("a client Business stays closed without acceptance", () => {
    assert.equal(canEnterBusiness(false, null), true);
    assert.equal(canEnterBusiness(false, "44444444-4444-4444-8444-444444444444"), false);
    assert.equal(canEnterBusiness(true, "44444444-4444-4444-8444-444444444444"), true);
  });
});
