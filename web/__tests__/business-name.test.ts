import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { formatBusinessName } from "@/components/business-app/business-format";

describe("business display name", () => {
  test("uses the existing localized fallback for absent names and the English default", () => {
    for (const name of [null, undefined, "", "  ", "My business"]) {
      assert.equal(formatBusinessName(name, "Mi negocio"), "Mi negocio");
    }
  });

  test("preserves custom names verbatim", () => {
    for (const name of ["Colmado Lucía", "My business supplies", "Mi negocio", "Business", "  Taller  "]) {
      assert.equal(formatBusinessName(name, "Mi negocio"), name);
    }
  });

  test("keeps the English default for the English locale", () => {
    assert.equal(formatBusinessName("My business", "My business"), "My business");
  });
});
