import { describe, expect, test } from "bun:test";
import { businessContent } from "../components/content";
import { LOCALES } from "../lib/site-routes";
import spanish from "../content/legal-es.json";
import english from "../content/legal-en.json";

for (const [locale, documents] of [["es", spanish], ["en", english]] as const) {
  test(`${locale} publishes the current security-only cookie policy`, () => {
    const text = JSON.stringify(documents.privacidad);
    expect(text).toContain("Cuadrao LLC");
    expect(text).toContain("Cookies:");
    expect(text).toContain("GPC");
    expect(text).not.toMatch(/no usamos cookies\.|we don't use cookies\./i);
  });
}

describe.each(LOCALES)("contact form privacy line (%s)", (locale) => {
  test("does not claim the details are used only to reply", () => {
    expect(businessContent[locale].contact.privacy).not.toMatch(/solo para responderte|only to reply/);
  });
});
