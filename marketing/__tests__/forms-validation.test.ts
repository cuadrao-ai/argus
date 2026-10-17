import { describe, expect, test } from "bun:test";
import {
  emailDigest,
  isHoneypotFilled,
  normalizeEmail,
  parseMailbox,
  validateInquiry,
  validateSignup,
} from "../lib/forms/validation";
import { SUBMISSION_ID, inquiryBody } from "./forms-support";

describe("inquiry validation", () => {
  test("normalizes the address and trims the text", () => {
    const result = validateInquiry(inquiryBody({ name: "  Marisol Peña  " }));
    expect(result).toEqual({
      ok: true,
      value: {
        name: "Marisol Peña",
        email: "marisol@example.invalid",
        description: "Llevo las cuentas de una ferretería.",
        locale: "es",
        submissionId: SUBMISSION_ID,
      },
    });
  });

  test("an empty description is allowed", () => {
    expect(validateInquiry(inquiryBody({ description: "" })).ok).toBe(true);
  });

  test.each([
    [{ name: "" }, "name"],
    [{ name: "x".repeat(121) }, "name"],
    [{ name: "Ana\r\nBcc: someone@example.invalid" }, "name"],
    [{ email: "no-at-sign" }, "email"],
    [{ email: "a b@example.invalid" }, "email"],
    [{ email: `${"a".repeat(250)}@example.invalid` }, "email"],
    [{ description: "x".repeat(1001) }, "description"],
    [{ submissionId: "not-a-uuid" }, "submissionId"],
    [{ locale: "fr" }, "locale"],
  ])("rejects %j", (overrides, field) => {
    const result = validateInquiry(inquiryBody(overrides as Record<string, unknown>));
    expect(result).toEqual({ ok: false, fields: [field] });
  });

  test.each([null, "text", 4, ["a"]])("rejects a non-object body %p", (body) => {
    expect(validateInquiry(body)).toEqual({ ok: false, fields: ["body"] });
  });

  test("keeps newlines in the description but drops other control characters", () => {
    const result = validateInquiry(inquiryBody({ description: "uno\ndos\u0000\u0007" }));
    expect(result.ok && result.value.description).toBe("uno\ndos");
  });
});

describe("signup validation", () => {
  test("accepts an address and a language", () => {
    expect(validateSignup({ email: " Ana@Example.INVALID", locale: "en" })).toEqual({
      ok: true,
      value: { email: "ana@example.invalid", locale: "en" },
    });
  });

  test.each([
    [{ email: "", locale: "es" }, ["email"]],
    [{ email: "ana@example.invalid", locale: "xx" }, ["locale"]],
    [{ email: "ana", locale: "xx" }, ["email", "locale"]],
  ])("rejects %j", (body, fields) => {
    expect(validateSignup(body)).toEqual({ ok: false, fields });
  });
});

describe("address digest", () => {
  test("is the same for every spelling of one address", () => {
    expect(emailDigest(normalizeEmail(" Ana@Example.INVALID "))).toBe(
      emailDigest(normalizeEmail("ana@example.invalid")),
    );
  });

  test("is a 64 character lowercase hex string that does not contain the address", () => {
    const digest = emailDigest("ana@example.invalid");
    expect(digest).toMatch(/^[0-9a-f]{64}$/);
    expect(digest).not.toContain("ana");
  });
});

describe("honeypot", () => {
  test.each([
    [{ website: "https://spam.example.invalid" }, true],
    [{ website: "   " }, false],
    [{ website: "" }, false],
    [{}, false],
    [null, false],
  ])("%j is %p", (body, filled) => {
    expect(isHoneypotFilled(body)).toBe(filled);
  });
});

describe("configured mailbox", () => {
  test("accepts one bare address and normalizes it", () => {
    expect(parseMailbox(" Founder@Example.INVALID ")).toBe("founder@example.invalid");
  });

  test.each([
    undefined,
    "",
    "   ",
    "a@example.invalid, b@example.invalid",
    "Founder <founder@example.invalid>",
    "founder@example.invalid\nBcc: x@example.invalid",
    "no-at-sign",
  ])("refuses %p so it can never become several recipients", (value) => {
    expect(parseMailbox(value)).toBeNull();
  });
});
