import assert from "node:assert/strict";
import { test } from "bun:test";
import type { BusinessFact } from "@/lib/business-dossier";
import { formatRnc, rncStatus } from "@/lib/rnc-status";
const known = (value: string): BusinessFact<string> => ({ state: "known", value, origin: "extracted", verified: true, source_ids: [] });
test("missing includes unknown, owner uncertainty and blank", () => {
  assert.equal(rncStatus(null), "missing");
  assert.equal(rncStatus(undefined), "missing");
  assert.equal(rncStatus(known("  ")), "missing");
  assert.equal(rncStatus({ state: "unknown", value: null, origin: null, verified: false, source_ids: [] }), "missing");
  assert.equal(rncStatus({ state: "owner_does_not_know", value: null, origin: "owner_stated", verified: false, source_ids: [] }), "missing");
});
test("length alone defines receipt errors; no checksum or verification claim", () => {
  for (const value of ["1", "12345678", "1234567890", "123456789012", "abc"]) assert.equal(rncStatus(known(value)), "invalid_length");
  for (const value of ["101123456", "1-01-12345-6", "00112345678", "001-1234567-8", "000000000", "00000000000"]) assert.equal(rncStatus(known(value)), "unverified");
});
test("nine and eleven digit display, all other text unchanged", () => {
  assert.equal(formatRnc("101123456"), "1-01-12345-6");
  assert.equal(formatRnc("00112345678"), "001-1234567-8");
  assert.equal(formatRnc("12-345"), "12-345");
});
