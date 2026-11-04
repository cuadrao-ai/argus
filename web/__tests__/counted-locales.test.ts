import { expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

function flatten(tree: Record<string, unknown>, prefix = ""): Record<string, string> {
  return Object.fromEntries(Object.entries(tree).flatMap(([name, value]) => {
    const key = `${prefix}${name}`;
    return typeof value === "string" ? [[key, value]] : Object.entries(flatten(value as Record<string, unknown>, `${key}.`));
  }));
}

const catalogs = { en: flatten(en), "es-419": flatten(es) };
const keys = [...new Set(Object.values(catalogs).flatMap(Object.keys))];
const baseKey = (key: string) => key.replace(/_(one|other|zero)$/, "");

function candidates(expression: ts.Expression): string[] {
  if (ts.isStringLiteralLike(expression)) {
    if (expression.text.includes(".")) return [baseKey(expression.text)];
    return keys.filter(key => baseKey(key) === expression.text || baseKey(key).endsWith(`.${expression.text}`)).map(baseKey);
  }
  if (ts.isConditionalExpression(expression)) return [...candidates(expression.whenTrue), ...candidates(expression.whenFalse)];
  if (ts.isCallExpression(expression)) return expression.arguments.flatMap(candidates);
  if (ts.isTemplateExpression(expression)) {
    return keys.filter(key => key.startsWith(expression.head.text) && key.endsWith(expression.templateSpans.at(-1)!.literal.text) && Object.values(catalogs).some(catalog => catalog[key]?.includes("{{count}}"))).map(baseKey);
  }
  return [];
}

test("translation calls with count have a singular form in both languages", () => {
  const missing = new Set<string>();
  for (const folder of ["app", "components", "lib"]) {
    const directory = join(import.meta.dir, "..", folder);
    for (const file of readdirSync(directory, { recursive: true })) {
      if (!/\.tsx?$/.test(file)) continue;
      const source = ts.createSourceFile(file, readFileSync(join(directory, file), "utf8"), ts.ScriptTarget.Latest, true);
      const visit = (node: ts.Node) => {
        if (ts.isCallExpression(node) && /^(t|word)$/.test(node.expression.getText(source)) && node.arguments.slice(1).some(argument =>
          ts.isObjectLiteralExpression(argument) && argument.properties.some(property => property.name?.getText(source).replace(/["']/g, "") === "count"),
        )) {
          for (const key of candidates(node.arguments[0])) {
            for (const [language, catalog] of Object.entries(catalogs)) {
              if (!catalog[`${key}_one`]) missing.add(`${language}: ${key}`);
            }
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
  }
  expect([...missing].sort()).toEqual([]);
});
