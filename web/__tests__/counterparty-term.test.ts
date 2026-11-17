import assert from "node:assert/strict";
import { test } from "bun:test";
import i18next from "i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { counterpartyTerm, documentFamily, factLabel } from "@/lib/counterparty-term";

const TERM = "business.terms.counterparty";
const LOCALES = { "es-419": spanish, en: english } as const;
const WORDS = { "es-419": { purchase: "Emisor", sale: "Cliente", neither: "Contraparte" }, en: { purchase: "Supplier", sale: "Customer", neither: "Counterparty" } } as const;

function* leaves(node: unknown, path: string): Generator<[string, string]> {
  if (typeof node === "string") yield [path, node];
  else if (node && typeof node === "object") for (const [key, value] of Object.entries(node)) yield* leaves(value, path ? `${path}.${key}` : key);
}

for (const language of ["es-419", "en"] as const) {
  test(`the word ${WORDS[language].neither} lives only in ${TERM} in ${language}`, () => {
    const owners = [...leaves(LOCALES[language], "")].filter(([, value]) => value.split(/[^\p{L}]+/u).some((word) => word.toLowerCase() === WORDS[language].neither.toLowerCase())).map(([path]) => path);
    assert.deepEqual(owners, [TERM]);
  });

  test(`a purchase names Emisor, a sale Cliente, and money with no document the base word in ${language}`, async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: language, resources: { [language]: { translation: LOCALES[language] } } });
    assert.equal(counterpartyTerm(i18n.t, documentFamily("recibo")), WORDS[language].purchase);
    assert.equal(counterpartyTerm(i18n.t, documentFamily("venta")), WORDS[language].sale);
    assert.equal(counterpartyTerm(i18n.t, documentFamily(undefined)), WORDS[language].neither);
    assert.equal(factLabel(i18n.t, "counterparty", "sale"), WORDS[language].sale);
    assert.equal(factLabel(i18n.t, "occurred_on", "sale"), i18n.t("business.dossier.field.occurred_on"));
  });
}
