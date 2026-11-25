import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const REMOVED_KEYS = [
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

  test("no source keeps the web's own fact standing, RNC check or currency list", () => {
    const text = sources.map((path) => readFileSync(path, "utf8")).join("\n");
    for (const name of REMOVED_NAMES) assert.equal(new RegExp(`(?<![\\w-])${name}(?![\\w-])`).test(text), false, name);
  });
});
