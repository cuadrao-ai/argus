import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import {
  BUSINESS_CONSENT_I18N_KEYS,
  BUSINESS_PRIVACY_NOTICE_VERSION,
  acceptanceMatchesCurrentNotice,
  canSubmitAcceptance,
  featureReachable,
  featureRequiresConsent,
  noticePlainText,
  sha256Hex,
  type PrivacyNoticeAcceptance,
} from "../lib/business-privacy-notice";

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
  test("a current acceptance for this person skips the screen", () => {
    assert.equal(acceptanceMatchesCurrentNotice(acceptance(), USER), true);
  });

  test("a missing, other-person, or older notice does not skip the screen", () => {
    assert.equal(acceptanceMatchesCurrentNotice(null, USER), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ userId: "someone-else" }), USER), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ noticeVersion: "2026-10-01-draft-0" }), USER), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ textSha256: "not-a-hash" }), USER), false);
    assert.equal(acceptanceMatchesCurrentNotice(acceptance({ acceptedAt: "" }), USER), false);
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
