import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "bun:test";
import { STATUS_CHIP_WIDTH } from "@/components/business-app/foundation/StatusChip";
import { RECORDS_COLUMN_LAYOUT } from "@/components/business-app/transacciones/records-view-preferences";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

const cells = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/transacciones-cells.module.css"), "utf8");
const chips = readFileSync(resolve(import.meta.dir, "../components/business-app/foundation/status-chip.module.css"), "utf8");
const rule = (name: string, css = cells) => css.match(new RegExp(`(?:^|\\n)\\.${name} \\{([^}]*)\\}`))?.[1] ?? "";
const CHARACTER_PX = 6.4;
const CHIP_PADDING_PX = 16;

test("Estado uses the shared fixed chip width and never wraps or spills", () => {
  assert.equal(RECORDS_COLUMN_LAYOUT.stage.width, 168);
  assert.equal(STATUS_CHIP_WIDTH, 120);
  assert.ok(STATUS_CHIP_WIDTH <= RECORDS_COLUMN_LAYOUT.stage.width);
  assert.match(rule("workflow", chips), /max-width:100%/);
  assert.match(rule("workflow", chips), /white-space:nowrap/);
  assert.match(rule("stage", chips), /overflow:hidden/);
  assert.match(rule("stage", chips), /text-overflow:ellipsis/);
});

test.each([["es-419", spanish], ["en", english]] as const)("the everyday status chips fit their width in %s", (_, locale) => {
  const { ready, not_ready } = locale.business.transactions.layout.workflow;
  for (const label of [ready, not_ready, locale.business.receipts.duplicate_resolution.different]) {
    const chip = Math.ceil(label.length * CHARACTER_PX) + CHIP_PADDING_PX;
    assert.ok(chip <= STATUS_CHIP_WIDTH, `"${label}" needs ${chip}px of ${STATUS_CHIP_WIDTH}px`);
  }
});

test("a read-only note adds no height, so it centers with its row", () => {
  const note = rule("noteButton");
  assert.ok(note);
  assert.doesNotMatch(note, /min-height/);
});
