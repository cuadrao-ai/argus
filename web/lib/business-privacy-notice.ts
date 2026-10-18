import enCatalog from "@/public/locales/en/common.json";
import esCatalog from "@/public/locales/es-419/common.json";

/**
 * Versioned Cuadrao Business privacy-notice acceptance.
 *
 * TODO(counsel): replace the placeholder copy, then bump
 * BUSINESS_PRIVACY_NOTICE_VERSION in this file. The placeholder lives only in
 * the i18n catalogs, Spanish first:
 * - business.consent.title
 * - business.consent.intro
 * - business.consent.privacy_link
 * - business.consent.opt_in
 * - business.consent.accept
 * - business.consent.decline
 * - business.consent.saving
 * - business.consent.save_error
 * - business.consent.decline_title
 * - business.consent.decline_body
 * - business.consent.continue_without
 * - business.consent.holding
 * - business.consent.hold_error
 * - business.consent.back
 * - business.consent.accepted_title
 * - business.consent.accepted_body
 * - business.consent.continue
 * - business.consent.held
 * - business.consent.review
 * - business.consent.version_label
 * - business.privacy_notice.title
 * - business.privacy_notice.close
 * - business.privacy_notice.paragraphs
 */

export const BUSINESS_PRIVACY_NOTICE_VERSION = "2026-10-18-draft-2";

export const MOCK_AUTH_CONSENT_USER_ID = "mock-auth-user";

export const CONSENT_REQUIRED_FEATURES = ["receipt_reading", "assistant"] as const;

export type ConsentRequiredFeature = (typeof CONSENT_REQUIRED_FEATURES)[number];

export type PrivacyNoticeLocale = "en" | "es-419";

export type PrivacyNoticeAcceptance = {
  userId: string;
  acceptedAt: string;
  noticeVersion: string;
  locale: PrivacyNoticeLocale;
  textSha256: string;
};

export const BUSINESS_CONSENT_I18N_KEYS = [
  "business.consent.title",
  "business.consent.intro",
  "business.consent.privacy_link",
  "business.consent.opt_in",
  "business.consent.accept",
  "business.consent.decline",
  "business.consent.saving",
  "business.consent.save_error",
  "business.consent.decline_title",
  "business.consent.decline_body",
  "business.consent.continue_without",
  "business.consent.holding",
  "business.consent.hold_error",
  "business.consent.back",
  "business.consent.accepted_title",
  "business.consent.accepted_body",
  "business.consent.continue",
  "business.consent.held",
  "business.consent.review",
  "business.consent.version_label",
  "business.privacy_notice.title",
  "business.privacy_notice.close",
] as const;

type NoticeCatalog = {
  business?: { privacy_notice?: { paragraphs?: unknown } };
};

export function noticeParagraphs(locale: PrivacyNoticeLocale): string[] {
  const catalog = (locale === "en" ? enCatalog : esCatalog) as NoticeCatalog;
  const value = catalog.business?.privacy_notice?.paragraphs;
  return Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0) ? value : [];
}

export function noticePlainText(paragraphs: readonly string[]): string {
  return paragraphs.join("\n\n");
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function isPrivacyNoticeLocale(value: string): value is PrivacyNoticeLocale {
  return value === "en" || value === "es-419";
}

export function acceptanceMatchesCurrentNotice(
  record: PrivacyNoticeAcceptance | null | undefined,
  userId: string,
  noticeHashes: Readonly<Record<PrivacyNoticeLocale, string>>,
  version: string = BUSINESS_PRIVACY_NOTICE_VERSION,
): boolean {
  if (!record || record.userId !== userId || record.noticeVersion !== version) return false;
  if (record.acceptedAt.length === 0 || !isPrivacyNoticeLocale(record.locale)) return false;
  return noticeHashes[record.locale] === record.textSha256 && /^[0-9a-f]{64}$/.test(record.textSha256);
}

export async function currentNoticeHashes(): Promise<Record<PrivacyNoticeLocale, string>> {
  return {
    en: await sha256Hex(noticePlainText(noticeParagraphs("en"))),
    "es-419": await sha256Hex(noticePlainText(noticeParagraphs("es-419"))),
  };
}

export function featureRequiresConsent(feature: string): feature is ConsentRequiredFeature {
  return (CONSENT_REQUIRED_FEATURES as readonly string[]).includes(feature);
}

export function featureReachable(feature: string, accepted: boolean): boolean {
  return accepted || !featureRequiresConsent(feature);
}

export function canEnterBusiness(accepted: boolean, grantId: string | null): boolean {
  return accepted || grantId === null;
}

export function canSubmitAcceptance(optedIn: boolean, saving: boolean): boolean {
  return optedIn && !saving;
}
