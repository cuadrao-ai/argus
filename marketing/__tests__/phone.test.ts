import { describe, expect, test } from "bun:test";
import { checkPhone, cleanPhoneInput } from "../components/phone";

describe("phone input", () => {
  test("cleaning keeps digits and a leading plus", () => {
    expect(cleanPhoneInput(" (809) 555-0123 ext")).toBe("8095550123");
    expect(cleanPhoneInput("+1 (809) 555-0123")).toBe("+18095550123");
    expect(cleanPhoneInput("1+2")).toBe("12");
  });

  test("empty stays optional", () => {
    expect(checkPhone("")).toEqual({ status: "empty" });
    expect(checkPhone("  -- ")).toEqual({ status: "empty" });
  });

  test("Dominican Republic numbers in common spellings", () => {
    const valid = { status: "valid", display: "+1 809 555 0123" };
    for (const raw of ["8095550123", "(809) 555-0123", "809.555.0123", "1 809 555 0123", "+1 809 555 0123", "+18095550123"]) {
      expect(checkPhone(raw)).toEqual(valid);
    }
    expect(checkPhone("829-555-0199")).toEqual({ status: "valid", display: "+1 829 555 0199" });
  });

  test("short and long DR/US numbers need ten national digits", () => {
    for (const raw of ["1234", "809555012", "80955501234", "23123123123123", "+1 809 555 012", "+1 809 555 01234"]) {
      expect(checkPhone(raw)).toEqual({ status: "invalid", reason: "length" });
    }
  });

  test("ten-digit numbers with impossible area or exchange codes have a format error", () => {
    for (const raw of ["0095550123", "8091550123", "+1 009 555 0123", "+1 809 155 0123"]) {
      expect(checkPhone(raw)).toEqual({ status: "invalid", reason: "format" });
    }
    for (const raw of ["8295550199", "8495550199", "2025550199"]) {
      expect(checkPhone(raw).status).toBe("valid");
    }
  });

  test("only Dominican Republic and United States regions are accepted", () => {
    for (const raw of ["+34 612 345 678", "+44 20 7946 0958", "4165550123", "+1 416 555 0123", "8765550123", "+1 876 555 0123", "8005550123", "+1 800 555 0123"]) {
      expect(checkPhone(raw)).toEqual({ status: "invalid", reason: "region" });
    }
    for (const raw of ["8095550123", "8295550123", "8495550123", "2025550123", "2125550123", "4155550123", "7875550123", "+1 202 555 0123"]) {
      expect(checkPhone(raw).status).toBe("valid");
    }
    expect(checkPhone("34612345678")).toEqual({ status: "invalid", reason: "length" });
    expect(checkPhone("+3461234")).toEqual({ status: "invalid", reason: "region" });
    expect(checkPhone("+3461234567890123")).toEqual({ status: "invalid", reason: "region" });
    expect(checkPhone("+441234")).toEqual({ status: "invalid", reason: "region" });
  });
});
