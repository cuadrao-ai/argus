import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "bun:test";

const root = join(import.meta.dir, "..");
const businessApp = join(root, "components/business-app");

/** A shown language picked from a literal instead of resolveLanguage, or a branch on the language outside the catalog. */
const LITERAL_LANGUAGE = /(?:resolvedLanguage|i18n\.language)(?:\s*\?\?\s*i18n\.language)?\s*(?:\?\?|===|!==)\s*["'][\w-]+["']|(?:resolvedLanguage|i18n\.language)\)?\.startsWith\(/g;

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

test("Business picks the shown language through resolveLanguage, never a literal or a Spanish branch", () => {
  const found = Object.fromEntries(
    sources(businessApp)
      .map((path) => [relative(root, path), readFileSync(path, "utf-8").match(LITERAL_LANGUAGE)?.length ?? 0] as const)
      .filter(([, count]) => count > 0),
  );
  assert.deepEqual(found, {});
});
