import { BUSINESS_PRIVACY_NOTICE_STORAGE_KEY, readSessionStored, writeSessionStored } from "./browser-storage";
import { setChosenGrant } from "./business-grant";
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

export type PrivacyNoticeAcceptInput = {
  userId: string;
  noticeVersion: string;
  locale: PrivacyNoticeLocale;
  textSha256: string;
};

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

export async function revokeEnabledReceiptReading<Reading extends { enabled: boolean; can_change?: boolean }>(
  source: ReadingSwitch<Reading>,
  language: PrivacyNoticeLocale,
): Promise<void> {
  setChosenGrant(null);
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
