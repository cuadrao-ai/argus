import assert from "node:assert/strict";
import { test } from "bun:test";
import { formatRnc } from "@/lib/rnc-status";
test("nine and eleven digit display, all other text unchanged", () => {
  assert.equal(formatRnc("101123456"), "1-01-12345-6");
  assert.equal(formatRnc("00112345678"), "001-1234567-8");
  assert.equal(formatRnc("12-345"), "12-345");
});
