import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { formatBusinessName } from "@/components/business-app/business-format";

describe("business display name", () => {
  test("an unnamed Business, which the server sends as null, takes the reader's localized title", () => {
    for (const name of [null, undefined, "", "  "]) {
      assert.equal(formatBusinessName(name, "Mi negocio"), "Mi negocio");
    }
  });

  test("a name the server sends is shown verbatim", () => {
    for (const name of ["Colmado Lucía", "My business supplies", "My business", "Business", "  Taller  "]) {
      assert.equal(formatBusinessName(name, "Mi negocio"), name);
    }
  });
});
