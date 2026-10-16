import type { ReactNode } from "react";
import documents from "../content/legal-es.json";
import { BusinessHeader } from "./business-header";
import { BusinessFooter } from "./business-footer";
import styles from "./business.module.css";
import legal from "./legal.module.css";

export type LegalPageName = "privacy" | "terms" | "deletion";
const slugs = { privacy: "privacidad", terms: "terminos", deletion: "eliminar-datos" } as const;

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*.*?\*\*|hola@cuadrao\.ai|\/eliminar-datos)/g).map((part, index) => {
    if (part.startsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part === "hola@cuadrao.ai") return <a key={index} href={`mailto:${part}`}>{part}</a>;
    if (part === "/eliminar-datos") return <a key={index} href={part}>{part}</a>;
    return part;
  });
}

export function LegalPage({ page }: { page: LegalPageName }) {
  const document = documents[slugs[page]];
  return (
    <div className={styles.site} lang="es-419" id="top">
      <BusinessHeader locale="es" page={page} />
      <main id="business-main" tabIndex={-1} className={legal.layout}>
        <article className={legal.document} aria-labelledby="legal-title">
          <h1 id="legal-title">{document.title}</h1>
          {document.blocks.map((block, index) => {
            if (block.kind === "heading" && "text" in block) return <h2 key={index}>{block.text}</h2>;
            if ("items" in block && block.items) {
              const List = block.kind === "ordered" ? "ol" : "ul";
              return <List key={index}>{block.items.map((item) => <li key={item}>{inline(item)}</li>)}</List>;
            }
            return <p key={index}>{inline(block.text ?? "")}</p>;
          })}
        </article>
      </main>
      <BusinessFooter locale="es" showClosing={false} business />
    </div>
  );
}
