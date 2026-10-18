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

/** Bump when the notice text the person sees changes. */
export const BUSINESS_PRIVACY_NOTICE_VERSION = "2026-10-18-draft-1";

/** Signed-in identity while mock auth has no Supabase user. */
export const MOCK_AUTH_CONSENT_USER_ID = "mock-auth-user";

/**
 * Features that send business data to a model. Manual recording stays available
 * when the notice is declined. Docs: connected-flow spec (the owner can finish
 * the work without AI) and the privacy draft, section 4.
 */
export const CONSENT_REQUIRED_FEATURES = ["receipt_reading", "assistant"] as const;

export type ConsentRequiredFeature = (typeof CONSENT_REQUIRED_FEATURES)[number];

export type PrivacyNoticeLocale = "en" | "es-419";

/** Who accepted, when, which notice, which locale, and a hash of the text shown. */
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

/** The notice body, in the order it is shown. The hash covers this text. */
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

/** A returning person skips the screen only for this user and this notice version. */
export function acceptanceMatchesCurrentNotice(
  record: PrivacyNoticeAcceptance | null | undefined,
  userId: string,
  version: string = BUSINESS_PRIVACY_NOTICE_VERSION,
): boolean {
  if (!record || record.userId !== userId || record.noticeVersion !== version) return false;
  return record.acceptedAt.length > 0 && isPrivacyNoticeLocale(record.locale) && /^[0-9a-f]{64}$/.test(record.textSha256);
}

export function featureRequiresConsent(feature: string): feature is ConsentRequiredFeature {
  return (CONSENT_REQUIRED_FEATURES as readonly string[]).includes(feature);
}

/** Manual work stays reachable. Model features wait for the current notice. */
export function featureReachable(feature: string, accepted: boolean): boolean {
  return accepted || !featureRequiresConsent(feature);
}

/** Accept stays disabled until the person actively opts in. */
export function canSubmitAcceptance(optedIn: boolean, saving: boolean): boolean {
  return optedIn && !saving;
}
