/**
 * The one owner of the Cuadrao legal URLs. Terms and Privacy default to the
 * published app pages in the reader's language; a non-blank setting overrides
 * each, for every language. Data deletion has no published page yet, so it
 * stays empty, and a surface hides that link, until its setting names one.
 * Next inlines only literal `process.env.NAME` reads, so each is spelled out.
 */
export type LegalLanguage = "es" | "en";

export const PUBLISHED_LEGAL_URLS: Record<LegalLanguage, { terms: string; privacy: string }> = {
  es: { terms: "https://cuadrao.ai/app/terminos", privacy: "https://cuadrao.ai/app/privacidad" },
  en: { terms: "https://cuadrao.ai/en/app/terms", privacy: "https://cuadrao.ai/en/app/privacy" },
};

export type CuadraoLegalLinks = {
  terms: string;
  privacy: string;
  dataDeletion: string | undefined;
};

function configured(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

/** English readers get the English pages; every other language, or none yet, gets the Spanish ones. */
export function legalLanguage(language: string | null | undefined): LegalLanguage {
  return language?.toLowerCase().startsWith("en") ? "en" : "es";
}

export function cuadraoLegalLinks(language?: string | null): CuadraoLegalLinks {
  const published = PUBLISHED_LEGAL_URLS[legalLanguage(language)];
  return {
    terms: configured(process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL) ?? published.terms,
    privacy: configured(process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL) ?? published.privacy,
    dataDeletion: configured(process.env.NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL),
  };
}

export type AcceptanceLinks = { terms: string; privacy: string };

/** The acceptance sentence names both documents. */
export function acceptanceLinks(language?: string | null): AcceptanceLinks {
  const { terms, privacy } = cuadraoLegalLinks(language);
  return { terms, privacy };
}
