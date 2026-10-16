/**
 * The one owner of the published Cuadrao legal URLs. Each is empty until the
 * page is published. A surface hides a link while its URL is empty, and the
 * acceptance sentence renders only through `acceptanceLinks()`.
 * Next inlines only literal `process.env.NAME` reads, so each is spelled out.
 */
export type CuadraoLegalLinks = {
  terms: string | undefined;
  privacy: string | undefined;
  dataDeletion: string | undefined;
};

function published(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function cuadraoLegalLinks(): CuadraoLegalLinks {
  return {
    terms: published(process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL),
    privacy: published(process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL),
    dataDeletion: published(process.env.NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL),
  };
}

export type AcceptanceLinks = { terms: string; privacy: string };

/** The acceptance sentence names both documents, so it renders only when both are published. */
export function acceptanceLinks(): AcceptanceLinks | null {
  const { terms, privacy } = cuadraoLegalLinks();
  return terms && privacy ? { terms, privacy } : null;
}
