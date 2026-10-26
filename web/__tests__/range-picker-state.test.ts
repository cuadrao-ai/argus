import assert from "node:assert/strict";
import { test } from "bun:test";
import { createRangeDraft, parseRangeInput, presetRange, previewRange, reduceRangeDraft, shiftMonth, validDraftRange } from "@/components/business-app/foundation/range-picker-state";

const initial = () => createRangeDraft({ from: "2026-10-01", to: "2026-10-25" }, "es-419");
test("typed dates are locale-specific and reject impossible calendar dates", () => {
  assert.equal(parseRangeInput("31/02/2026", "es-419"), null);
  assert.equal(parseRangeInput("29/02/2024", "es-419"), "2024-02-29");
  assert.equal(parseRangeInput("10/25/2026", "en"), "2026-10-25");
  assert.equal(parseRangeInput("25/10/2026", "en"), null);
  assert.equal(parseRangeInput("2026-10-25", "es-419"), null);
});
test("two picks allow same-day, reverse and cross-month ranges", () => {
  for (const [start, end, expected] of [
    ["2026-10-10", "2026-10-10", { from: "2026-10-10", to: "2026-10-10" }],
    ["2026-10-20", "2026-10-10", { from: "2026-10-10", to: "2026-10-20" }],
    ["2026-10-30", "2026-11-03", { from: "2026-10-30", to: "2026-11-03" }],
  ] as const) {
    const first = reduceRangeDraft(initial(), { type: "pick", day: start }, "es-419");
    const last = reduceRangeDraft(first, { type: "pick", day: end }, "es-419");
    assert.deepEqual(last.range, expected); assert.equal(last.phase, "start");
  }
});
test("hover previews without committing and endpoint drag can cross the other endpoint", () => {
  const picked = reduceRangeDraft(initial(), { type: "pick", day: "2026-10-20" }, "es-419");
  const hovered = reduceRangeDraft(picked, { type: "hover", day: "2026-10-10" }, "es-419");
  assert.deepEqual(previewRange(hovered), { from: "2026-10-10", to: "2026-10-20" });
  assert.equal(hovered.range.from, "2026-10-20");
  const start = reduceRangeDraft(initial(), { type: "drag-start", edge: "to" }, "es-419");
  const moved = reduceRangeDraft(start, { type: "drag-move", day: "2026-09-29" }, "es-419");
  assert.deepEqual(moved.range, { from: "2026-09-29", to: "2026-10-01" });
  assert.deepEqual(reduceRangeDraft(moved, { type: "drag-cancel" }, "es-419").range, initial().range);
});
test("quick periods use complete prior quarter and inclusive day windows", () => {
  assert.deepEqual(presetRange("last_quarter", "2026-01-10"), { from: "2025-10-01", to: "2025-12-31" });
  assert.deepEqual(presetRange("last_quarter", "2026-10-25"), { from: "2026-07-01", to: "2026-09-30" });
  assert.deepEqual(presetRange("last_7", "2026-10-25"), { from: "2026-10-19", to: "2026-10-25" });
  assert.equal(shiftMonth("2024-02-29", 12), "2025-02-28");
});
test("typed draft rejects reversed and over-366-day ranges", () => {
  let draft = reduceRangeDraft(initial(), { type: "type", edge: "to", text: "30/09/2026" }, "es-419");
  assert.equal(validDraftRange(draft, "es-419"), null);
  draft = reduceRangeDraft(initial(), { type: "type", edge: "to", text: "02/10/2027" }, "es-419");
  assert.equal(validDraftRange(draft, "es-419"), null);
});
