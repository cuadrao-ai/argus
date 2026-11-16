import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "bun:test";
import { RECORDS_COLUMN_LAYOUT } from "@/components/business-app/transacciones/records-view-preferences";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

const cells = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/transacciones-cells.module.css"), "utf8");
const rule = (name: string) => cells.match(new RegExp(`(?:^|\\n)\\.${name} \\{([^}]*)\\}`))?.[1] ?? "";
const CHARACTER_PX = 6.4;
const CHIP_PADDING_PX = 16;

test("Estado uses its fixed chip width and never wraps or spills", () => {
  assert.equal(RECORDS_COLUMN_LAYOUT.stage.width, 168);
  assert.equal(RECORDS_COLUMN_LAYOUT.stage.chipWidth, 120);
  assert.match(rule("workflow"), /max-width:100%/);
  assert.match(rule("workflow"), /white-space:nowrap/);
  assert.match(rule("stage"), /overflow:hidden/);
  assert.match(rule("stage"), /text-overflow:ellipsis/);
  const badge = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/RecordWorkflowBadge.tsx"), "utf8");
  assert.match(badge, /style=\{\{ width: RECORDS_COLUMN_LAYOUT\.stage\.chipWidth \}\}/);
  assert.match(badge, /\$\{styles\.workflow\} \$\{styles\.stage\}/);
});

test.each([["es-419", spanish], ["en", english]] as const)("the everyday Estado chips fit their column in %s", (_, locale) => {
  const { ready, not_ready } = locale.business.transactions.layout.workflow;
  for (const label of [ready, not_ready]) {
    const chip = Math.ceil(label.length * CHARACTER_PX) + CHIP_PADDING_PX;
    assert.ok(chip <= RECORDS_COLUMN_LAYOUT.stage.chipWidth, `"${label}" needs ${chip}px of ${RECORDS_COLUMN_LAYOUT.stage.chipWidth}px`);
  }
});

test("a read-only note adds no height, so it centers with its row", () => {
  const note = rule("noteButton");
  assert.ok(note);
  assert.doesNotMatch(note, /min-height/);
});
