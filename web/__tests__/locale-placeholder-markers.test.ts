import { describe, test } from "bun:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const localesRoot = join(import.meta.dir, "../public/locales");
const PLACEHOLDER_MARKER = /PENDIENTE COPY|COPY PENDING/i;

function stringsIn(node: unknown, path: string): [string, string][] {
  if (typeof node === "string") return [[path, node]];
  if (node && typeof node === "object") {
    return Object.entries(node).flatMap(([key, child]) => stringsIn(child, path ? `${path}.${key}` : key));
  }
  return [];
}

describe("locale copy ships approved words, never a marked placeholder", () => {
  const locales = readdirSync(localesRoot);
  test("reads the es-419 and en locales", () => {
    assert.ok(locales.includes("es-419") && locales.includes("en"), locales.join(", "));
  });
  for (const locale of locales) {
    test(`${locale} has no value marked as pending copy`, () => {
      const tree = JSON.parse(readFileSync(join(localesRoot, locale, "common.json"), "utf-8"));
      const offenders = stringsIn(tree, "").filter(([, value]) => PLACEHOLDER_MARKER.test(value)).map(([key]) => key);
      assert.deepEqual(offenders, []);
    });
  }
});
