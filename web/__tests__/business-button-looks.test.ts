import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";

const ROOT = join(import.meta.dir, "..");

function sources(dir: string): string[] {
  return readdirSync(join(ROOT, dir), { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.(tsx?|css)$/.test(entry.name) ? [path] : [];
  });
}

const businessFiles = sources("components/business-app").filter((path) => !path.endsWith("business-ui.tsx"));

describe("Business button looks have one owner", () => {
  test("no Business file paints a black or white-on-dark fill: a CTA is primary, secondary, quiet or danger", () => {
    const offenders = businessFiles.filter((path) => /\bbg-black(?![/\w-])[^"`]*\btext-white\b|\bdark:bg-white dark:text-black\b/.test(readFileSync(join(ROOT, path), "utf8")));
    assert.deepEqual(offenders, []);
  });

  test("the one red is #9e2f39: the off-palette #a8434c appears nowhere in components or lib", () => {
    const offenders = [...sources("components"), ...sources("lib")].filter((path) => /#a8434c/i.test(readFileSync(join(ROOT, path), "utf8")));
    assert.deepEqual(offenders, []);
  });

  test("the classes live in business-ui.tsx: no second PRIMARY_BUTTON or SECONDARY_BUTTON copy", () => {
    const offenders = businessFiles.filter((path) => /\b(PRIMARY_BUTTON|SECONDARY_BUTTON|PILL_BUTTON)\b/.test(readFileSync(join(ROOT, path), "utf8")));
    assert.deepEqual(offenders, []);
  });
});
