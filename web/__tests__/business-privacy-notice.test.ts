import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { describe, test } from "bun:test";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import {
  BUSINESS_CONSENT_WORDING_KEYS,
  canEnterBusiness,
  consentCopyVersion,
  sha256Hex,
} from "../lib/business-privacy-notice";

/** The version every acceptance saved so far carries; the same words must keep it. */
const TODAYS_VERSION = "75cfe4cb3fa507c5";

const SPANISH = {
  title: "Antes de empezar",
  body: "Cuadrao guarda los recibos, facturas y datos que subes para leerlos, organizarlos y preparar tus reportes. Solo tú y las personas que invites a tu negocio pueden verlos. Puedes pedir que borremos tus datos cuando quieras.",
  opt_in: "Entiendo y acepto que Cuadrao use mis datos para esto.",
  continue: "Continuar",
  privacy_link: "Ver aviso de privacidad",
  one_time: "Te lo pedimos una sola vez, para los datos de tu negocio.",
  save_failed: "No pudimos guardar tu aceptación. No cambió nada.",
  reference: "Ref. {{reference}}",
};

const ENGLISH = {
  title: "Before you start",
  body: "Cuadrao keeps the receipts, invoices and data you upload to read them, organize them and prepare your reports. Only you and the people you invite to your business can see them. You can ask us to delete your data whenever you want.",
  opt_in: "I understand and agree that Cuadrao uses my data for this.",
  continue: "Continue",
  privacy_link: "View privacy notice",
  one_time: "We ask this once, for your business's data.",
  save_failed: "We couldn't save your acceptance. Nothing changed.",
  reference: "Ref. {{reference}}",
};

type ConsentBlock = Record<string, string>;
const blocks = [es.business.consent, en.business.consent] as ConsentBlock[];

function versionWith(block: ConsentBlock, key: string): string {
  const before = block[key];
  block[key] = `${before} `;
  try {
    return consentCopyVersion();
  } finally {
    block[key] = before;
  }
}

describe("business consent copy", () => {
  test("the screen says exactly the approved words, and nothing else", () => {
    assert.deepEqual(es.business.consent, SPANISH);
    assert.deepEqual(en.business.consent, ENGLISH);
  });

  test("today's words keep today's version, so nobody who accepted is asked again", () => {
    assert.equal(consentCopyVersion(), TODAYS_VERSION);
  });

  test("any edit to the accepted words, in either language, is a new version", () => {
    const wording = BUSINESS_CONSENT_WORDING_KEYS.map((key) => key.replace("business.consent.", ""));
    assert.deepEqual(wording, ["title", "body", "opt_in", "continue"]);
    for (const block of blocks) {
      for (const key of wording) assert.notEqual(versionWith(block, key), TODAYS_VERSION, `${key} is accepted wording`);
      for (const key of Object.keys(block).filter((name) => !wording.includes(name))) {
        assert.equal(versionWith(block, key), TODAYS_VERSION, `${key} explains the screen and is not accepted`);
      }
    }
  });

  test("the version needs no secure context: the LAN dev link has no crypto.subtle", () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, "crypto");
    Object.defineProperty(globalThis, "crypto", { configurable: true, value: { getRandomValues: crypto.getRandomValues.bind(crypto) } });
    try {
      assert.equal(globalThis.crypto.subtle, undefined);
      assert.equal(consentCopyVersion(), TODAYS_VERSION);
    } finally {
      if (original) Object.defineProperty(globalThis, "crypto", original);
    }
  });

  test("sha256Hex is SHA-256 of the UTF-8 text across block boundaries", () => {
    for (let length = 0; length < 260; length += 1) {
      const text = `${randomBytes(length).toString("base64").slice(0, length)}ñé😀`;
      assert.equal(sha256Hex(text), createHash("sha256").update(text, "utf8").digest("hex"), `length ${length}`);
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

describe("business consent entry", () => {
  test("a client Business stays closed without acceptance", () => {
    assert.equal(canEnterBusiness(false, null), true);
    assert.equal(canEnterBusiness(false, "44444444-4444-4444-8444-444444444444"), false);
    assert.equal(canEnterBusiness(true, "44444444-4444-4444-8444-444444444444"), true);
  });
});
