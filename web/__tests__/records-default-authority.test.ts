import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { test } from "bun:test";
import ts from "typescript";
import { REPORT_PRESENTATION_KEYS, reportAnswerSchema, reportPresentationSchema, reportRequestSchema } from "@/lib/business-reports-api";
import { recordedReportAnswer } from "./fixtures/recorded-report-answer";
import { sampleRecordsPreferences } from "@/components/business-app/transacciones/sample-records-preferences";
import { recordsPresentationToReport } from "@/lib/business-reporting-wire";

const root = path.resolve(import.meta.dir, "..");
const columnKeys = new Set<string>([...REPORT_PRESENTATION_KEYS, ...sampleRecordsPreferences().order]);
/** The enum one schema in docs/api/openapi.yaml gives one property: the server registry's keys as the contract publishes them. */
function openapiEnum(schema: string, property: string): string[] {
  const lines = readFileSync(path.join(root, "../docs/api/openapi.yaml"), "utf8").split("\n");
  const start = lines.indexOf(`    ${schema}:`);
  const field = lines.findIndex((line, index) => index > start && line.startsWith(`        ${property}:`));
  const values: string[] = [];
  for (let index = lines.indexOf(lines.slice(field).find((line) => line.trim() === "enum:")!, field) + 1; /^\s+- /.test(lines[index]); index++) values.push(lines[index].trim().slice(2));
  return values;
}
function enclosing(node: ts.Node, predicate: (node: ts.Node) => boolean): boolean {
  for (let current = node.parent; current; current = current.parent) if (predicate(current)) return true;
  return false;
}
function columnDefaults(source: string, filename: string): string[] {
  const tree = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const violations: string[] = [];
  const catalogue = (node: ts.Node) => filename.endsWith("lib/business-reports-api.ts") && ts.isVariableDeclaration(node) && node.name.getText(tree) === "REPORT_PRESENTATION_KEYS";
  const validation = (node: ts.Node) => ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) && ["enum", "refine"].includes(node.expression.name.text);
  const exportSelection = (node: ts.Node) => filename.endsWith("lib/business-reports-api.ts") && ts.isPropertyAssignment(node) && node.name.getText(tree) === "columns";
  const visit = (node: ts.Node) => {
    // A rule kept by hand, such as which columns are required or purchase-only, reads as a map of columns to flags.
    if (ts.isObjectLiteralExpression(node)) {
      const flags = node.properties.filter((property) => ts.isPropertyAssignment(property) && columnKeys.has(property.name.getText(tree).replace(/^["']|["']$/g, "")) && [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(property.initializer.kind));
      if (flags.length >= 2) violations.push(node.getText(tree));
    }
    if (ts.isArrayLiteralExpression(node)) {
      const values = node.elements.filter(ts.isStringLiteral).map((element) => element.text);
      const namesColumns = values.length >= 2 && values.every((value) => columnKeys.has(value));
      const derivesCatalogue = node.elements.some((element) => ts.isSpreadElement(element) && element.expression.getText(tree) === "REPORT_PRESENTATION_KEYS");
      if ((namesColumns || derivesCatalogue) && !enclosing(node, catalogue) && !enclosing(node, validation) && !enclosing(node, exportSelection)) violations.push(node.getText(tree));
    }
    if (ts.isPropertyAssignment(node) && ["order", "hidden"].includes(node.name.getText(tree))) {
      const initializer = node.initializer;
      if (ts.isArrayLiteralExpression(initializer) || /\bRECORDS_PREVIEW_COLUMNS\b|\bREPORT_PRESENTATION_KEYS\s*\.map\b/.test(initializer.getText(tree)) || ts.isIdentifier(initializer) && initializer.text === "REPORT_PRESENTATION_KEYS") violations.push(initializer.getText(tree));
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return violations;
}
const skippedDirectories = new Set(["node_modules", ".git", ".turbo", "out", "build", "dist", "coverage", "playwright-report", "test-results", "__tests__", "e2e"]);
const recordedFixture = path.join(root, "test-fixtures/records-default-report-answer.json");
function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) return skippedDirectories.has(entry.name) || entry.name.startsWith(".next") ? [] : sourceFiles(filename);
    return /\.(?:[cm]?[jt]sx?|json)$/.test(filename) && !/\.(?:test|spec)\./.test(filename) ? [filename] : [];
  });
}
function jsonColumnDefaults(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    if (value.length >= 2 && value.every((item) => typeof item === "string" && columnKeys.has(item))) return [value];
    return value.flatMap(jsonColumnDefaults);
  }
  return value !== null && typeof value === "object" ? Object.values(value).flatMap(jsonColumnDefaults) : [];
}
test("web contains validation catalogues but no table default column arrays", () => {
  const violations = sourceFiles(root).flatMap((filename) => {
    if (filename === recordedFixture) return [];
    const source = readFileSync(filename, "utf8");
    const found = filename.endsWith(".json") ? jsonColumnDefaults(JSON.parse(source)) : columnDefaults(source, filename);
    return found.map((value) => `${path.relative(root, filename)}: ${JSON.stringify(value)}`);
  });
  assert.deepEqual(violations, []);
});
test("the web's column keys are the contract's: the openapi Presentation and ReportColumn enums", () => {
  assert.deepEqual(openapiEnum("Presentation", "order"), [...REPORT_PRESENTATION_KEYS]);
  assert.deepEqual(openapiEnum("ReportColumn", "key"), [...REPORT_PRESENTATION_KEYS]);
});
test("the web validates a layout's shape only and keeps no column rule of its own", () => {
  assert.equal(reportPresentationSchema.safeParse({ order: ["date", "counterparty", "category"], hidden: ["counterparty"], density: 48 }).success, true);
  const ruled = { ...recordedReportAnswer, columns: recordedReportAnswer.columns.map((column) => ({ ...column, required: column.key === "note", pinned: false })) };
  assert.deepEqual(reportAnswerSchema.parse(ruled).columns, ruled.columns);
});
test("authority guard rejects renamed literal defaults and order derived from a catalogue", () => {
  for (const source of [
    'const required = { counterparty: true, gross_amount: true };',
    'const startingColumns = ["counterparty", "date", "gross_amount"];',
    'const layout = () => ({ order: RECORDS_PREVIEW_COLUMNS.map(column => column.key), hidden: ["funding"] });',
    'const schema = z.object({ order: z.array(key).default([...REPORT_PRESENTATION_KEYS]) });',
  ]) assert.ok(columnDefaults(source, "hooks/candidate.js").length > 0, source);
});
test("only the checked fixture may provide JSON table defaults", () => {
  assert.ok(jsonColumnDefaults({ presentation: { order: ["counterparty", "date"], hidden: ["funding", "expense_type"] } }).length > 0);
  assert.deepEqual(jsonColumnDefaults({ totals: [], matching_count: 0 }), []);
});
test("preview adapts the recorded server answer and request validation adds no presentation", () => {
  assert.deepEqual(recordsPresentationToReport(sampleRecordsPreferences()), recordedReportAnswer.presentation);
  assert.equal(reportRequestSchema.safeParse({ schema_version: 1, presentation: recordedReportAnswer.presentation }).success, false);
  assert.equal(reportPresentationSchema.safeParse({}).success, false);
  const request = reportRequestSchema.parse({ schema_version: 2 });
  assert.equal(Object.hasOwn(JSON.parse(JSON.stringify(request)), "presentation"), false);
  for (const filename of ["components/business-app/transacciones/BusinessReportsPanel.tsx", "lib/business-reporting-wire.ts", "lib/business-reports-api.ts"]) {
    assert.doesNotMatch(readFileSync(path.join(root, filename), "utf8"), /sampleRecordsPreferences|test-fixtures|sample-records-preferences/);
  }
});
