import { describe, expect, test } from "bun:test";

import {
  conversationLoadRetryActionFromConversationId,
  failedActionRetryActionFromMetadata,
  hasFailedActionMetadata,
  retryLastTurnActionFromMetadata,
  retryLastTurnActionFromMessage,
  retryLastTurnChatActionFromAction,
  retryLoadConversationIdFromAction,
  retryLastTurnMessageFromAction,
  retryLastTurnRequestMessageIdFromAction,
  retryLastTurnSendOptions,
  isRetryAction,
  normalizeDurableRetryActionHistory,
} from "../lib/chat-retry-actions";
import type { Message } from "../components/chat/types";

describe("failed-action retry UI contract", () => {
  test("hydrates a retry action from retryable failed-action metadata", () => {
    const action = failedActionRetryActionFromMetadata({
      latest_failed_action_reference: {
        artifact_kind: "failed_action",
        artifact_id: "failed-1",
        artifact_status: "failed",
        metadata: {
          retryable: true,
          launch_payload: {
            strategy_type: "buy_and_hold",
            symbols: ["AAPL"],
          },
        },
      },
    });

    expect(action).toEqual({
      id: "retry-failed-action-failed-1",
      label: "Retry",
      labelKey: "common.retry",
      value: "Retry",
      type: "retry_failed_action",
      artifactId: "failed-1",
      artifactType: "failed_action",
      artifactStatus: "failed",
      payload: { failed_action_id: "failed-1" },
    });
  });

  test("does not hydrate retry when failed action can only reopen its confirmation", () => {
    const metadata = {
      latest_failed_action_reference: {
        artifact_kind: "failed_action",
        artifact_id: "failed-invalid-date",
        artifact_status: "failed",
        metadata: {
          retryable: false,
          recovery_mode: "reopen_confirmation",
          launch_payload: {
            strategy_type: "buy_and_hold",
            symbols: ["AAPL"],
          },
        },
      },
    };
    const action = failedActionRetryActionFromMetadata(metadata);

    expect(action).toBeNull();
    expect(hasFailedActionMetadata(metadata)).toBe(true);
  });

  test("does not hydrate retry when metadata has no recoverable launch context", () => {
    expect(
      failedActionRetryActionFromMetadata({
        latest_failed_action_reference: {
          artifact_kind: "failed_action",
          artifact_id: "failed-2",
          artifact_status: "failed",
          metadata: {
            retryable: false,
            recovery_mode: "none",
            launch_payload: {
              strategy_type: "buy_and_hold",
              symbols: ["MSFT"],
            },
          },
        },
      }),
    ).toBeNull();

    expect(
      failedActionRetryActionFromMetadata({
        failed_action: {
          artifact_id: "failed-3",
          retryable: true,
        },
      }),
    ).toBeNull();
  });

  test("hydrates from legacy fallback failed_action metadata without prose matching", () => {
    const action = failedActionRetryActionFromMetadata({
      failed_action: {
        artifact_id: "failed-legacy",
        artifact_status: "failed",
        retryable: true,
        launch_payload: {
          strategy_type: "dca_accumulation",
          symbols: ["NVDA"],
        },
      },
    });

    expect(action?.artifactId).toBe("failed-legacy");
    expect(action?.artifactType).toBe("failed_action");
    expect(action?.type).toBe("retry_failed_action");
    expect(action?.value).toBe("Retry");
  });

  test("does not hydrate retryable failed-action metadata without an artifact id", () => {
    const metadata = {
      failed_action: {
        artifact_status: "failed",
        retryable: true,
        launch_payload: {
          strategy_type: "dca_accumulation",
          symbols: ["NVDA"],
        },
      },
    };

    expect(failedActionRetryActionFromMetadata(metadata)).toBeNull();
    expect(hasFailedActionMetadata(metadata)).toBe(true);
  });

  test("does not treat unrelated metadata as a failed action", () => {
    expect(hasFailedActionMetadata({ stage_outcome: "needs_clarification" })).toBe(
      false,
    );
  });

  test("hydrates a local retry action for a failed user turn without backend payload", () => {
    const action = retryLastTurnActionFromMessage(
      " what if I bought $125 of BTC every two weeks in 2022? ",
      { assistantMessageId: "assistant-failed-1" },
    );

    expect(action).toEqual({
      id: "retry-last-turn",
      label: "Retry",
      labelKey: "common.retry",
      value: "Retry",
      type: "retry_last_turn",
      payload: {
        message: "what if I bought $125 of BTC every two weeks in 2022?",
        failed_assistant_id: "assistant-failed-1",
      },
    });
    expect(retryLastTurnMessageFromAction(action)).toBe(
      "what if I bought $125 of BTC every two weeks in 2022?",
    );
    expect(
      retryLastTurnSendOptions({
        failedAssistantId: "assistant-failed-1",
        requestMessageId: null,
      }),
    ).toEqual({
      renderUserMessage: false,
      replacementAssistantId: "assistant-failed-1",
      keepLocalTranscript: true,
    });
    expect(
      retryLastTurnSendOptions({
        failedAssistantId: null,
        requestMessageId: "request-message-1",
      }),
    ).toEqual({ renderUserMessage: true });
  });

  test("hydrates a retry-last-turn action from persisted failure metadata", () => {
    const action = retryLastTurnActionFromMetadata(
      {
        agent_runtime_turn: {
          turn_id: "request-message-1",
        },
        retry_last_turn: {
          request_message_id: "request-message-1",
          message: "tampered browser copy",
        },
      },
      {
        owningMessageId: "request-message-1",
        persistedMessage: "what if I bought $125 of BTC every two weeks in 2022?",
        messageRole: "user",
      },
    );

    expect(action).toEqual({
      id: "retry-last-turn-request-message-1",
      label: "Retry",
      labelKey: "common.retry",
      value: "Retry",
      type: "retry_last_turn",
      payload: {
        message: "what if I bought $125 of BTC every two weeks in 2022?",
        request_message_id: "request-message-1",
      },
    });
    expect(retryLastTurnRequestMessageIdFromAction(action)).toBe(
      "request-message-1",
    );
  });

  test("preserves a discovery pick so Retry does not send the chip label alone", () => {
    const action = retryLastTurnActionFromMessage("AAPL", {
      assistantMessageId: "assistant-claim-2",
      chatAction: {
        type: "select_discovery_candidate",
        label: "AAPL",
        payload: {
          symbol: "AAPL",
          name: "Apple Inc.",
          asset_class: "equity",
        },
      },
    });

    expect(retryLastTurnChatActionFromAction(action)).toEqual({
      type: "select_discovery_candidate",
      label: "AAPL",
      payload: {
        symbol: "AAPL",
        name: "Apple Inc.",
        asset_class: "equity",
      },
    });
  });

  test("preserves a typed chat action for finalization retry", () => {
    const action = retryLastTurnActionFromMetadata(
      {
        retry_last_turn: {
          message: "run backtest",
          action: {
            type: "run_backtest",
            label: "Run backtest",
            payload: { confirmation_id: "confirmation-1" },
            presentation: "confirmation",
          },
        },
      },
      { assistantMessageId: "assistant-finalization-failed" },
    );

    expect(retryLastTurnChatActionFromAction(action)).toEqual({
      type: "run_backtest",
      label: "Run backtest",
      payload: { confirmation_id: "confirmation-1" },
      presentation: "confirmation",
    });
  });

  test("retries a failed response option with only its durable request identity", () => {
    const action = retryLastTurnActionFromMetadata(
      {
        agent_runtime_turn: {
          turn_id: "request-message-1",
        },
        retry_last_turn: {
          request_message_id: "request-message-1",
          message: "Use daily bars",
          action: {
            type: "select_response_option",
            label: "Use daily bars",
            payload: {
              option_id: "daily",
              replacement_values: { timeframe: "1D" },
            },
          },
        },
      },
      {
        owningMessageId: "request-message-1",
        persistedMessage: "Use daily bars",
        messageRole: "user",
      },
    );

    expect(retryLastTurnChatActionFromAction(action)).toEqual({
      type: "select_response_option",
      label: "Retry",
      labelKey: "common.retry",
      payload: {
        request_message_id: "request-message-1",
      },
    });
  });

  test("does not hydrate retry-last-turn from malformed persisted metadata", () => {
    expect(retryLastTurnActionFromMetadata({ retry_last_turn: {} })).toBeNull();
    expect(
      retryLastTurnActionFromMetadata({
        retry_last_turn: { message: "   " },
      }),
    ).toBeNull();
    expect(
      retryLastTurnActionFromMetadata(
        {
          agent_runtime_turn: { turn_id: "different-message" },
          retry_last_turn: {
            request_message_id: "request-message-1",
            message: "Test AAPL",
          },
        },
        {
          owningMessageId: "request-message-1",
          persistedMessage: "Test AAPL",
          messageRole: "user",
        },
      ),
    ).toBeNull();
    expect(
      retryLastTurnActionFromMetadata(
        {
          agent_runtime_turn: { turn_id: "request-message-1" },
          retry_last_turn: {
            request_message_id: "request-message-1",
            message: "Test AAPL",
          },
        },
        {
          owningMessageId: "request-message-1",
          persistedMessage: "Test AAPL",
          messageRole: "assistant",
        },
      ),
    ).toBeNull();
  });

  test("does not hydrate a retry-last-turn action from empty input", () => {
    expect(retryLastTurnActionFromMessage("   ")).toBeNull();
  });

  test("hydrates a structured retry action for conversation load failures", () => {
    const action = conversationLoadRetryActionFromConversationId(
      " conversation-load-1 ",
    );

    expect(action).toEqual({
      id: "retry-load-conversation",
      label: "Retry",
      labelKey: "common.retry",
      value: "Retry",
      type: "retry_load_conversation",
      payload: {
        conversation_id: "conversation-load-1",
      },
    });
    expect(retryLoadConversationIdFromAction(action)).toBe("conversation-load-1");
    expect(isRetryAction(action)).toBe(true);
  });

  test("does not hydrate a conversation-load retry without a conversation id", () => {
    expect(conversationLoadRetryActionFromConversationId("  ")).toBeNull();
    expect(retryLoadConversationIdFromAction(undefined)).toBeNull();
  });

  test("later work removes the assistant retry but preserves historical recovery", () => {
    const recoveryOwner: Message = {
      id: "assistant-failed-1",
      role: "ai",
      kind: "text",
      content: "Something went wrong.",
      recoveryDisplay: { kind: "recovery_code", code: "runtime_failure" },
      actions: [
        {
          id: "retry-last-turn-request-message-1",
          label: "Retry",
          type: "retry_last_turn",
          payload: {
            request_message_id: "request-message-1",
            message: "Test AAPL",
          },
        },
      ],
    };

    const [historical, later] = normalizeDurableRetryActionHistory([
      recoveryOwner,
      {
        id: "later-user-message",
        role: "user",
        kind: "text",
        content: "Test MSFT instead",
      },
    ]);

    expect(historical.actions).toBeUndefined();
    expect(historical.recoveryDisplay).toEqual(recoveryOwner.recoveryDisplay);
    expect(later.id).toBe("later-user-message");
  });

  test("keeps linked accepted-turn recovery on the assistant message", () => {
    const owners: Message[] = [
      {
        id: "request-message-1",
        role: "user",
        kind: "text",
        content: "Test AAPL",
      },
      {
        id: "request-message-1",
        role: "user",
        kind: "action",
        content: "Use daily bars",
        selectedAction: {
          type: "select_response_option",
          label: "Use daily bars",
          payload: { option_id: "daily" },
        },
      },
    ];

    for (const owner of owners) {
      const retryAction = {
        id: "retry-last-turn-request-message-1",
        label: "Retry",
        type: "retry_last_turn" as const,
        payload: {
          request_message_id: "request-message-1",
          message: owner.content,
        },
      };
      const recoveryDisplay = {
        kind: "recovery_code" as const,
        code: "runtime_failure",
      };

      const assistantFailure: Message = {
        id: "assistant-failed-1",
        role: "ai",
        kind: "text",
        content: "Something went wrong.",
        recoveryDisplay,
        assistantRecoveryCode: "runtime_failure",
        actions: [retryAction],
      };
      const normalized = normalizeDurableRetryActionHistory([
        owner,
        assistantFailure,
      ]);

      expect(normalized).toEqual([owner, assistantFailure]);
    }
  });
});
