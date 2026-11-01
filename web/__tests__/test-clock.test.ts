import assert from "node:assert/strict";
import { describe, test, setSystemTime } from "bun:test";
import { TEST_NOW } from "./test-clock";
import { periodRange } from "@/components/business-app/business-format";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";

describe("the clock every test starts from", () => {
  test("is the pinned instant, so a suite passes or fails the same on every day it runs", () => {
    assert.equal(new Date().getTime(), TEST_NOW.getTime());
    assert.deepEqual(periodRange("this_month"), { key: "this_month", from: "2026-10-01", to: null });
  });

  test("keeps the sample records inside the default month", async () => {
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const thisMonth = await source.expenses("2026-10-01", null);
    const everything = await source.expenses("2000-01-01", null);
    assert.ok(everything.length > 0);
    assert.equal(thisMonth.length, everything.length);
  });

  test("a test that leaves the clock on another day does not carry it to the next test", () => {
    setSystemTime(new Date("2031-03-04T05:06:07Z"));
    assert.equal(new Date().getUTCFullYear(), 2031);
  });

  test("starts the test after it from the pinned instant again", () => {
    assert.equal(new Date().getTime(), TEST_NOW.getTime());
  });
});
