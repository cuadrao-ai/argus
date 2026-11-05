/**
 * The one owner of the Cuadrao legal URLs. Terms and Privacy default to the
 * published pages (the same ones iOS opens); a non-blank setting overrides
 * each. Data deletion has no published page yet, so it stays empty, and a
 * surface hides that link, until its setting names one.
 * Next inlines only literal `process.env.NAME` reads, so each is spelled out.
 */
export const PUBLISHED_TERMS_URL = "https://cuadrao.ai/terminos";
export const PUBLISHED_PRIVACY_URL = "https://cuadrao.ai/privacidad";

export type CuadraoLegalLinks = {
  terms: string;
  privacy: string;
  dataDeletion: string | undefined;
};

function configured(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function cuadraoLegalLinks(): CuadraoLegalLinks {
  return {
    terms: configured(process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL) ?? PUBLISHED_TERMS_URL,
    privacy: configured(process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL) ?? PUBLISHED_PRIVACY_URL,
    dataDeletion: configured(process.env.NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL),
  };
}

export type AcceptanceLinks = { terms: string; privacy: string };

/** The acceptance sentence names both documents. */
export function acceptanceLinks(): AcceptanceLinks {
  const { terms, privacy } = cuadraoLegalLinks();
  return { terms, privacy };
}
