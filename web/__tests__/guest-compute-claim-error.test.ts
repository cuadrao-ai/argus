import { describe, expect, test } from "bun:test";
import { tFromCatalog } from "./support/catalog-translator";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

import { chatHttpErrorDisplay } from "../components/chat/chat-message-projection";
import { ChatStreamError, streamChatMessage } from "../lib/argus-api";
import { retryLastTurnChatActionFromAction } from "../lib/chat-retry-actions";
import { discoveryCandidateMention } from "../lib/chat-discovery-sidecar";
import {
  REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE,
  GUEST_COMPUTE_CLAIM_RETRY_IN_KEY,
  GUEST_COMPUTE_CLAIM_UNAVAILABLE_CODE,
  claimErrorKeepsLocalTranscript,
  claimErrorMessagePatch,
  claimErrorRetryAction,
  admissionErrorTerminalPayload,
  computeClaimTransportPatch,
  settleAdmissionTransportReadiness,
  localizedComputeClaimMessage,
} from "../lib/compute-claim-error";
import { recoveryDisplayText } from "../lib/chat-recovery-display";
import {
  isHttpRetryAfterDate,
  parseRetryAfterSeconds,
  remainingRetryAfterSeconds,
  shouldKeepRetryAfterTicker,
  RETRY_AFTER_FALLBACK_SECONDS,
  RETRY_AFTER_MAX_SECONDS,
  RETRY_AFTER_MIN_SECONDS,
} from "../lib/retry-after";

const root = join(import.meta.dir, "..");
const enCatalog = JSON.parse(
  readFileSync(join(root, "public/locales/en/common.json"), "utf8"),
) as Record<string, unknown>;
const esCatalog = JSON.parse(
  readFileSync(join(root, "public/locales/es-419/common.json"), "utf8"),
) as Record<string, unknown>;

const RAW_SERVER_DETAIL = "Argus could not start this turn. Please try again.";
const EN_COPY = "Cuadrao could not start this turn. Try again in a moment.";
const ES_COPY = "Cuadrao no pudo iniciar este turno. Inténtalo de nuevo en un momento.";
const EM_DASH = "\u2014";

function catalogString(
  catalog: Record<string, unknown>,
  key: string,
): string {
  const value = key.split(".").reduce<unknown>((current, segment) => {
    if (typeof current !== "object" || current === null) return undefined;
    return (current as Record<string, unknown>)[segment];
  }, catalog);
  if (typeof value !== "string") {
    throw new Error(`missing locale string ${key}`);
  }
  return value;
}

describe("Retry-After parsing", () => {
  test("reads delta-seconds", () => {
    expect(parseRetryAfterSeconds("15")).toBe(15);
    expect(parseRetryAfterSeconds("1")).toBe(1);
    expect(parseRetryAfterSeconds("120")).toBe(120);
  });

  test("reads an HTTP-date relative to now", () => {
    const nowMs = Date.parse("Fri, 25 Sep 2026 12:00:00 GMT");
    expect(
      parseRetryAfterSeconds("Fri, 25 Sep 2026 12:00:08 GMT", nowMs),
    ).toBe(8);
  });

  test("falls back when the header is missing or garbage", () => {
    expect(parseRetryAfterSeconds(null)).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds(undefined)).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("   ")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("soon")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("15s")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("not-a-http-date")).toBe(
      RETRY_AFTER_FALLBACK_SECONDS,
    );
    expect(parseRetryAfterSeconds("-5")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("1.5")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("abc")).toBe(RETRY_AFTER_FALLBACK_SECONDS);
    expect(parseRetryAfterSeconds("Sep 25 2026")).toBe(
      RETRY_AFTER_FALLBACK_SECONDS,
    );
  });

  test("accepts only IMF-fixdate, RFC 850, or asctime HTTP-dates", () => {
    expect(isHttpRetryAfterDate("Fri, 25 Sep 2026 12:00:08 GMT")).toBe(true);
    expect(isHttpRetryAfterDate("Friday, 25-Sep-26 12:00:08 GMT")).toBe(true);
    expect(isHttpRetryAfterDate("Fri Sep 25 12:00:08 2026")).toBe(true);
    expect(isHttpRetryAfterDate("Fri Sep  5 12:00:08 2026")).toBe(true);
    expect(isHttpRetryAfterDate("Fri, 25 Sep 2026")).toBe(false);
    expect(isHttpRetryAfterDate("2026-09-25T12:00:08.000Z")).toBe(false);
    expect(isHttpRetryAfterDate("-5")).toBe(false);
    expect(isHttpRetryAfterDate("1.5")).toBe(false);
    expect(isHttpRetryAfterDate("")).toBe(false);
    expect(isHttpRetryAfterDate("abc")).toBe(false);
    const nowMs = Date.parse("Fri, 25 Sep 2026 12:00:00 GMT");
    expect(
      parseRetryAfterSeconds("Friday, 25-Sep-26 12:00:08 GMT", nowMs),
    ).toBe(8);
    const asctime = "Fri Sep 25 12:00:08 2026";
    expect(
      parseRetryAfterSeconds(asctime, nowMs),
    ).toBe(8);
  });

  test.each(["America/Los_Angeles", "Asia/Tokyo"])(
    "parses asctime as GMT in %s, including a space-padded day",
    (timeZone) => {
      const script = `
        import { parseRetryAfterSeconds } from ${JSON.stringify(join(root, "lib/retry-after.ts"))};
        console.log(JSON.stringify([
          parseRetryAfterSeconds("Fri Sep 25 12:00:08 2026", Date.parse("2026-09-25T12:00:00Z")),
          parseRetryAfterSeconds("Sat Sep  5 12:00:08 2026", Date.parse("2026-09-05T12:00:00Z")),
        ]));
      `;
      const result = spawnSync(process.execPath, ["--eval", script], {
        env: { ...process.env, TZ: timeZone }, encoding: "utf8",
      });
      expect(result.status).toBe(0);
      expect(JSON.parse(result.stdout)).toEqual([8, 8]);
    },
  );

  test("clamps huge, zero, and past values into 1..120", () => {
    expect(parseRetryAfterSeconds("0")).toBe(RETRY_AFTER_MIN_SECONDS);
    expect(parseRetryAfterSeconds("999999")).toBe(RETRY_AFTER_MAX_SECONDS);
    const nowMs = Date.parse("Fri, 25 Sep 2026 12:00:00 GMT");
    expect(
      parseRetryAfterSeconds("Wed, 21 Oct 2015 07:28:00 GMT", nowMs),
    ).toBe(RETRY_AFTER_MIN_SECONDS);
    expect(
      parseRetryAfterSeconds("Fri, 25 Sep 2026 16:00:00 GMT", nowMs),
    ).toBe(RETRY_AFTER_MAX_SECONDS);
  });

  test("remaining seconds never go negative", () => {
    expect(remainingRetryAfterSeconds(undefined, 1_000)).toBe(0);
    expect(remainingRetryAfterSeconds(1_500, 1_000)).toBe(1);
    expect(remainingRetryAfterSeconds(500, 1_000)).toBe(0);
  });

  test("a newly assigned deadline is unreadied on the same clock read", () => {
    const mountedAtMs = 1_000;
    expect(remainingRetryAfterSeconds(undefined, mountedAtMs)).toBe(0);
    const availableAtMs = mountedAtMs + 15_000;
    expect(remainingRetryAfterSeconds(availableAtMs, mountedAtMs)).toBe(15);
    expect(remainingRetryAfterSeconds(availableAtMs, availableAtMs - 1)).toBe(1);
    expect(remainingRetryAfterSeconds(availableAtMs, availableAtMs)).toBe(0);
    const laterDeadlineMs = availableAtMs + 8_000;
    expect(remainingRetryAfterSeconds(laterDeadlineMs, availableAtMs)).toBe(8);
    expect(shouldKeepRetryAfterTicker(availableAtMs, mountedAtMs)).toBe(true);
    expect(shouldKeepRetryAfterTicker(availableAtMs, availableAtMs)).toBe(false);
    expect(shouldKeepRetryAfterTicker(undefined, mountedAtMs)).toBe(false);
  });
});

describe.each([
  GUEST_COMPUTE_CLAIM_UNAVAILABLE_CODE,
  REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE,
] as const)("%s recovery", (claimCode) => {
  test("maps the 503 claim code to English and es-419 catalogs", () => {
    const projected = chatHttpErrorDisplay(
      claimCode,
      RAW_SERVER_DETAIL,
    );

    expect(projected.content).toBe("");
    expect(projected.recoveryDisplay).toEqual({
      kind: "recovery_code",
      code: claimCode,
    });
    expect(
      recoveryDisplayText(projected.recoveryDisplay, tFromCatalog(enCatalog)),
    ).toBe(EN_COPY);
    expect(
      recoveryDisplayText(projected.recoveryDisplay, tFromCatalog(esCatalog)),
    ).toBe(ES_COPY);
    expect(
      recoveryDisplayText(projected.recoveryDisplay, tFromCatalog(enCatalog)),
    ).not.toBe(RAW_SERVER_DETAIL);
    expect(
      recoveryDisplayText(projected.recoveryDisplay, tFromCatalog(esCatalog)),
    ).not.toContain(RAW_SERVER_DETAIL);
  });

  test("never renders raw server text for the claim code", () => {
    expect(
      localizedComputeClaimMessage(
        claimCode,
        tFromCatalog(enCatalog),
        RAW_SERVER_DETAIL,
      ),
    ).toBe(EN_COPY);
    expect(
      localizedComputeClaimMessage(
        claimCode,
        tFromCatalog(esCatalog),
        RAW_SERVER_DETAIL,
      ),
    ).toBe(ES_COPY);
    expect(
      localizedComputeClaimMessage(
        "stream_interrupted",
        tFromCatalog(enCatalog),
        RAW_SERVER_DETAIL,
      ),
    ).toBe(RAW_SERVER_DETAIL);
  });

  test("keeps unrelated HTTP errors on the backend message", () => {
    expect(
      chatHttpErrorDisplay("artifact_action_invalid_state", RAW_SERVER_DETAIL),
    ).toEqual({
      content: RAW_SERVER_DETAIL,
      recoveryDisplay: null,
    });
  });

  test("new claim strings contain no em dash", () => {
    const keys = [
      `chat.recovery.${claimCode}`,
      `${GUEST_COMPUTE_CLAIM_RETRY_IN_KEY}_one`,
      `${GUEST_COMPUTE_CLAIM_RETRY_IN_KEY}_other`,
    ];
    for (const catalog of [enCatalog, esCatalog]) {
      for (const key of keys) {
        const value = catalogString(catalog, key);
        expect(value, key).not.toContain(EM_DASH);
        expect(value.includes("—"), key).toBe(false);
      }
    }
  });

  test("attaches one retry control that waits for Retry-After", () => {
    const nowMs = Date.parse("Fri, 25 Sep 2026 12:00:00 GMT");
    const patch = computeClaimTransportPatch({
      code: claimCode,
      retryAfterHeader: "8",
      retryAction: {
        id: "retry-last-turn",
        label: "Retry",
        labelKey: "common.retry",
        type: "retry_last_turn",
        payload: { message: "Compare Apple with SPY" },
      },
      nowMs,
    });

    expect(patch?.assistantRecoveryCode).toBe(
      claimCode,
    );
    expect(patch?.actions?.[0]?.availableAtMs).toBe(nowMs + 8_000);
    expect(patch?.actions?.[0]?.payload).toEqual({
      message: "Compare Apple with SPY",
    });
    expect(
      computeClaimTransportPatch({
        code: "too_many_requests",
        retryAfterHeader: "8",
        retryAction: {
          id: "retry-last-turn",
          label: "Retry",
          type: "retry_last_turn",
        },
      }),
    ).toEqual({});
  });

  test("streamChatMessage keeps Retry-After on a 503 claim error", async () => {
    const originalFetch = globalThis.fetch;
    const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          code: claimCode,
          detail: RAW_SERVER_DETAIL,
        }),
        {
          status: 503,
          headers: {
            "Content-Type": "application/problem+json",
            "Retry-After": "8",
            "X-Request-Id": "claim-503",
          },
        },
      )) as typeof fetch;

    let caught: unknown;
    try {
      await streamChatMessage("conversation-1", "Compare Apple with SPY", "en", () => {});
    } catch (err) {
      caught = err;
    } finally {
      globalThis.fetch = originalFetch;
      if (originalMockAuth === undefined) {
        delete process.env.NEXT_PUBLIC_MOCK_AUTH;
      } else {
        process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
      }
    }

    expect(caught).toBeInstanceOf(ChatStreamError);
    const error = caught as ChatStreamError;
    expect(error.status).toBe(503);
    expect(error.code).toBe(claimCode);
    expect(error.retryAfter).toBe("8");
    expect(error.message).toBe(RAW_SERVER_DETAIL);
  });

  test("a later claim 503 keeps the local turn and rebuilds Retry", () => {
    const nowMs = Date.parse("Fri, 25 Sep 2026 12:00:00 GMT");
    expect(
      claimErrorKeepsLocalTranscript(claimCode),
    ).toBe(true);
    expect(claimErrorKeepsLocalTranscript("too_many_requests")).toBe(false);
    expect(admissionErrorTerminalPayload("assistant-claim-1", claimCode)).toEqual({
      message_id: "assistant-claim-1",
      recovery: { code: claimCode },
    });

    const rebuilt = claimErrorRetryAction({
      code: claimCode,
      retryAction: {
        id: "retry-last-turn",
        label: "Retry",
        type: "retry_last_turn",
        payload: { message: "Compare Apple with SPY" },
      },
      message: "Compare Apple with SPY",
      assistantMessageId: "assistant-claim-1",
    });
    expect(rebuilt?.type).toBe("retry_last_turn");
    expect(rebuilt?.payload).toEqual({
      message: "Compare Apple with SPY",
    });
    expect(
      claimErrorRetryAction({
        code: claimCode,
        retryAction: null,
        message: "AAPL",
        assistantMessageId: "assistant-claim-1",
      }),
    ).toBeNull();

    const later = claimErrorMessagePatch({
      code: claimCode,
      retryAfterHeader: "4",
      retryAction: rebuilt,
      message: "Compare Apple with SPY",
      assistantMessageId: "assistant-claim-1",
      nowMs,
    });
    expect(later.actions?.[0]?.availableAtMs).toBe(nowMs + 4_000);
    const accepts: unknown[] = [];
    const finishes: boolean[] = [];
    settleAdmissionTransportReadiness(
      {
        reject: () => false,
        accept: (payload, authorized) => {
          accepts.push({ payload, authorized });
          return authorized;
        },
        finish: (authorized) => {
          finishes.push(authorized);
          return false;
        },
      },
      { kind: "recovery_code", code: claimCode },
      "assistant-claim-1",
      true,
    );
    expect(accepts).toEqual([
      {
        payload: admissionErrorTerminalPayload("assistant-claim-1", claimCode),
        authorized: true,
      },
    ]);
    expect(finishes).toEqual([true]);
    expect(
      claimErrorRetryAction({
        code: "too_many_requests",
        retryAction: null,
        message: "Compare Apple with SPY",
        assistantMessageId: "assistant-claim-1",
      }),
    ).toBeNull();
  });

  test("a claim 503 on a discovery pick keeps the original action on Retry", () => {
    const discoveryAction = {
      type: "select_discovery_candidate" as const,
      label: "AAPL",
      payload: {
        symbol: "AAPL",
        name: "Apple Inc.",
        asset_class: "equity",
      },
    };
    const rebuilt = claimErrorRetryAction({
      code: claimCode,
      retryAction: null,
      message: "AAPL",
      assistantMessageId: "assistant-claim-2",
      chatAction: discoveryAction,
    });
    expect(rebuilt?.type).toBe("retry_last_turn");
    expect(rebuilt?.payload).toEqual({
      message: "AAPL",
      failed_assistant_id: "assistant-claim-2",
      chat_action: discoveryAction,
    });
    const replayed = retryLastTurnChatActionFromAction(rebuilt);
    expect(replayed).toEqual(discoveryAction);
    expect(discoveryCandidateMention(replayed!)).toEqual({
      id: "asset:equity:AAPL",
      type: "asset",
      label: "Apple Inc.",
      symbol: "AAPL",
      asset_class: "equity",
      insert_text: "AAPL",
    });
  });

  test("the claim 503 catch keeps local messages and the retry path does not reload empty", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf8",
    );
    expect(chat).toContain("keepLocalTranscript");
    expect(chat).toContain("if (!options?.keepLocalTranscript)");
    expect(chat).toContain("applyChatHttpErrorToMessages(");
    expect(chat).toContain("settleAdmissionTransportReadiness(terminalReadiness, httpErrorDisplay.recoveryDisplay, assistantId,");
    expect(chat).toContain("retryLastTurnSendOptions({ failedAssistantId, requestMessageId })");
  });

  test("countdown labels localize without raw server text", () => {
    expect(
      tFromCatalog(enCatalog)(GUEST_COMPUTE_CLAIM_RETRY_IN_KEY, { count: 1 }),
    ).toBe("Retry in 1 second");
    expect(
      tFromCatalog(enCatalog)(GUEST_COMPUTE_CLAIM_RETRY_IN_KEY, { count: 15 }),
    ).toBe("Retry in 15 seconds");
    expect(
      tFromCatalog(esCatalog)(GUEST_COMPUTE_CLAIM_RETRY_IN_KEY, { count: 1 }),
    ).toBe("Reintentar en 1 segundo");
    expect(
      tFromCatalog(esCatalog)(GUEST_COMPUTE_CLAIM_RETRY_IN_KEY, { count: 15 }),
    ).toBe("Reintentar en 15 segundos");
  });
});
