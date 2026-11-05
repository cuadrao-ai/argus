import assert from "node:assert/strict";
import { test } from "bun:test";
import { pickDay } from "@/components/business-app/foundation/RangeCalendar";

test("the first tap starts a one-day range and the second ends it", () => {
  const first = pickDay({ from: "2026-10-01", to: "2026-10-31" }, "start", "2026-10-10");
  assert.deepEqual(first, { range: { from: "2026-10-10", to: "2026-10-10" }, phase: "end" });
  assert.deepEqual(pickDay(first.range, first.phase, "2026-10-24"), { range: { from: "2026-10-10", to: "2026-10-24" }, phase: "start" });
});

test("an end tapped before the start starts the range over there", () => {
  assert.deepEqual(pickDay({ from: "2026-10-10", to: "2026-10-10" }, "end", "2026-10-03"), { range: { from: "2026-10-03", to: "2026-10-03" }, phase: "end" });
});
