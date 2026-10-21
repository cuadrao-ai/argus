import { describe, test } from "bun:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const localesRoot = join(import.meta.dir, "../public/locales");

function stringsIn(node: unknown, path: string): [string, string][] {
  if (typeof node === "string") return [[path, node]];
  if (node && typeof node === "object") {
    return Object.entries(node).flatMap(([key, child]) => stringsIn(child, path ? `${path}.${key}` : key));
  }
  return [];
}

describe("locale copy names the product Cuadrao", () => {
  for (const locale of readdirSync(localesRoot)) {
    test(`${locale} has no value that says Argus`, () => {
      const tree = JSON.parse(readFileSync(join(localesRoot, locale, "common.json"), "utf-8"));
      const offenders = stringsIn(tree, "").filter(([, value]) => /argus/i.test(value)).map(([key]) => key);
      assert.deepEqual(offenders, []);
    });
  }
});
