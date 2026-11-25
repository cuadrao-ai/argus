import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const REMOVED_KEYS = [
  "all_types",
  "annotations.choose_file",
  "annotations.empty_file",
  "annotations.keep_local_preview",
  "annotations.linked_unknown",
  "annotations.no_linked_attachment",
  "annotations.open_attachment",
  "annotations.open_linked_attachment",
  "annotations.preparing_preview",
  "annotations.preview_file",
  "annotations.record_actions",
  "column_type",
  "no_period_records",
  "overview.fiscal.description_purchase",
  "overview.fiscal.description_sale",
  "overview.itbis_helper_placeholder",
  "overview.total_helper_placeholder",
  "reset_period",
  "results.partial_meaning",
].map((key) => `business.transactions.layout.${key}`);
const REMOVED_NAMES = ["wide-canvas", "useWideCanvas", "OPEN_ROW_CLASS", "calendarPanel", "calendarBody", "calendarInputs", "monthNavigation", "viewsList", "totalAction", "breakdownList", "exclusions summary"];

const root = join(import.meta.dir, "..");
const sources = ["app", "components", "lib"].flatMap((folder) =>
  (readdirSync(join(root, folder), { recursive: true }) as string[])
    .filter((name) => /\.(tsx?|css)$/.test(name))
    .map((name) => join(root, folder, name)));
const has = (catalog: unknown, key: string) =>
  key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog) !== undefined;

describe("Registros old paths", () => {
  test("the words no Registros screen shows are in neither catalog", () => {
    for (const key of REMOVED_KEYS) {
      assert.equal(has(es419, key), false, `es-419 ${key}`);
      assert.equal(has(en, key), false, `en ${key}`);
    }
  });

  test("no source keeps the wide canvas, the old open-row class or the unused Registros styles", () => {
    const text = sources.map((path) => readFileSync(path, "utf8")).join("\n");
    for (const name of REMOVED_NAMES) assert.equal(new RegExp(`(?<![\\w-])${name}(?![\\w-])`).test(text), false, name);
  });
});
