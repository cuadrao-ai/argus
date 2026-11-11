import type { ReactNode } from "react";
import spanish from "../content/legal-es.json";
import english from "../content/legal-en.json";
import appSpanish from "../content/app-legal-es.json";
import appEnglish from "../content/app-legal-en.json";
import { legalSections, sectionId } from "@/lib/legal-sections";
import { htmlLang, type BusinessLocale } from "@/lib/site-routes";
import { BusinessHeader } from "./business-header";
import { BusinessFooter } from "./business-footer";
import { LegalIndex } from "./legal-index";
import { siteCopy } from "./site-copy";
import styles from "./business.module.css";
import legal from "./legal.module.css";

type Documents = { es: Record<string, LegalDocument>; en: Record<string, LegalDocument> };
type LegalDocument = { title: string; blocks: ({ kind: string; text?: string; items?: string[] })[] };

const website: Documents = { es: spanish, en: english };
const app: Documents = { es: appSpanish, en: appEnglish };

const SOURCES = {
  privacy: { documents: website, slug: "privacidad" },
  terms: { documents: website, slug: "terminos" },
  deletion: { documents: website, slug: "eliminar-datos" },
  appPrivacy: { documents: app, slug: "privacidad" },
  appTerms: { documents: app, slug: "terminos" },
} as const;

export type LegalPageName = keyof typeof SOURCES;

function shown(text: string): string {
  return text.replace(/^(?:Vigente desde|Effective): .+? (?=(?:Última actualización|Last updated): )/, "");
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*.*?\*\*|hola@cuadrao\.ai|\/eliminar-datos)/g).map((part, index) => {
    if (part.startsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part === "hola@cuadrao.ai") return <a key={index} href={`mailto:${part}`}>{part}</a>;
    if (part === "/eliminar-datos") return <a key={index} href={part}>{part}</a>;
    return part;
  });
}

export function LegalPage({ page, locale = "es" }: { page: LegalPageName; locale?: BusinessLocale }) {
  const { documents, slug } = SOURCES[page];
  const document = documents[locale][slug]!;
  const indexed = page !== "deletion";
  return (
    <div className={styles.site} lang={htmlLang(locale)} id="top" data-page-background="business">
      <BusinessHeader locale={locale} page={page} />
      <main id="business-main" tabIndex={-1} className={indexed ? `${legal.layout} ${legal.indexed}` : legal.layout}>
        {indexed && <LegalIndex label={siteCopy[locale].legalIndex} sections={legalSections(document.blocks)} />}
        <article className={legal.document} aria-labelledby="legal-title">
          <h1 id="legal-title">{document.title}</h1>
          {document.blocks.map((block, index) => {
            if (block.kind === "heading" && block.text) return <h2 key={index} id={sectionId(block.text)}>{block.text}</h2>;
            if (block.items) {
              const List = block.kind === "ordered" ? "ol" : "ul";
              return <List key={index}>{block.items.map((item) => <li key={item}>{inline(item)}</li>)}</List>;
            }
            return <p key={index}>{inline(shown(block.text ?? ""))}</p>;
          })}
        </article>
      </main>
      <BusinessFooter locale={locale} showClosing={false} />
    </div>
  );
}
