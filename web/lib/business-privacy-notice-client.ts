import { BUSINESS_PRIVACY_NOTICE_STORAGE_KEY, readSessionStored, writeSessionStored } from "./browser-storage";
import {
  type PrivacyNoticeAcceptance,
  type PrivacyNoticeLocale,
  isPrivacyNoticeLocale,
} from "./business-privacy-notice";

type ReadingSwitch<Reading extends { enabled: boolean; can_change?: boolean }> = {
  receiptReading?: (language: PrivacyNoticeLocale, signal?: AbortSignal) => Promise<Reading>;
  setReceiptReading?: (
    reading: Reading,
    enabled: boolean,
    language: PrivacyNoticeLocale,
    signal?: AbortSignal,
  ) => Promise<Reading>;
};

/**
 * Client for the Cuadrao Business privacy-notice acceptance.
 *
 * No existing endpoint stores this fact. Receipt-reading consent
 * (`POST /business/receipt-reading`) records a different disclosure, locks
 * scope_version to 1, requires a model route, and does not store locale.
 * `business_ai_consents` must not gain a reader. Email consent was dropped.
 * WhatsApp AI consent does not cover the web notice.
 *
 * This stub keeps the acceptance in this tab only. The server contract that
 * should replace it is documented on `BusinessPrivacyNoticeClient`.
 */

export type PrivacyNoticeAcceptInput = {
  userId: string;
  noticeVersion: string;
  locale: PrivacyNoticeLocale;
  textSha256: string;
};

/**
 * Needed backend contract (not implemented in this lane):
 *
 * `GET /api/v1/business/privacy-notice`
 *   200 `PrivacyNoticeAcceptance` for the authenticated user, or 404 when none.
 *   `user_id` comes from the session. The body never names another person.
 *
 * `POST /api/v1/business/privacy-notice`
 *   Header `Idempotency-Key` (1–80 characters).
 *   Body `{ notice_version, locale: "en" | "es-419", text_sha256 }` where
 *   `text_sha256` is the SHA-256 hex of the notice paragraphs shown, joined by
 *   a blank line, in order.
 *   200 the stored row: `user_id`, `accepted_at` (server clock), `notice_version`,
 *   `locale`, `text_sha256`.
 *   Replay of the same key returns the original row. A different body for the
 *   same key is a conflict.
 *
 * Table `business_privacy_notice_acceptances` (service role writes, owner can
 * read their own row): `user_id`, `notice_version`, `locale`, `text_sha256`
 * (64 hex chars), `accepted_at`. Unique `(user_id, notice_version)`. Immutable
 * after insert. Not a substitute for receipt-reading consent.
 */
export interface BusinessPrivacyNoticeClient {
  read(userId: string): Promise<PrivacyNoticeAcceptance | null>;
  accept(input: PrivacyNoticeAcceptInput): Promise<PrivacyNoticeAcceptance>;
}

type StoredAcceptances = Record<string, PrivacyNoticeAcceptance>;

function isAcceptance(value: unknown): value is PrivacyNoticeAcceptance {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<PrivacyNoticeAcceptance>;
  return typeof record.userId === "string"
    && typeof record.acceptedAt === "string"
    && typeof record.noticeVersion === "string"
    && typeof record.locale === "string"
    && isPrivacyNoticeLocale(record.locale)
    && typeof record.textSha256 === "string";
}

export function readStoredAcceptances(): StoredAcceptances {
  const raw = readSessionStored(BUSINESS_PRIVACY_NOTICE_STORAGE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const stored: StoredAcceptances = {};
    for (const [userId, value] of Object.entries(parsed)) {
      if (isAcceptance(value) && value.userId === userId) stored[userId] = value;
    }
    return stored;
  } catch {
    return {};
  }
}

export function readPrivacyNoticeAcceptance(userId: string): PrivacyNoticeAcceptance | null {
  return readStoredAcceptances()[userId] ?? null;
}

export function rememberPrivacyNoticeAcceptance(
  record: PrivacyNoticeAcceptance,
  persist: (value: string) => boolean = (value) => writeSessionStored(BUSINESS_PRIVACY_NOTICE_STORAGE_KEY, value),
): PrivacyNoticeAcceptance {
  const stored = readStoredAcceptances();
  stored[record.userId] = record;
  if (!persist(JSON.stringify(stored))) throw new Error("privacy_notice_not_stored");
  return record;
}

function isMissingBusiness(error: unknown): boolean {
  const problem = error as { status?: number; code?: string } | null;
  return problem?.status === 404 && problem.code === "business_space_missing";
}

/**
 * Decline turns off the owner's stored receipt-reading switch. Upload, email,
 * and WhatsApp intake all read that one setting, so a web-only flag would
 * leave the next receipt free to reach a model.
 *
 * A person with no Business yet has nothing to turn off. A read that says the
 * switch is already off is not the last word when this person can change it:
 * another tab can enable it before we return, so the disable is submitted and
 * its result is checked. A grantee cannot change the owner's switch. When it
 * is already off, decline continues. When it is on, decline stays here.
 */
export async function revokeEnabledReceiptReading<Reading extends { enabled: boolean; can_change?: boolean }>(
  source: ReadingSwitch<Reading>,
  language: PrivacyNoticeLocale,
): Promise<void> {
  if (!source.receiptReading || !source.setReceiptReading) return;
  let reading: Reading;
  try {
    reading = await source.receiptReading(language);
  } catch (error) {
    if (isMissingBusiness(error)) return;
    throw error;
  }
  if (reading.can_change === false) {
    if (reading.enabled) throw new Error("receipt_reading_still_enabled");
    return;
  }
  let next: Reading;
  try {
    next = await source.setReceiptReading(reading, false, language);
  } catch (error) {
    if (isMissingBusiness(error)) return;
    throw error;
  }
  if (next.enabled) throw new Error("receipt_reading_still_enabled");
}

/** In-tab stand-in. `acceptedAt` is stamped here, never taken from the caller. */
export function createStubPrivacyNoticeClient(
  clock: () => string = () => new Date().toISOString(),
): BusinessPrivacyNoticeClient {
  return {
    async read(userId) {
      return readPrivacyNoticeAcceptance(userId);
    },
    async accept(input) {
      return rememberPrivacyNoticeAcceptance({ ...input, acceptedAt: clock() });
    },
  };
}
