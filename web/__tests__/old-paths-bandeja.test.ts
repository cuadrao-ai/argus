import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const REMOVED_KEYS = [
  "business.empty.all_clear_body",
  "business.empty.all_clear_title",
  "business.empty.inbox_body",
  "business.empty.inbox_error",
  "business.empty.inbox_title",
  "business.empty.month_body",
  "business.empty.see_all_periods",
  "business.intake.camera",
  "business.intake.formats_short",
  "business.intake.paste_hint",
];
const REMOVED_NAMES = ["foundation/PrimaryUpload", "readClipboardFile", "documentIcon"];

const root = join(import.meta.dir, "..");
const sources = ["app", "components", "lib"].flatMap((folder) =>
  (readdirSync(join(root, folder), { recursive: true }) as string[])
    .filter((name) => /\.(tsx?|css)$/.test(name))
    .map((name) => join(root, folder, name)));
const has = (catalog: unknown, key: string) =>
  key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalog) !== undefined;

describe("Bandeja old paths", () => {
  test("the words no Bandeja screen shows are in neither catalog", () => {
    for (const key of REMOVED_KEYS) {
      assert.equal(has(es419, key), false, `es-419 ${key}`);
      assert.equal(has(en, key), false, `en ${key}`);
    }
  });

  test("the top bar's Agregar is the one upload button the app defines", () => {
    const text = sources.map((path) => readFileSync(path, "utf8")).join("\n");
    for (const name of REMOVED_NAMES) assert.equal(text.includes(name), false, name);
    assert.ok(readFileSync(join(root, "components/business-app/BusinessAddMenu.tsx"), "utf8").includes('data-testid="business-primary-upload"'));
  });
});
