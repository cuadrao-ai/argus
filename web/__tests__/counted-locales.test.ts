import { expect, test } from "bun:test";
import { readdirSync } from "node:fs";
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

const root = join(import.meta.dir, "..");
const config = ts.readConfigFile(join(root, "tsconfig.json"), ts.sys.readFile);
const { options } = ts.parseJsonConfigFileContent(config.config, ts.sys, root);
const files = ["app", "components", "lib"].flatMap(folder => {
  const directory = join(root, folder);
  return readdirSync(directory, { recursive: true }).filter(file => /\.tsx?$/.test(file)).map(file => join(directory, file));
});
const program = ts.createProgram(files, options);
const sources = files.map(file => program.getSourceFile(file)!);
const checker = program.getTypeChecker();
const hasCount = (node: ts.CallExpression) => node.arguments.slice(1).some(argument =>
  ts.isObjectLiteralExpression(argument) && argument.properties.some(property => property.name?.getText().replace(/["']/g, "") === "count"),
);

function callerKeys(expression: ts.Expression): string[] {
  const type = checker.getTypeAtLocation(expression);
  const literals = (type.isUnion() ? type.types : [type]).flatMap(member => member.isStringLiteral() ? [member.value] : []);
  if (literals.length) return literals.flatMap(key => key.includes(".") ? [key] : keys.filter(candidate => candidate.endsWith(`.${key}`)));
  if (ts.isCallExpression(expression)) return expression.arguments.flatMap(callerKeys);
  return [];
}

const calls = sources.flatMap(source => {
  const found: { key: string; counted: boolean }[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && /^(t|word)$/.test(node.expression.getText(source)) && node.arguments[0]) {
      for (const key of callerKeys(node.arguments[0])) found.push({ key, counted: hasCount(node) });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
});

function redundantBases(catalog: Record<string, string>, callers: typeof calls): string[] {
  const withoutCount = new Set(callers.filter(call => !call.counted).map(call => call.key));
  return Object.keys(catalog).filter(key => catalog[`${key}_one`] && catalog[`${key}_other`] && !withoutCount.has(key)).sort();
}

test("translation calls with count have a singular form in both languages", () => {
  const missing = new Set<string>();
  for (const source of sources) {
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && /^(t|word)$/.test(node.expression.getText(source)) && hasCount(node)) {
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
  expect([...missing].sort()).toEqual([]);
});

test("counted translations keep a base only for callers without count", () => {
  for (const [language, catalog] of Object.entries(catalogs)) {
    expect(redundantBases(catalog, calls), language).toEqual([]);
  }
});

test("an uncounted caller retains its base without retaining counted-only duplicates", () => {
  const catalog = { label: "items", label_one: "item", label_other: "items" };
  const counted = { key: "label", counted: true };
  expect(redundantBases(catalog, [counted])).toEqual(["label"]);
  expect(redundantBases(catalog, [counted, { key: "label", counted: false }])).toEqual([]);
  expect(redundantBases(catalog, [counted, { key: "label_one", counted: false }])).toEqual(["label"]);
});
