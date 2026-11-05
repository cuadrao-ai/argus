import { describe, expect, test } from "bun:test";
import type { Message } from "../components/chat/types";
import {
  applyChatHttpErrorToMessages,
  chatHttpErrorDisplay,
} from "../components/chat/chat-message-projection";
import {
  createConversationActivityTerminalReadinessSession,
  createConversationActivityTranscriptReadiness,
} from "../components/chat/useConversationActivityViewport";
import {
  REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE,
  settleAdmissionTransportReadiness,
} from "../lib/compute-claim-error";
import { retryLastTurnActionFromMessage } from "../lib/chat-retry-actions";

const nowMs = Date.parse("2026-09-26T18:00:00Z");
const messages = (): Message[] => [
  { id: "prior", role: "ai", content: "Which idea would you like to test?" },
  { id: "question", role: "user", content: "Compare Apple with SPY" },
  { id: "pending", role: "ai", content: "" },
];
const capDisplay = () => chatHttpErrorDisplay("too_many_requests", "Internal detail", {
  status: 429, retryAfter: "21600", nowMs,
});

describe("chat admission rejection", () => {
  test("a daily cap preserves the question without manufacturing an assistant turn", () => {
    const before = messages();
    const after = applyChatHttpErrorToMessages(before, capDisplay(), {
      code: "too_many_requests", retryAfterHeader: "21600", retryAction: null,
      message: before[1].content, assistantMessageId: before[2].id, nowMs,
    });
    expect(after).toEqual(before.slice(0, 2));
    expect(before).toHaveLength(3);
  });

  test("claim failures retain the existing Retry action and its shared countdown", () => {
    const before = messages();
    const retryAction = retryLastTurnActionFromMessage(before[1].content, {
      assistantMessageId: before[2].id,
    });
    const code = REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE;
    const display = chatHttpErrorDisplay(code, "Internal detail");
    const after = applyChatHttpErrorToMessages(before, display, {
      code, retryAfterHeader: "15", retryAction,
      message: before[1].content, assistantMessageId: before[2].id, nowMs,
    });
    expect(after.slice(0, 2)).toEqual(before.slice(0, 2));
    expect(after[2]).toMatchObject({
      content: "", recoveryDisplay: display.recoveryDisplay,
      assistantRecoveryCode: code,
      actions: [{ ...retryAction, availableAtMs: nowMs + 15_000 }],
    });
  });

  test("stale confirmation rejections keep their structured recovery", () => {
    const before = messages();
    const code = "confirmation_action_stale_card";
    const after = applyChatHttpErrorToMessages(before, chatHttpErrorDisplay(code, "Internal detail"), {
      code, retryAfterHeader: null, retryAction: null,
      message: before[1].content, assistantMessageId: before[2].id,
    });
    expect(after[2]).toMatchObject({ content: "", recoveryDisplay: { kind: "recovery_code", code } });
  });

  test.each([true, false])("daily-cap readiness preserves local state only for an authorized request: %s", (authorized) => {
    const conversationId = "active-conversation";
    const readiness = createConversationActivityTranscriptReadiness();
    const reconciled: string[] = [];
    const readyRef = { current: null as string | null };
    const session = createConversationActivityTerminalReadinessSession({
      getRequest: () => ({ conversationId, kind: "chat_turn" }),
      activeConversationIdRef: { current: conversationId },
      currentViewRef: { current: "chat" },
      readyTranscriptConversationIdRef: readyRef,
      transcriptReadiness: readiness,
      reconcileCanonical: (id) => { reconciled.push(id); },
    });
    session.stage();
    settleAdmissionTransportReadiness(session, capDisplay().recoveryDisplay, "pending", authorized);
    expect(readiness.snapshot(conversationId).canonicalReady).toBe(authorized);
    expect(readyRef.current).toBe(authorized ? conversationId : null);
    expect(reconciled).toEqual([]);
  });
});
