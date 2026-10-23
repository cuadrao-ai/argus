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

  test("privacy policy matches the optional demo checkbox and its purpose", () => {
    const documents = locale === "es" ? spanish : english;
    const contactParagraph = documents.privacidad.blocks
      .flatMap((block) =>
        "items" in block && block.items ? block.items : "text" in block ? [block.text] : [],
      )
      .find((text) => text.includes(locale === "es" ? 'Formulario "Hablemos' : '"Hablemos de tu negocio" form**')) ?? "";

    const expectedLabel =
      locale === "es" ? "Me interesa una demostración de Cuadrao." : "I’m interested in a Cuadrao demo.";
    expect(businessContent[locale].contact.pilot).toBe(expectedLabel);
    expect(contactParagraph).toContain(expectedLabel);
    expect(contactParagraph).toContain(
      locale === "es" ? "invitarte a una demostración de Cuadrao" : "invite you to a Cuadrao demo",
    );
    expect(contactParagraph.toLowerCase()).not.toMatch(/prototipo|prototype|piloto|pilot|probar|try it/);
  });
});
