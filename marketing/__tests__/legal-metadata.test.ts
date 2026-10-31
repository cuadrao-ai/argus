import { expect, test } from "bun:test";
import { PAGE_METADATA } from "../lib/page-metadata";

const TAB_TITLES = {
  es: {
    terms: "Términos | Cuadrao",
    privacy: "Privacidad | Cuadrao",
    deletion: "Eliminar tus datos | Cuadrao",
  },
  en: {
    terms: "Terms | Cuadrao",
    privacy: "Privacy | Cuadrao",
    deletion: "Delete your data | Cuadrao",
  },
} as const;

for (const locale of ["es", "en"] as const) {
  for (const page of ["terms", "privacy", "deletion"] as const) {
    test(`${locale} ${page} tab title is the approved short title`, () => {
      expect(PAGE_METADATA[locale][page]?.title).toBe(TAB_TITLES[locale][page]);
    });
  }
}
