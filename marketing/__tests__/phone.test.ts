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

  test("Dominican and North American numbers in any common spelling", () => {
    const valid = { status: "valid", display: "+1 809 555 0123" };
    for (const raw of ["8095550123", "(809) 555-0123", "809.555.0123", "1 809 555 0123", "+1 809 555 0123", "+18095550123"]) {
      expect(checkPhone(raw)).toEqual(valid);
    }
    expect(checkPhone("829-555-0199")).toEqual({ status: "valid", display: "+1 829 555 0199" });
  });

  test("short, long and impossible North American numbers are refused", () => {
    for (const raw of ["809555012", "80955501234", "0095550123", "8091550123", "+1 809 555 012"]) {
      expect(checkPhone(raw).status).toBe("invalid");
    }
  });

  test("other countries need a plus and 8 to 15 digits", () => {
    expect(checkPhone("+34 612 345 678")).toEqual({ status: "valid", display: "+34612345678" });
    expect(checkPhone("+44 20 7946 0958")).toEqual({ status: "valid", display: "+442079460958" });
    expect(checkPhone("34612345678").status).toBe("invalid");
    expect(checkPhone("+3461234").status).toBe("invalid");
    expect(checkPhone("+3461234567890123").status).toBe("invalid");
  });
});
