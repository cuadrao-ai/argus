import { expect, test } from "bun:test";
import spanish from "../content/legal-es.json";
import english from "../content/legal-en.json";
import { legalSections, sectionId } from "../lib/legal-sections";

// Published deep links. Changing one breaks every link that points at it.
const PINNED = {
  es: {
    privacidad: [
      "quienes-somos",
      "que-datos-recogemos-y-para-que",
      "base-legal-y-consentimiento",
      "con-quien-los-compartimos",
      "transferencia-a-estados-unidos",
      "cuanto-tiempo-los-guardamos",
      "tus-derechos",
      "como-borrar-tus-datos",
      "residentes-de-ee-uu",
      "seguridad",
      "menores",
      "cambios",
      "idioma-y-contacto",
    ],
    terminos: [
      "quienes-somos",
      "que-es-este-sitio",
      "pilotos",
      "uso-aceptable",
      "contenido-y-marca",
      "no-es-asesoria",
      "sitio-tal-cual",
      "responsabilidad",
      "tus-derechos-como-consumidor",
      "ley-aplicable-y-disputas",
      "cambios",
      "idioma-y-contacto",
    ],
    "eliminar-datos": ["como-pedir-que-borremos-tus-datos", "que-pasa-despues"],
  },
  en: {
    privacidad: [
      "who-we-are",
      "what-we-collect-and-why",
      "legal-basis-and-consent",
      "who-we-share-it-with",
      "transfer-to-the-united-states",
      "how-long-we-keep-it",
      "your-rights",
      "deleting-your-data",
      "us-residents",
      "security",
      "children",
      "changes",
      "language-and-contact",
    ],
    terminos: [
      "who-we-are",
      "what-this-site-is",
      "pilots",
      "acceptable-use",
      "content-and-name",
      "not-advice",
      "as-is-site",
      "liability",
      "your-consumer-rights",
      "governing-law-and-disputes",
      "changes",
      "language-and-contact",
    ],
    "eliminar-datos": ["how-to-ask-us-to-delete-your-data", "what-happens-next"],
  },
} as const;

for (const [locale, documents] of [["es", spanish], ["en", english]] as const) {
  for (const slug of Object.keys(documents) as (keyof typeof documents)[]) {
    test(`${locale} ${slug} keeps every pinned section anchor`, () => {
      expect(legalSections(documents[slug].blocks).map((section) => section.id)).toEqual([...PINNED[locale][slug]]);
    });
  }
}

test("the privacy section that links to /eliminar-datos keeps its anchor in both languages", () => {
  for (const [documents, id] of [[spanish, "como-borrar-tus-datos"], [english, "deleting-your-data"]] as const) {
    const blocks = documents.privacidad.blocks;
    const link = blocks.findIndex((block) => "text" in block && block.text?.includes("/eliminar-datos"));
    const heading = blocks.slice(0, link).findLast((block) => block.kind === "heading");
    expect(heading && "text" in heading ? sectionId(heading.text!) : null).toBe(id);
  }
});

test("the index lists the headings in reading order with their visible titles", () => {
  const blocks = [
    { kind: "paragraph", text: "Intro" },
    { kind: "heading", text: "1. Quiénes somos" },
    { kind: "list", items: ["Uno"] },
    { kind: "heading", text: "7. Sitio \"tal cual\"" },
    { kind: "heading", text: "9. Residentes de EE. UU." },
  ];
  expect(legalSections(blocks)).toEqual([
    { id: "quienes-somos", title: "1. Quiénes somos" },
    { id: "sitio-tal-cual", title: "7. Sitio \"tal cual\"" },
    { id: "residentes-de-ee-uu", title: "9. Residentes de EE. UU." },
  ]);
});

test("renumbering a heading keeps its anchor", () => {
  expect(sectionId("4. Uso aceptable")).toBe(sectionId("12. Uso aceptable"));
});

test("two headings that would share an anchor fail the build", () => {
  expect(() => legalSections([{ kind: "heading", text: "1. Cambios" }, { kind: "heading", text: "2. Cambios" }])).toThrow();
});
