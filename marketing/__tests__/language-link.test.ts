import { expect, test } from "bun:test";
import { languageSwitch } from "../lib/language-link";

test("Spanish contact offers English on the matching English page", () => {
  expect(languageSwitch("es", "contact")).toEqual({
    href: "/en/contact",
    label: "English",
    lang: "en",
    phoneLabel: "Cambiar idioma",
  });
});

test("English privacy offers Español on the matching Spanish page", () => {
  expect(languageSwitch("en", "privacy")).toEqual({
    href: "/privacidad",
    label: "Español",
    lang: "es",
    phoneLabel: "Change language",
  });
});

test("the home link stays on home in the other language", () => {
  expect(languageSwitch("es", "home").href).toBe("/en");
  expect(languageSwitch("en", "home").href).toBe("/");
});
