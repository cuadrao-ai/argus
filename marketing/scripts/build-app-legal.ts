import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { APP_LEGAL_SLUGS } from "../lib/app-legal";
import { parseBilingualLegalMarkdown, type LegalDocument } from "../lib/legal-markdown";

const content = join(import.meta.dir, "../content");
const out: Record<"es" | "en", Record<string, LegalDocument>> = { es: {}, en: {} };
for (const slug of APP_LEGAL_SLUGS) {
  const parsed = parseBilingualLegalMarkdown(readFileSync(join(content, "app-legal-source", `${slug}.md`), "utf8"));
  out.es[slug] = parsed.es;
  out.en[slug] = parsed.en;
}
for (const locale of ["es", "en"] as const) {
  writeFileSync(join(content, `app-legal-${locale}.json`), `${JSON.stringify(out[locale], null, 2)}\n`);
}
