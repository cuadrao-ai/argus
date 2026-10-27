import assert from "node:assert/strict";
import { test } from "bun:test";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

/** Words that read the same in both languages: DGII names, document names, and plain words English shares. */
const SHARED_CONTEXTS = new Map([
  ["business.invoicing_preview.email_cc_short", "Cc"],
  ["business.invoicing_preview.document_customer_ced", "CED: {{id}}"],
  ["business.invoicing_preview.document_customer_rnc", "RNC: {{id}}"],
  ["business.invoicing_preview.subtotal", "Subtotal"],
  ["business.reception_preview.source_whatsapp", "WhatsApp"],
  ["business.transactions.layout.results.personal_one", "{{count}} personal"],
  ["business.notifications.times.recent", "5 min"],
]);
const SAME_IN_BOTH = new Set(["RNC", "NCF", "e-NCF", "e-CF", "ITBIS", "DGII", "Cédula", "Total", "total", "Personal", "Normal", "No", "Ref."]);

type Tree = { [key: string]: string | Tree };

function leaves(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string" ? [[path, value] as [string, string]] : leaves(value, path);
  });
}

test("no English Business text is still the Spanish source, apart from names both languages share", () => {
  const es = new Map(leaves((spanish as unknown as { business: Tree }).business, "business"));
  const untranslated = leaves((english as unknown as { business: Tree }).business, "business")
    .filter(([key, value]) => {
      const words = value.replace(/\{\{\w+\}\}/g, "").trim();
      return es.get(key) === value && /\p{L}{2,}/u.test(words) && !SAME_IN_BOTH.has(words) && SHARED_CONTEXTS.get(key) !== value;
    })
    .map(([key]) => key);
  assert.deepEqual(untranslated, []);
});
