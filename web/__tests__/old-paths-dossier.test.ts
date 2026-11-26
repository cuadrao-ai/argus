import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const REMOVED_KEYS = [
  "business.activity_feed.no_record",
  "business.dossier.standing.empty",
  "business.dossier.title",
  "business.dossier.unknown",
  "business.email.no_filename",
  "business.history.channel_web",
  "business.inicio.attention.untitled",
  "business.receipt.untitled",
  "business.reception_preview.sent_by_unknown",
  "business.reception_preview.source_web",
  "business.transactions.layout.annotations.received_document",
  "business.transactions.unknown",
  "business.dgii.recorded_income",
  "business.dgii.recorded_refund",
  "business.dgii.rnc_check.invalid_length.approval_body",
  "business.dgii.rnc_check.invalid_length.approval_title",
  "business.dgii.rnc_check.missing.approval_body",
  "business.dgii.rnc_check.missing.approval_title",
];
const REMOVED_NAMES = ["receipt-currencies", "factStanding", "recordFactRows", "fiscalFactRows", "totalMismatch", "KIND_FIELDS", "useGrowingNoteBox", "rncStatus"];

const root = join(import.meta.dir, "..");
const sources = ["app", "components", "lib"].flatMap((folder) =>
  (readdirSync(join(root, folder), { recursive: true }) as string[])
    .filter((name) => /\.(tsx?|css)$/.test(name))
    .map((name) => join(root, folder, name)));
const has = (catalog: unknown, key: string) =>
  key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog) !== undefined;

describe("Dossier old paths", () => {
  test("the words no dossier shows are in neither catalog", () => {
    for (const key of REMOVED_KEYS) {
      assert.equal(has(es419, key), false, `es-419 ${key}`);
      assert.equal(has(en, key), false, `en ${key}`);
    }
  });

  test("the shared words have one key per concept in each Business catalog", () => {
    function keysWithValue(tree: object, word: string, prefix = "business"): string[] {
      return Object.entries(tree).flatMap(([key, value]) => {
        const path = `${prefix}.${key}`;
        if (typeof value !== "string") return keysWithValue(value, word, path);
        return value.toLowerCase() === word.toLowerCase() ? [path] : [];
      });
    }
    for (const [catalog, upload, empty, unnamed] of [
      [es419.business, "Carga web", "Sin dato", "Documento"],
      [en.business, "Web upload", "No value", "Document"],
    ] as const) {
      assert.equal(catalog.dossier.web, upload);
      assert.equal(catalog.dossier.row.no_data, empty);
      assert.equal(catalog.document_delete.unnamed, unnamed);
      assert.deepEqual(keysWithValue(catalog, upload), ["business.dossier.web"]);
      assert.deepEqual(keysWithValue(catalog, empty), ["business.dossier.row.no_data"]);
      // The same noun also labels a tab, a region and a matched document field.
      const fieldLabels = ["business.dossier.document.region", "business.dossier.tab.documento", "business.transactions.tray.matched"];
      assert.deepEqual(keysWithValue(catalog, unnamed).filter(key => !fieldLabels.includes(key)), ["business.document_delete.unnamed"]);
    }
  });

  test("no source keeps the web's own fact standing, RNC check or currency list", () => {
    const text = sources.map((path) => readFileSync(path, "utf8")).join("\n");
    for (const name of REMOVED_NAMES) assert.equal(new RegExp(`(?<![\\w-])${name}(?![\\w-])`).test(text), false, name);
  });
});
