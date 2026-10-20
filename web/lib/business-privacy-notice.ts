import enCatalog from "@/public/locales/en/common.json";
import esCatalog from "@/public/locales/es-419/common.json";

export const MOCK_AUTH_CONSENT_USER_ID = "mock-auth-user";

export type PrivacyNoticeLocale = "en" | "es-419";

/** Every word of the Business consent screen, Spanish first, in screen order. */
export const BUSINESS_CONSENT_I18N_KEYS = [
  "business.consent.title",
  "business.consent.body",
  "business.consent.opt_in",
  "business.consent.continue",
  "business.consent.privacy_link",
] as const;

type Catalog = Record<string, unknown>;

const CATALOGS: Record<PrivacyNoticeLocale, Catalog> = { en: enCatalog, "es-419": esCatalog };

function lookup(catalog: Catalog, key: string): unknown {
  return key.split(".").reduce<unknown>(
    (value, part) => (value && typeof value === "object" ? (value as Catalog)[part] : undefined),
    catalog,
  );
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function shownWords(locale: PrivacyNoticeLocale): unknown[] {
  const catalog = CATALOGS[locale];
  const words = BUSINESS_CONSENT_I18N_KEYS.filter((key) => key !== "business.consent.privacy_link")
    .map((key) => lookup(catalog, key));
  if (!privacyNoticePublished(locale)) return words;
  return [
    ...words,
    lookup(catalog, "business.consent.privacy_link"),
    lookup(catalog, "business.privacy_notice.title"),
    ...noticeParagraphs(locale),
  ];
}

/**
 * The wording a person accepts, named by what the screen shows, the notice
 * behind its link included: changing any of it in either language is a new
 * wording, and everyone is asked again.
 */
export async function consentCopyVersion(): Promise<string> {
  const words = (["es-419", "en"] as const).map(shownWords);
  return (await sha256Hex(JSON.stringify(words))).slice(0, 16);
}

export function noticeParagraphs(locale: PrivacyNoticeLocale): string[] {
  const value = lookup(CATALOGS[locale], "business.privacy_notice.paragraphs");
  return Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0) ? value : [];
}

/**
 * The Business privacy notice is a draft until its text is in the catalog.
 * While it is a draft, nothing links to it.
 */
export function privacyNoticePublished(locale: PrivacyNoticeLocale): boolean {
  const catalog = CATALOGS[locale];
  return typeof lookup(catalog, "business.privacy_notice.title") === "string"
    && typeof lookup(catalog, "business.privacy_notice.close") === "string"
    && noticeParagraphs(locale).length > 0;
}

export function canEnterBusiness(accepted: boolean, grantId: string | null): boolean {
  return accepted || grantId === null;
}
