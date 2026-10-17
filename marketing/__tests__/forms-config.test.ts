import { describe, expect, test } from "bun:test";
import { readFormsConfig } from "../lib/forms/config";

describe("forms configuration", () => {
  test("reads the inquiry recipient from CUADRAO_INQUIRY_TO and has no default", () => {
    expect(readFormsConfig({}).inquiryTo).toBeNull();
    expect(readFormsConfig({ CUADRAO_INQUIRY_TO: " Owner@Example.INVALID " }).inquiryTo).toBe(
      "owner@example.invalid",
    );
  });

  test("an invalid recipient reads as not configured", () => {
    expect(readFormsConfig({ CUADRAO_INQUIRY_TO: "a@x.invalid,b@x.invalid" }).inquiryTo).toBeNull();
  });
});
