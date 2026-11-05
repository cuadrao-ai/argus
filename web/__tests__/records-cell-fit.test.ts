import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test } from "bun:test";
import { RECORDS_PREVIEW_COLUMNS } from "@/components/business-app/transacciones/records-view-preferences";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

// Measured on the live panel: Inter 12px weight 500 averages 6.3px a character.
const CHARACTER_PX = 6.4;
const CHIP_PADDING_PX = 16;
const CELL_PADDING_PX = 24;

const labels = (words: unknown): string[] => typeof words === "string" ? [words] : Object.values(words as object).flatMap(labels);

test.each([["es-419", spanish], ["en", english]] as const)("every Estado chip fits its column in %s", (_, locale) => {
  const estado = RECORDS_PREVIEW_COLUMNS.find((column) => column.key === "estado")!.width!;
  for (const label of labels(locale.business.transactions.layout.workflow)) {
    const chip = Math.ceil(label.length * CHARACTER_PX) + CHIP_PADDING_PX;
    assert.ok(chip + CELL_PADDING_PX <= estado, `"${label}" needs ${chip + CELL_PADDING_PX}px of ${estado}px`);
  }
});

test("a read-only note adds no height, so it centers with its row", () => {
  const css = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/transacciones-cells.module.css"), "utf8");
  const note = css.match(/(?:^|\n)\.noteButton \{([^}]*)\}/)?.[1];
  assert.ok(note);
  assert.doesNotMatch(note, /min-height/);
});
