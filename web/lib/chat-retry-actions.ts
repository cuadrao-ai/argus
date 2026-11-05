import type { ChatActionOption } from "@/components/chat/types";
import type { Message } from "@/components/chat/types";

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

const STRUCTURED_CHAT_ACTION_TYPES = new Set<NonNullable<ChatActionOption["type"]>>([
  "run_backtest",
  "change_dates",
  "change_asset",
  "adjust_assumptions",
  "cancel_confirmation",
  "show_breakdown",
  "refine_strategy",
  "save_strategy",
  "retry_failed_action",
  "select_response_option",
  "select_discovery_candidate",
  "retest_run",
]);

function structuredChatActionOrNull(value: unknown): ChatActionOption | null {
  const record = recordOrNull(value);
  const type = stringOrNull(record?.type) as ChatActionOption["type"] | null;
  if (!type || !STRUCTURED_CHAT_ACTION_TYPES.has(type)) {
    return null;
  }
  const presentation = stringOrNull(record?.presentation);
  return {
    type,
    label: stringOrNull(record?.label) ?? "Retry",
    ...(stringOrNull(record?.labelKey)
      ? { labelKey: stringOrNull(record?.labelKey) ?? undefined }
      : {}),
    ...(recordOrNull(record?.payload) ? { payload: recordOrNull(record?.payload) ?? {} } : {}),
    ...(presentation === "confirmation" || presentation === "result"
      ? { presentation }
      : {}),
  };
}

function failedActionPayloadFromMetadata(
  metadata: Record<string, unknown>,
): {
  artifactId: string | null;
  artifactStatus: string | null;
  launchPayload: Record<string, unknown> | null;
  retryable: unknown;
} | null {
  const reference = recordOrNull(metadata.latest_failed_action_reference);
  const referenceMetadata = recordOrNull(reference?.metadata);
  const failedAction = recordOrNull(metadata.failed_action) ?? referenceMetadata;
  if (!reference && !failedAction) {
    return null;
  }

  const retryable =
    failedAction?.retryable ?? referenceMetadata?.retryable ?? metadata.retryable;

  const launchPayload =
    recordOrNull(failedAction?.launch_payload) ??
    recordOrNull(referenceMetadata?.launch_payload);
  if (!launchPayload) {
    return null;
  }

  return {
    artifactId:
      stringOrNull(reference?.artifact_id) ??
      stringOrNull(failedAction?.artifact_id),
    artifactStatus:
      stringOrNull(reference?.artifact_status) ??
      stringOrNull(failedAction?.artifact_status),
    launchPayload,
    retryable,
  };
}

function retryableFailedActionPayload(metadata: Record<string, unknown>) {
  const failedAction = failedActionPayloadFromMetadata(metadata);
  if (!failedAction || failedAction.retryable !== true) {
    return null;
  }
  return failedAction;
}

export function hasFailedActionMetadata(
  metadata: Record<string, unknown>,
): boolean {
  return failedActionPayloadFromMetadata(metadata) !== null;
}

export function failedActionRetryActionFromMetadata(
  metadata: Record<string, unknown>,
): ChatActionOption | null {
  const failedAction = retryableFailedActionPayload(metadata);
  if (!failedAction) {
    return null;
  }
  const artifactId = failedAction.artifactId;
  if (!artifactId) {
    return null;
  }
  return {
    id: `retry-failed-action-${artifactId}`,
    label: "Retry",
    labelKey: "common.retry",
    value: "Retry",
    type: "retry_failed_action",
    artifactId,
    artifactType: "failed_action",
    artifactStatus: failedAction.artifactStatus ?? "failed",
    payload: {
      failed_action_id: artifactId,
    },
  };
}

type RetryLastTurnOptions = {
  assistantMessageId?: string;
  chatAction?: ChatActionOption | null;
  owningMessageId?: string;
  persistedMessage?: string;
  messageRole?: "user" | "assistant";
  requestMessageId?: string;
};

// Retired onboarding rows persist in old conversations; they must never
// resurface as retryable turns.
function isLegacyOnboardingMarker(content: string): boolean {
  return (
    content === "__ONBOARDING_SKIP__" ||
    content.startsWith("__ONBOARDING_GOAL__:")
  );
}

export function retryLastTurnActionFromMessage(
  message: string,
  options?: RetryLastTurnOptions,
): ChatActionOption | null {
  const trimmed = message.trim();
  if (!trimmed || isLegacyOnboardingMarker(trimmed)) {
    return null;
  }
  const failedAssistantId = options?.assistantMessageId?.trim();
  const requestMessageId = options?.requestMessageId?.trim();
  return {
    id: requestMessageId
      ? `retry-last-turn-${requestMessageId}`
      : "retry-last-turn",
    label: "Retry",
    labelKey: "common.retry",
    value: "Retry",
    type: "retry_last_turn",
    payload: {
      message: trimmed,
      ...(requestMessageId
        ? { request_message_id: requestMessageId }
        : {}),
      ...(failedAssistantId ? { failed_assistant_id: failedAssistantId } : {}),
      ...(options?.chatAction ? { chat_action: options.chatAction } : {}),
    },
  };
}

export function retryLastTurnActionFromMetadata(
  metadata: Record<string, unknown>,
  options?: RetryLastTurnOptions,
): ChatActionOption | null {
  const retryLastTurn = recordOrNull(metadata.retry_last_turn);
  const requestMessageId = stringOrNull(
    retryLastTurn?.request_message_id,
  )?.trim();
  if (requestMessageId) {
    const runtimeTurn = recordOrNull(metadata.agent_runtime_turn);
    const turnId = stringOrNull(runtimeTurn?.turn_id)?.trim();
    const owningMessageId = options?.owningMessageId?.trim();
    const linkedRequestMessageId = options?.requestMessageId?.trim();
    const persistedMessage = options?.persistedMessage?.trim();
    const ownsAbandonedUserProjection =
      options?.messageRole === "user" &&
      requestMessageId === owningMessageId &&
      turnId === owningMessageId;
    const ownsLinkedAssistantProjection =
      options?.messageRole === "assistant" &&
      requestMessageId === linkedRequestMessageId &&
      turnId === linkedRequestMessageId;
    if (
      (!ownsAbandonedUserProjection && !ownsLinkedAssistantProjection) ||
      !owningMessageId ||
      !persistedMessage
    ) {
      return null;
    }
    return retryLastTurnActionFromMessage(persistedMessage, {
      ...options,
      requestMessageId,
      chatAction: structuredChatActionOrNull(retryLastTurn?.action),
    });
  }
  const legacyMessage = stringOrNull(retryLastTurn?.message);
  if (!legacyMessage || options?.messageRole === "user") {
    return null;
  }
  return retryLastTurnActionFromMessage(legacyMessage, {
    ...options,
    chatAction: structuredChatActionOrNull(retryLastTurn?.action),
  });
}

export function durableRetryLastTurnFromStreamError(
  metadata: Record<string, unknown>,
): {
  action: ChatActionOption;
  persistedMessage: string;
  requestMessageId: string;
} | null {
  const retryLastTurn = recordOrNull(metadata.retry_last_turn);
  const requestMessageId = stringOrNull(
    retryLastTurn?.request_message_id,
  )?.trim();
  const persistedMessage = stringOrNull(retryLastTurn?.message)?.trim();
  if (!requestMessageId || !persistedMessage) {
    return null;
  }
  const action = retryLastTurnActionFromMetadata(
    {
      ...metadata,
      agent_runtime_turn: {
        turn_id: requestMessageId,
      },
    },
    {
      assistantMessageId: stringOrNull(metadata.message_id)?.trim(),
      owningMessageId: requestMessageId,
      persistedMessage,
      messageRole: "user",
    },
  );
  return action ? { action, persistedMessage, requestMessageId } : null;
}

export function retryLastTurnSendOptions(input: {
  failedAssistantId: string | null;
  requestMessageId: string | null;
}): {
  renderUserMessage: boolean;
  replacementAssistantId?: string;
  keepLocalTranscript?: boolean;
} {
  const keepLocalTranscript = !input.requestMessageId;
  if (input.failedAssistantId) {
    return {
      renderUserMessage: false,
      replacementAssistantId: input.failedAssistantId,
      keepLocalTranscript,
    };
  }
  if (input.requestMessageId) {
    return { renderUserMessage: true };
  }
  return { renderUserMessage: false, keepLocalTranscript };
}

export function retryLastTurnRequestMessageIdFromAction(
  action: ChatActionOption | null | undefined,
): string | null {
  if (action?.type !== "retry_last_turn") {
    return null;
  }
  return stringOrNull(action.payload?.request_message_id)?.trim() || null;
}

export function retryLastTurnMessageFromAction(
  action: ChatActionOption | null | undefined,
): string | null {
  if (action?.type !== "retry_last_turn") {
    return null;
  }
  const message = stringOrNull(action.payload?.message);
  return message?.trim() || null;
}

export function retryLastTurnFailedAssistantIdFromAction(
  action: ChatActionOption | null | undefined,
): string | null {
  if (action?.type !== "retry_last_turn") {
    return null;
  }
  return stringOrNull(action.payload?.failed_assistant_id)?.trim() || null;
}

export function retryLastTurnChatActionFromAction(
  action: ChatActionOption | null | undefined,
): ChatActionOption | null {
  if (action?.type !== "retry_last_turn") {
    return null;
  }
  const chatAction = structuredChatActionOrNull(action.payload?.chat_action);
  if (chatAction?.type !== "select_response_option") {
    return chatAction;
  }
  const requestMessageId = retryLastTurnRequestMessageIdFromAction(action);
  if (!requestMessageId) {
    return null;
  }
  return {
    type: "select_response_option",
    label: "Retry",
    labelKey: "common.retry",
    payload: {
      request_message_id: requestMessageId,
    },
  };
}

export function conversationLoadRetryActionFromConversationId(
  conversationId: string | null | undefined,
): ChatActionOption | null {
  const trimmed = conversationId?.trim();
  if (!trimmed) {
    return null;
  }
  return {
    id: "retry-load-conversation",
    label: "Retry",
    labelKey: "common.retry",
    value: "Retry",
    type: "retry_load_conversation",
    payload: {
      conversation_id: trimmed,
    },
  };
}

export function retryLoadConversationIdFromAction(
  action: ChatActionOption | null | undefined,
): string | null {
  if (action?.type !== "retry_load_conversation") {
    return null;
  }
  return stringOrNull(action.payload?.conversation_id)?.trim() || null;
}

export function isRetryAction(action: ChatActionOption | null | undefined): boolean {
  if (!action) {
    return false;
  }
  return (
    action.type === "retry_failed_action" ||
    action.type === "retry_last_turn" ||
    action.type === "retry_load_conversation" ||
    action.artifactType === "failed_action"
  );
}

export function normalizeDurableRetryActionHistory(
  messages: Message[],
): Message[] {
  // Accepted user input and an Argus-side failure are separate transcript
  // events. The retry payload links them without moving presentation ownership.
  return messages.flatMap((message, index) => {
    if (
      message.role === "ai" &&
      message.kind === "text" &&
      message.contentPresentation === "superseded_runtime_failure"
    ) {
      return [];
    }
    if (!message.actions?.some(isRetryAction)) {
      return [message];
    }
    const laterWork = messages.slice(index + 1).some((later) => {
      if (later.role === "user") {
        return true;
      }
      if (
        later.kind === "strategy_result" ||
        later.kind === "strategy_confirmation" ||
        later.kind === "backtest_job"
      ) {
        return true;
      }
      return (
        later.role === "ai" &&
        later.kind === "text" &&
        !later.recoveryDisplay
      );
    });
    if (!laterWork) {
      return [message];
    }
    const actions = message.actions.filter(
      (action) => !isRetryAction(action),
    );
    return [
      {
        ...message,
        actions: actions.length > 0 ? actions : undefined,
      },
    ];
  });
}
