import { expect, test } from "bun:test";
import { containsSensitiveDigits, parsePersonalWaitlist, plainWish } from "../lib/forms/personal-waitlist-input";

test("the personal signup accepts only its optional answers and normalizes the email", () => {
  expect(parsePersonalWaitlist({ email: "  Person@Example.test ", expenseMethod: "En una libreta o notas", wish: "  Ordenar mis gastos  ", captchaToken: "token", whatsapp: "ignored", fingerprint: "ignored" })).toEqual({ email: "person@example.test", expenseMethod: "En una libreta o notas", wish: "Ordenar mis gastos", captchaToken: "token" });
  expect(parsePersonalWaitlist({ email: "person@example.test" })).toEqual({ email: "person@example.test", expenseMethod: null, wish: null, captchaToken: "" });
  expect(parsePersonalWaitlist({ email: "person@example.test", expenseMethod: "Not a choice" })).toBeNull();
  expect(parsePersonalWaitlist({ email: "not-an-email" })).toBeNull();
});

test("account-like digit runs drop only the optional answer", () => {
  for (const wish of ["Cuenta 1234567", "Tarjeta 1234 5678 9012 3456", "１２３４５６７", "١٢٣٤٥٦٧", "123-456-789", "1\u200b2\u200b3\u200b4\u200b5\u200b6\u200b7"]) {
    expect(containsSensitiveDigits(wish)).toBe(true);
    expect(parsePersonalWaitlist({ email: "person@example.test", wish })?.wish).toBeNull();
    expect(parsePersonalWaitlist({ email: "person@example.test", wish })?.email).toBe("person@example.test");
  }
  expect(containsSensitiveDigits("Quiero ordenar 3 cuentas y 2 tarjetas")).toBe(false);
});

test("optional text is plain, link-free and limited to 280 characters", () => {
  expect(plainWish('<script>alert(1)</script><b>Orden</b> https://example.test/a www.example.test example.test/path')).toBe("Orden");
  expect(plainWish("<img src=x onerror=alert(1)>Ayuda")).toBe("Ayuda");
  expect(plainWish("a".repeat(281))).toHaveLength(280);
  expect(plainWish("<script>unclosed")).toBeNull();
});
