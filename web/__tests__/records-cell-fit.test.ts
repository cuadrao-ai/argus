import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "bun:test";
import { RECORDS_COLUMN_LAYOUT } from "@/components/business-app/transacciones/records-view-preferences";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

const cells = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/transacciones-cells.module.css"), "utf8");
const rule = (name: string) => cells.match(new RegExp(`(?:^|\\n)\\.${name} \\{([^}]*)\\}`))?.[1] ?? "";
// Measured in the browser (#2044): Estado's pill gives its text the column's width less 24px. At 168px every Spanish reason fits ("Falta la forma de pago" 144px); the longest English ones still cut ("Payment method is missing" 165px).
const ESTADO_TEXT_PX = 144;
const CHARACTER_PX = 6.4;
const CHIP_PADDING_PX = 16;
const labels = (words: unknown): string[] => typeof words === "string" ? [words] : Object.values(words as object).flatMap(labels);

test("Estado keeps its measured width, and a chip wider than it cuts with an ellipsis and never spills", () => {
  assert.equal(RECORDS_COLUMN_LAYOUT.stage.width, ESTADO_TEXT_PX + 24);
  assert.match(rule("workflow"), /max-width:100%/);
  assert.match(rule("workflow"), /white-space:nowrap/);
  assert.match(rule("stage"), /overflow:hidden/);
  assert.match(rule("stage"), /text-overflow:ellipsis/);
  const badge = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/RecordWorkflowBadge.tsx"), "utf8");
  assert.match(badge, /<Tooltip content=\{label\}[^>]*><span data-record-workflow=\{metadata\.workflow\} className=\{`\$\{styles\.workflow\} \$\{styles\.stage\}/);
});

test.each([["es-419", spanish], ["en", english]] as const)("the everyday Estado chips fit their column in %s", (_, locale) => {
  const { exported, ready, review, missing } = locale.business.transactions.layout.workflow;
  for (const label of [exported, ready, review, missing.rnc_missing, missing.ncf_missing, missing.rnc_invalid, missing.ncf_invalid, missing.date_missing]) {
    const chip = Math.ceil(label.length * CHARACTER_PX) + CHIP_PADDING_PX;
    assert.ok(chip <= ESTADO_TEXT_PX, `"${label}" needs ${chip}px of ${ESTADO_TEXT_PX}px`);
  }
});

test("a read-only note adds no height, so it centers with its row", () => {
  const note = rule("noteButton");
  assert.ok(note);
  assert.doesNotMatch(note, /min-height/);
});
