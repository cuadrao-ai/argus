import { describe, expect, test } from "bun:test";
import { businessContent } from "../components/content";
import { siteCopy } from "../components/site-copy";
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

const legalText = (documents: typeof spanish) =>
  Object.values(documents)
    .flatMap((document) => document.blocks)
    .flatMap((block) => ("items" in block && block.items ? block.items : "text" in block ? [block.text] : []))
    .join(" ");

test("the English privacy page quotes the labels the English form shows", () => {
  const text = legalText(english);
  const formNames = (locale: "es" | "en") => [
    siteCopy[locale].cta,
    siteCopy[locale].contactLead.replace("\n", " ").replace(/\.$/, ""),
    businessContent[locale].contact.roleLabel,
    businessContent[locale].contact.pilot,
  ];
  for (const name of formNames("en")) expect(text).toContain(`"${name}`);
  for (const name of formNames("es")) expect(text).not.toContain(`"${name}`);
});

test.each([["es", spanish], ["en", english]] as const)("%s legal pages no longer describe the waitlist", (_locale, documents) => {
  expect(legalText(documents)).not.toMatch(/lista de espera|waitlist|anotarte|te anotaste|sign up|signing up/i);
});

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
      .find((text) => text.includes(locale === "es" ? 'Formulario "Hablemos' : '"Let’s talk about your business" form**')) ?? "";

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
