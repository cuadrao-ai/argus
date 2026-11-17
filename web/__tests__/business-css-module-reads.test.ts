import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { test } from "bun:test";

const WEB = resolve(import.meta.dir, "..");
const ROOT = resolve(WEB, "components/business-app");

const sources = readdirSync(ROOT, { recursive: true, encoding: "utf8" })
  .filter((path) => /\.tsx?$/.test(path))
  .map((path) => resolve(ROOT, path));

function definedClasses(cssPath: string) {
  const css = readFileSync(cssPath, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  return new Set(Array.from(css.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g), (match) => match[1]));
}

function deadReads(file: string) {
  const source = readFileSync(file, "utf8");
  const code = source.replace(/^import [^;]*;$/gm, "");
  const dead: string[] = [];
  for (const [, alias, specifier] of source.matchAll(/^import (\w+) from "([^"]+\.module\.css)";$/gm)) {
    const cssPath = specifier.startsWith("@/") ? resolve(WEB, specifier.slice(2)) : resolve(dirname(file), specifier);
    const defined = definedClasses(cssPath);
    const reads = code.matchAll(new RegExp(`\\b${alias}(?:\\.([A-Za-z_]\\w*)|\\[["'\`]([\\w-]+)["'\`]\\])`, "g"));
    for (const [, dotted, bracketed] of reads) {
      const name = dotted ?? bracketed;
      if (!defined.has(name)) dead.push(`${relative(WEB, file)}: ${alias}.${name} is not in ${specifier}`);
    }
  }
  return dead;
}

test("every CSS module class a Business component reads is defined in the module it imports", () => {
  assert.ok(sources.length > 100, "found the Business components");
  assert.deepEqual(sources.flatMap(deadReads), []);
});
