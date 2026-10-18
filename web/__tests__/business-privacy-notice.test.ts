import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import {
  BUSINESS_CONSENT_I18N_KEYS,
  BUSINESS_PRIVACY_NOTICE_VERSION,
  acceptanceMatchesCurrentNotice,
  canSubmitAcceptance,
  currentNoticeHashes,
  featureReachable,
  featureRequiresConsent,
  noticePlainText,
  noticeParagraphs,
  sha256Hex,
  type PrivacyNoticeAcceptance,
  type PrivacyNoticeLocale,
} from "../lib/business-privacy-notice";
import { rememberPrivacyNoticeAcceptance, revokeEnabledReceiptReading } from "../lib/business-privacy-notice-client";

const USER = "owner-jose";

function acceptance(overrides: Partial<PrivacyNoticeAcceptance> = {}): PrivacyNoticeAcceptance {
  return {
    userId: USER,
    acceptedAt: "2026-10-18T15:00:00.000Z",
    noticeVersion: BUSINESS_PRIVACY_NOTICE_VERSION,
    locale: "es-419",
    textSha256: "ab".repeat(32),
    ...overrides,
  };
}

function lookup(catalog: object, key: string): unknown {
  return key.split(".").reduce<unknown>((value, part) => {
    if (!value || typeof value !== "object") return undefined;
    return (value as Record<string, unknown>)[part];
  }, catalog);
}

describe("business privacy notice version", () => {
  test("a current acceptance for this person skips the screen", async () => {
    const hashes = await currentNoticeHashes();
    const current = acceptance({ locale: "es-419", textSha256: hashes["es-419"] });
    assert.equal(acceptanceMatchesCurrentNotice(current, USER, hashes), true);
  });

  test("a missing, other-person, older, or different notice does not skip the screen", async () => {
    const hashes = await currentNoticeHashes();
    const current = acceptance({ textSha256: hashes["es-419"] });
    assert.equal(acceptanceMatchesCurrentNotice(null, USER, hashes), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ userId: "someone-else", textSha256: hashes["es-419"] }), USER, hashes), false);
    assert.equal(acceptanceMatchesCurrentNotice({ ...current, noticeVersion: "2026-10-01-draft-0" }, USER, hashes), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ textSha256: "not-a-hash" }), USER, hashes), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ textSha256: "ab".repeat(32) }), USER, hashes), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ acceptedAt: "", textSha256: hashes["es-419"] }), USER, hashes), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ locale: "en", textSha256: hashes["es-419"] }), USER, hashes), false);
  });

  test("the same version with edited paragraphs does not skip", async () => {
    const hashes = await currentNoticeHashes();
    const edited = noticePlainText([...noticeParagraphs("es-419").slice(0, -1), "[BORRADOR] Frase distinta."]);
    const stale = acceptance({ textSha256: await sha256Hex(edited) });
    assert.equal(acceptanceMatchesCurrentNotice(stale, USER, hashes), false);
  });

  test("the shown notice text is what the stored hash covers", async () => {
    const shown = noticePlainText(["[BORRADOR] Primera frase.", "[BORRADOR] Segunda frase."]);
    const changed = noticePlainText(["[BORRADOR] Primera frase.", "[BORRADOR] Frase distinta."]);
    const hash = await sha256Hex(shown);
    assert.equal(hash, await sha256Hex(shown));
    assert.notEqual(hash, await sha256Hex(changed));
    assert.match(hash, /^[0-9a-f]{64}$/);
  });
});

describe("business consent gating", () => {
  test("receipt reading and the assistant wait for acceptance", () => {
    for (const feature of ["receipt_reading", "assistant"] as const) {
      assert.equal(featureRequiresConsent(feature), true);
      assert.equal(featureReachable(feature, false), false);
      assert.equal(featureReachable(feature, true), true);
    }
  });

  test("manual recording stays reachable when the notice is declined", () => {
    for (const feature of ["upload_receipt", "record_expense", "review_inbox"]) {
      assert.equal(featureRequiresConsent(feature), false);
      assert.equal(featureReachable(feature, false), true);
    }
  });

  test("accept stays disabled until the person opts in, and while the save is in flight", () => {
    assert.equal(canSubmitAcceptance(false, false), false);
    assert.equal(canSubmitAcceptance(true, true), false);
    assert.equal(canSubmitAcceptance(true, false), true);
  });

  test("a failed tab write is not an acceptance", () => {
    assert.throws(
      () => rememberPrivacyNoticeAcceptance(acceptance(), () => false),
      /privacy_notice_not_stored/,
    );
  });

  test("declining turns off receipt reading even when the read says it is already off", async () => {
    const calls: boolean[] = [];
    await revokeEnabledReceiptReading({
      receiptReading: async () => ({ enabled: false }),
      setReceiptReading: async (_reading, enabled) => {
        calls.push(enabled);
        return { enabled };
      },
    }, "es-419");
    assert.deepEqual(calls, [false]);
  });

  test("a missing Business has no receipt-reading switch to turn off", async () => {
    const missing = Object.assign(new Error("missing"), { status: 404, code: "business_space_missing" });
    let wrote = false;
    await revokeEnabledReceiptReading({
      receiptReading: async () => { throw missing; },
      setReceiptReading: async () => { wrote = true; return { enabled: false }; },
    }, "es-419");
    assert.equal(wrote, false);
  });

  test("declining stays put when receipt reading cannot be turned off", async () => {
    await assert.rejects(() => revokeEnabledReceiptReading({
      receiptReading: async () => ({ enabled: true }),
      setReceiptReading: async () => ({ enabled: true }),
    }, "en" satisfies PrivacyNoticeLocale));
  });

  test("declining does nothing when this source has no receipt-reading switch", async () => {
    await revokeEnabledReceiptReading({}, "es-419");
  });

  test("another failure while turning receipt reading off stays on the decline screen", async () => {
    await assert.rejects(() => revokeEnabledReceiptReading({
      receiptReading: async () => { throw new Error("offline"); },
      setReceiptReading: async () => ({ enabled: false }),
    }, "es-419"));
  });
});

describe("placeholder notice copy", () => {
  test("every consent string is in both catalogs and marked as a draft", () => {
    for (const key of BUSINESS_CONSENT_I18N_KEYS) {
      const spanish = lookup(es, key);
      const english = lookup(en, key);
      assert.equal(typeof spanish, "string", key);
      assert.equal(typeof english, "string", key);
      assert.equal(String(spanish).startsWith("[BORRADOR]"), true, key);
      assert.equal(String(english).startsWith("[DRAFT]"), true, key);
    }
    for (const paragraph of es.business.privacy_notice.paragraphs) {
      assert.equal(paragraph.startsWith("[BORRADOR]"), true);
    }
    for (const paragraph of en.business.privacy_notice.paragraphs) {
      assert.equal(paragraph.startsWith("[DRAFT]"), true);
    }
    assert.equal(es.business.privacy_notice.paragraphs.length, en.business.privacy_notice.paragraphs.length);
  });
});
