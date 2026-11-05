import { sharedConversationFromMetadata } from "@/lib/shared-conversation";
import { answerAssumptionsFromMetadata, toolCardsFromMetadata, hasUnavailableToolCards } from "@/lib/tool-result-card";
import {
  resultCardFromConversationCard,
  type ApiMessage,
  type AssetClass,
  type ChatActionRequest,
  type BacktestJobResponse,
} from "@/lib/argus-api";
import { actionHasCardScopedOwnership } from "@/lib/chat-action-ownership";
import {
  discoverySidecarFromMetadata,
  researchDegradedCodeFromMetadata,
  researchSourcesForFinalPayload,
  researchSourcesFromMetadata,
} from "@/lib/chat-discovery-sidecar";
import { replaceOrAppendFinalAssistantMessage } from "@/lib/chat-send-state";
import { memoryRecallsFromMetadata } from "@/lib/memory-recalls";
import {
  decisionComputationFromMetadata,
  decisionStateFromValue,
} from "@/lib/decision-contract";
import { continuedFromMetadata } from "@/lib/computation-contract";
import { resultReadoutContentFromMetadata } from "@/lib/result-readout-content";
import { resultReadoutFacts } from "@/lib/result-readout-facts";
import { pendingArtifactCardFromPayload } from "@/lib/pending-artifact-card";
import {
  nextExperimentRowsFromMetadata,
  nextExperimentsSourceRunIdFromMetadata,
} from "@/lib/chat-next-experiments";
import { nextStepsFromMetadata } from "@/lib/chat-next-steps";
import {
  applyHydratedBacktestJobTruth,
  backtestJobCardAwaitsPolling,
  backtestJobMessageFromApi,
  RESEARCH_JOB_SCOPE,
  toolJobsFromMetadata,
} from "@/lib/chat-backtest-jobs";
import { retestReceiptFromMetadata } from "@/lib/chat-retest";
import { projectPendingBreakdowns } from "@/lib/pending-result-breakdown";
import { retireSupersededFailures } from "@/lib/chat-retry-action-history";
import {
  hydrateTextMessageFromApi,
  precedingUserMessageForRetryableRecovery,
  isHydratableResultCard,
  recordOrNull,
  retryRequestMessageForAssistant,
  strategyPathContextFromMetadata,
  stringArrayOrNull,
  stringOrNull,
} from "@/lib/chat-message-hydration";
import {
  normalizeDurableRetryActionHistory,
} from "@/lib/chat-retry-actions";
import {
  hydrateResultActions,
} from "@/lib/chat-result-actions";
import { retainCanonicalResultProjectionOwners } from "@/lib/chat-result-projection-ownership";
import {
  type RecoveryDisplay,
  visibleComposerResponseActions,
} from "@/lib/chat-recovery-display";
import { DAILY_CAP_RECOVERY_CODE, dailyCapResetAtMs } from "@/lib/daily-cap-reset-time";
import {
  claimErrorKeepsLocalTranscript,
  claimErrorMessagePatch,
  claimErrorRetryAction,
  admissionErrorTerminalPayload,
  computeClaimTransportPatch,
  isComputeClaimUnavailable,
  settleAdmissionTransportReadiness,
} from "@/lib/compute-claim-error";

export {
  claimErrorKeepsLocalTranscript,
  claimErrorMessagePatch,
  claimErrorRetryAction,
  admissionErrorTerminalPayload,
  computeClaimTransportPatch,
  isComputeClaimUnavailable,
  settleAdmissionTransportReadiness,
};
import {
  applyConsumedResultActions,
  applyConfirmationActionEffects,
  confirmationActionEffectFromAction,
  confirmationActionEffectsFromApi,
  consumedResultActionsFromApi,
  hiddenSaveActionMessageIdsFromApi,
  isBreakdownActionMetadata,
  isStaleConfirmationActionRejectionCode,
  normalizeConfirmationHistory,
  settleOpenConfirmationsAfterTextFinal,
} from "./artifact-history";
import {
  confirmationStatusAllowsActions,
  confirmationStatusFromPayload,
} from "./confirmation-display";
import type {
  ChatActionOption,
  Message,
} from "./types";

export type HydratedMessages = {
  messages: Message[];
  inputActions: ChatActionOption[];
};

export function applyChatHttpErrorToMessages(
  messages: Message[],
  display: ReturnType<typeof chatHttpErrorDisplay>,
  input: Parameters<typeof claimErrorMessagePatch>[0],
): Message[] {
  if (display.recoveryDisplay?.kind === "recovery_code" &&
    display.recoveryDisplay.code === DAILY_CAP_RECOVERY_CODE) {
    // Admission was refused before an assistant turn existed.
    return messages.filter((message) => message.id !== input.assistantMessageId);
  }
  const staleConfirmation = isStaleConfirmationActionRejectionCode(input.code);
  const claimPatch = claimErrorMessagePatch(input);
  return messages.map((message) => message.id === input.assistantMessageId ? {
    ...message,
    content: staleConfirmation ? "" : display.content,
    recoveryDisplay: staleConfirmation
      ? { kind: "recovery_code", code: input.code! }
      : (display.recoveryDisplay ?? message.recoveryDisplay),
    ...claimPatch,
  } : message);
}

export function chatActionRequestFromAction(
  action: ChatActionOption,
): ChatActionRequest {
  return {
    type: action.type as NonNullable<ChatActionOption["type"]>,
    label: action.label,
    labelKey: action.labelKey,
    payload: action.payload,
    presentation: action.presentation,
  };
}

export function settleOpenConfirmationsFromFinalPayload(
  messages: Message[],
  finalPayload: Record<string, unknown>,
  options: Omit<
    Parameters<typeof settleOpenConfirmationsAfterTextFinal>[1],
    "stageOutcome" | "recoveryCode"
  >,
): Message[] {
  return settleOpenConfirmationsAfterTextFinal(messages, {
    ...options,
    stageOutcome: finalPayload.stage_outcome,
    recoveryCode: stringOrNull(recordOrNull(finalPayload.recovery)?.code),
  });
}

export function latestInputActions(messages: Message[]): ChatActionOption[] {
  if (hasActiveArtifactActionSet(messages)) return [];
  const latestAi = [...messages]
    .reverse()
    .find((message) => message.role === "ai");
  if (
    latestAi?.kind === "strategy_confirmation" ||
    latestAi?.kind === "strategy_result"
  ) {
    return [];
  }
  return visibleComposerResponseActions(latestAi?.actions ?? []).filter(
    (action) => action.artifactType !== "failed_action",
  );
}

export function hasActiveArtifactActionSet(messages: Message[]): boolean {
  return messages.some((message) => {
    if (message.kind === "strategy_confirmation" && message.confirmation) {
      if (
        message.confirmation.confirmation_state &&
        message.confirmation.confirmation_state !== "active"
      ) {
        return false;
      }
      const status = confirmationStatusFromPayload(message.confirmation);
      if (!confirmationStatusAllowsActions(status)) return false;
      const actions = message.confirmation.actions ?? message.actions ?? [];
      return actions.some(actionHasCardScopedOwnership);
    }
    if (message.kind === "strategy_result" && message.result) {
      const actions = message.result.actions ?? message.actions ?? [];
      return actions.some(actionHasCardScopedOwnership);
    }
    return false;
  });
}

export function isFailedActionRetry(
  action: ChatActionOption | undefined,
): boolean {
  return Boolean(
    action &&
      (action.type === "retry_failed_action" ||
        action.artifactType === "failed_action"),
  );
}

export function consumeConfirmationActionOnMessages(
  messages: Message[],
  action: ChatActionOption | undefined,
): Message[] {
  const effect = confirmationActionEffectFromAction(action);
  return effect ? applyConfirmationActionEffects(messages, [effect]) : messages;
}

function assetClassOrUndefined(value: unknown): AssetClass | undefined {
  return value === "crypto" || value === "equity" || value === "currency_pair"
    ? value
    : undefined;
}

function resultActionContextFromMetadata(
  metadata: Record<string, unknown>,
  card: ReturnType<typeof resultCardFromConversationCard>,
) {
  const factBank = recordOrNull(metadata.result_fact_bank);
  const configSnapshot = recordOrNull(factBank?.config_snapshot);
  return {
    symbols: card.symbols ?? stringArrayOrNull(factBank?.symbols) ?? [],
    template: stringOrNull(configSnapshot?.template),
    assetClass: assetClassOrUndefined(factBank?.asset_class),
  };
}

function savedStrategyIdFromMetadata(
  metadata: Record<string, unknown>,
): string | null {
  return stringOrNull(metadata.saved_strategy_id);
}

export function savedStrategyIdFromFinalPayload(
  payload: Record<string, unknown>,
): string | null {
  return stringOrNull(payload.saved_strategy_id);
}

export function resultRunIdFromFinalPayload(
  payload: Record<string, unknown>,
  action?: ChatActionOption,
): string | null {
  const run = payload.run;
  const runId =
    typeof run === "object" && run !== null && "id" in run
      ? stringOrNull(run.id)
      : null;
  return (
    stringOrNull(payload.result_run_id) ??
    stringOrNull(payload.latest_run_id) ??
    runId ??
    stringOrNull(action?.payload?.run_id)
  );
}

export type MessageStreamPresentation = {
  isLatestAi: boolean;
  isWorkingMessage: boolean;
};

export function standaloneStreamStatusVisible(
  messages: Message[],
  hasVisibleStreamStatus: boolean,
): boolean {
  const latestAssistant = messages.findLast((message) => message.role === "ai");
  // The Breakdown frame already owns its pending copy.
  return hasVisibleStreamStatus && !latestAssistant?.content?.trim() &&
    latestAssistant?.contentPresentation !== "result_breakdown";
}

export function messageStreamPresentation(
  messages: Message[],
  message: Message,
  index: number,
  isStreamingResponse: boolean,
  hasVisibleStreamStatus: boolean,
): MessageStreamPresentation {
  const latestAiIndex = messages.findLastIndex((m) => m.role === "ai");
  const isLatestAi = message.role === "ai" && latestAiIndex === index;
  if (message.contentPresentation === "result_breakdown" && message.backtestJob) {
    return { isLatestAi, isWorkingMessage: backtestJobCardAwaitsPolling(message) };
  }
  return {
    isLatestAi,
    isWorkingMessage:
      (isLatestAi || Boolean(message.pendingBreakdown)) &&
      message.kind === "text" &&
      !message.toolResultCards?.length && !message.toolJobs?.length && !message.hasUnavailableToolResults &&
      message.contentPresentation !== "result_readout" &&
      message.recoveryDisplay?.kind !== "artifact_assumptions" &&
      (isStreamingResponse ||
        hasVisibleStreamStatus ||
        Boolean(message.pendingBreakdown) ||
        // A finished Breakdown may have empty content: its readout envelope
        // or typed facts own the display, so only live status means working.
        (message.contentPresentation !== "result_breakdown" && (message.content ?? "") === "")),
  };
}

export function messagesWithSavedDecisionState(
  messages: Message[],
  messageId: string,
  decisionState: NonNullable<Message["result"]>["decisionState"],
): Message[] {
  return messages.map((message) => {
    if (message.id !== messageId) return message;
    if (message.result) {
      return { ...message, result: { ...message.result, decisionState } };
    }
    // A computed answer carries its decision on the message itself.
    if (message.computation) return { ...message, decisionState };
    return message;
  });
}

export function markComposerActionsInactive(messages: Message[]): Message[] {
  return messages.map((message) => {
    if (message.kind === "strategy_result" && message.result) {
      const resultActions = message.result.actions ?? message.actions;
      return {
        ...message,
        actions: undefined,
        result: { ...message.result, actions: resultActions },
      };
    }
    if (message.kind === "strategy_confirmation" && message.confirmation) {
      const actions = message.confirmation.actions ?? message.actions;
      return {
        ...message,
        actions: undefined,
        confirmation: { ...message.confirmation, actions },
      };
    }
    // Retry belongs to the turn that failed, so a newer send supersedes it the
    // same way a newer card supersedes an older one. Conversational next moves
    // belong to the conversation, not to an artifact: whether a clarify option
    // is still answerable is decided by the row renderer, which is also the only
    // owner that survives reload -- hydration rebuilds actions for every
    // historical message, not just the newest.
    if (!message.actions) return message;
    const conversational = message.actions.filter(
      (action) => action.type === "select_response_option",
    );
    if (conversational.length === message.actions.length) return message;
    return {
      ...message,
      actions: conversational.length > 0 ? conversational : undefined,
    };
  });
}

export function hydrateMessagesFromApi(
  items: ApiMessage[],
): HydratedMessages {
  const consumedResultActions = consumedResultActionsFromApi(items);
  const confirmationActionEffects = confirmationActionEffectsFromApi(items);
  const hiddenMessageIds = new Set([
    ...hiddenSaveActionMessageIdsFromApi(items),
    ...confirmationActionEffects.hiddenMessageIds,
  ]);
  const messages: Message[] = retainCanonicalResultProjectionOwners(items)
    .filter((message) => !hiddenMessageIds.has(message.id))
    .map((message) => {
      const metadata = message.metadata ?? {};
      const sharedConversation = sharedConversationFromMetadata(metadata);
      if (sharedConversation) return { id: message.id, role: message.role === "user" ? "user" as const : "ai" as const, kind: "text" as const, content: message.content, sharedConversation };
      const toolResultCards = message.role !== "user" ? toolCardsFromMetadata(metadata) : undefined;
      const hasUnavailableToolResults = message.role !== "user" && hasUnavailableToolCards(metadata);
      const toolJobs = message.role !== "user" ? toolJobsFromMetadata(metadata) : undefined;
      const answerAssumptions = message.role !== "user" ? answerAssumptionsFromMetadata(metadata) : null;
      const isBreakdown = message.role !== "user" && (metadata.artifact_presentation_kind === "breakdown" || isBreakdownActionMetadata(metadata));
      const chatAction = metadata.chat_action as ChatActionOption | undefined;
      const confirmation = pendingArtifactCardFromPayload(metadata.confirmation_card);
      const projectedJob =
        message.role === "user" ? backtestJobMessageFromApi(message) : null;
      if (projectedJob) return projectedJob;
      if (
        message.role === "user" &&
        chatAction &&
        typeof chatAction === "object"
      ) {
        const retestReceipt = retestReceiptFromMetadata(metadata);
        return {
          ...hydrateTextMessageFromApi(message),
          kind: "action",
          selectedAction: chatAction,
          ...(retestReceipt ? { retestReceipt } : {}),
        };
      }
      if (
        message.role !== "user" &&
        !isBreakdown &&
        isHydratableResultCard(metadata.result_card)
      ) {
        const runId = String(
          metadata.result_run_id ?? metadata.latest_run_id ?? "",
        );
        const conversationId =
          typeof metadata.result_conversation_id === "string"
            ? metadata.result_conversation_id
            : message.conversation_id;
        const resultStrategyId = stringOrNull(metadata.result_strategy_id);
        const savedStrategyId = savedStrategyIdFromMetadata(metadata);
        const factBank = recordOrNull(metadata.result_fact_bank);
        const configSnapshot = recordOrNull(factBank?.config_snapshot);
        const card = resultCardFromConversationCard(metadata.result_card, {
          id: runId,
          strategy_id: resultStrategyId,
          benchmark_symbol:
            stringOrNull(factBank?.benchmark_symbol) ?? undefined,
          config_snapshot: configSnapshot ?? undefined,
          metrics: recordOrNull(factBank?.metrics) as import("@/lib/argus-api").BacktestRun["metrics"] | undefined,
          figures: recordOrNull(factBank?.figures) ?? undefined,
          symbols: stringArrayOrNull(factBank?.symbols) ?? undefined,
        });
        const context = resultActionContextFromMetadata(metadata, card);
        const actions = hydrateResultActions(card.actions ?? [], {
          runId: card.runId,
          strategyId: card.strategyId,
          conversationId,
          strategyName: card.strategyName,
          symbols: context.symbols,
          template: context.template ?? undefined,
          assetClass: context.assetClass,
        });
        return {
          id: message.id,
          role: "ai",
          kind: "strategy_result",
          toolResultCards, hasUnavailableToolResults, toolJobs,
          content: undefined,
          result: {
            ...card,
            readoutContent: resultReadoutContentFromMetadata(metadata, card.readoutContent),
            symbols: context.symbols,
            template: context.template ?? undefined,
            assetClass: context.assetClass,
            savedStrategyId,
            actions,
          },
          actions,
          nextExperiments:
            nextExperimentRowsFromMetadata(metadata) ?? undefined,
          savedStrategyId,
          memoryRecalls: memoryRecallsFromMetadata(metadata) ?? undefined,
        };
      }
      if (
        message.role !== "user" &&
        metadata.artifact_presentation_kind === "result"
      ) {
        return {
          id: message.id,
          role: "ai",
          kind: "text",
          contentPresentation: "result_readout",
          toolResultCards, hasUnavailableToolResults, toolJobs,
          resultReadoutFacts: resultReadoutFacts(metadata.result_fact_bank),
          resultReadoutContent: resultReadoutContentFromMetadata(metadata),
        };
      }
      const jobMessage = backtestJobMessageFromApi(message);
      if (jobMessage) return { ...jobMessage, toolResultCards, hasUnavailableToolResults, toolJobs };
      if (
        message.role !== "user" &&
        confirmation &&
        Array.isArray(confirmation.rows) &&
        // A discovery answer owns its message: if confirmation chrome ever
        // co-arrives, the rows the user asked for must not silently drop.
        !discoverySidecarFromMetadata(metadata)
      ) {
        return {
          id: message.id,
          role: "ai",
          kind: "strategy_confirmation",
          toolResultCards, hasUnavailableToolResults, toolJobs,
          content: message.content,
          confirmation,
          strategyPathContext: strategyPathContextFromMetadata(
            metadata,
            message.id,
          ),
          actions: confirmation.actions ?? [],
          // Researched peer adds ride the ordinary Try-next surface below
          // the card's turn (research rail, spec section 6).
          nextExperiments:
            nextExperimentRowsFromMetadata(metadata) ?? undefined,
        };
      }
      const hydratedText = { ...hydrateTextMessageFromApi(message, {
        retryRequestMessage:
          retryRequestMessageForAssistant(items, message) ??
          precedingUserMessageForRetryableRecovery(items, message),
        contentPresentation:
          isBreakdown
            ? "result_breakdown"
            : undefined,
      }), toolJobs, ...(answerAssumptions ? { answerAssumptions } : {}) };
      if (isBreakdown) {
        return {
          ...hydratedText,
          content: undefined,
          resultBreakdownJobId: stringOrNull(metadata.backtest_job_id) ?? undefined,
          researchSources: researchSourcesFromMetadata(metadata),
          researchDegradedCode: researchDegradedCodeFromMetadata(metadata),
          recoveryDisplay: hydratedText.recoveryDisplay?.kind === "result_breakdown" ? hydratedText.recoveryDisplay : {
            kind: "result_breakdown" as const,
            facts: resultReadoutFacts(metadata.result_fact_bank),
          },
        };
      }
      if (message.role !== "user") {
        const discovery = discoverySidecarFromMetadata(metadata);
        const researchSources = researchSourcesFromMetadata(metadata);
        const researchDegradedCode = researchDegradedCodeFromMetadata(metadata);
        // Grounded knowledge answers carry Try next rows on a plain message;
        // a discovery sidecar owns its message and suppresses them. Memory
        // recalls overlay either shape independently.
        const nextExperiments = discovery
          ? null
          : nextExperimentRowsFromMetadata(metadata);
        const nextSteps = discovery
          ? null
          : nextStepsFromMetadata(metadata, nextExperiments);
        const memoryRecalls = memoryRecallsFromMetadata(metadata);
        // A computed answer declares its computation; the backend stamps
        // the current decision beside it. Both are rendered, never inferred.
        const computation = decisionComputationFromMetadata(metadata);
        const continuedFrom = continuedFromMetadata(metadata);
        if (
          discovery ||
          nextExperiments ||
          nextSteps ||
          memoryRecalls ||
          computation ||
          researchSources.length > 0
        ) {
          return {
            ...hydratedText,
            ...(continuedFrom ? { continuedFrom } : {}),
            ...(computation
              ? {
                  computation,
                  decisionNoteId: stringOrNull(metadata.decision_note_id),
                  decisionState: decisionStateFromValue(metadata.decision_state),
                }
              : {}),
            ...(discovery ? { discovery } : {}),
            // A discovery turn already renders its own sources panel; one
            // answer must never offer two source surfaces.
            ...(!discovery && researchSources.length > 0
              ? { researchSources, researchDegradedCode }
              : {}),
            ...(nextExperiments
              ? {
                  nextExperiments,
                  nextExperimentsSourceRunId:
                    nextExperimentsSourceRunIdFromMetadata(metadata),
                }
              : {}),
            ...(nextSteps ? { nextSteps } : {}),
            ...(memoryRecalls ? { memoryRecalls } : {}),
          };
        }
      }
      return hydratedText;
    });

  // Retirement runs before the durable normalize: it needs to see the
  // superseded failure to hide the retry's duplicate request bubble.
  const normalized = normalizeDurableRetryActionHistory(
    retireSupersededFailures(
      applyConsumedResultActions(
        applyHydratedBacktestJobTruth(
          applyConfirmationActionEffects(
            normalizeConfirmationHistory(messages),
            confirmationActionEffects.effects,
          ),
        ),
        consumedResultActions,
      ),
    ),
  );
  const completedBreakdownJobs = new Set(normalized.flatMap((message) => message.resultBreakdownJobId ? [message.resultBreakdownJobId] : []));
  const retained = normalized.filter((message) => !message.backtestJob || !completedBreakdownJobs.has(message.backtestJob.id));
  const reconciled = projectPendingBreakdowns(items, reconcileToolJobMessages(retained));
  return { messages: reconciled, inputActions: latestInputActions(reconciled) };
}

/** Completed canonical answer messages retire only their own pending tool card. */
export function reconcileToolJobMessages(messages: Message[]): Message[] {
  return messages.map((source) => {
    if (!source.toolJobs?.length) return source;
    const toolJobs = source.toolJobs.map((pending) => {
      const completed = messages.find((candidate) => candidate.id !== source.id &&
        candidate.toolResultCards?.some((card) => card.call_id === pending.call_id &&
          card.artifact_id === pending.artifact_id && card.tool_name === pending.tool_name));
      return completed ? { ...pending, resultMessageId: completed.id } : pending;
    });
    return { ...source, toolJobs, toolResultCards: source.toolResultCards?.filter((card) =>
      !toolJobs.some((pending) => pending.resultMessageId && pending.artifact_id === card.artifact_id && pending.call_id === card.call_id)) };
  });
}

// A terminal research job's message (the answer, or the failure note) is a
// new assistant message the job response carries; it renders in place after
// the job card, the way a run result does, so the open view never has to
// refetch or blank to show it. The card records the message id once it is
// in the view, which is what ends its polling.
//
// Position: the conversation is locked from the card's persistence until the
// job settles, and settling requires the message to exist, so nothing else
// can be persisted between card and message; "right after the card" is the
// persisted order.
export function applyResearchJobAnswer(
  messages: Message[],
  response: BacktestJobResponse,
): Message[] {
  const answer = response.result_message;
  if (response.job.operation_scope !== RESEARCH_JOB_SCOPE || !answer) {
    return messages;
  }
  const toolSourceIndex = messages.findIndex((source) => source.toolJobs?.some((pending) => pending.job.id === response.job.id));
  if (toolSourceIndex !== -1) {
    if (messages.some((entry) => entry.id === answer.id)) return reconcileToolJobMessages(messages);
    const projected = hydrateMessagesFromApi([answer]).messages[0];
    if (!projected) return messages;
    const siblings = new Set(messages[toolSourceIndex].toolJobs?.map((pending) => pending.resultMessageId).filter(Boolean));
    const insertAfter = Math.max(toolSourceIndex, messages.findLastIndex((entry) => siblings.has(entry.id)));
    return reconcileToolJobMessages([...messages.slice(0, insertAfter + 1), projected, ...messages.slice(insertAfter + 1)]);
  }
  const cardIndex = messages.findIndex(
    (message) =>
      message.kind === "backtest_job" &&
      message.backtestJob?.id === response.job.id,
  );
  if (cardIndex !== -1 && messages[cardIndex].contentPresentation === "result_breakdown") {
    const projected = hydrateMessagesFromApi([answer]).messages[0];
    if (!projected) return messages;
    return messages.flatMap((message, index) => index === cardIndex
      ? [projected] : message.id === answer.id ? [] : [message]);
  }
  const present = messages.some((message) => message.id === answer.id);
  const cardSettled =
    cardIndex === -1 ||
    messages[cardIndex]?.researchResultMessageId === answer.id;
  if (present && cardSettled) return messages;
  const settled = cardSettled
    ? messages
    : messages.map((message, index) =>
        index === cardIndex
          ? { ...message, researchResultMessageId: answer.id }
          : message,
      );
  if (present) return settled;
  const projected = hydrateMessagesFromApi([answer]).messages[0];
  if (!projected) return settled;
  if (cardIndex === -1) return [...settled, projected];
  return [
    ...settled.slice(0, cardIndex + 1),
    projected,
    ...settled.slice(cardIndex + 1),
  ];
}

export function chatStreamErrorText(
  detail: string | undefined,
  fallback: string,
): string {
  return detail || fallback;
}

const RETEST_COVERAGE_PROBLEM_CODES: ReadonlySet<string> = new Set([
  "market_data_unavailable",
  "insufficient_common_data",
  "no_common_data_window",
  "kraken_ohlc_window_exceeded",
  "provider_history_start_unavailable",
  "provider_timeframe_unavailable",
]);

export function chatHttpErrorDisplay(
  problemCode: string | null,
  backendMessage: string,
  response?: { status: number; retryAfter: string | null; nowMs?: number },
): { content: string; recoveryDisplay: RecoveryDisplay | null } {
  if (response?.status === 429) {
    return {
      content: "",
      recoveryDisplay: {
        kind: "recovery_code",
        code: DAILY_CAP_RECOVERY_CODE,
        values: { resetAt: new Date(dailyCapResetAtMs(response.retryAfter, response.nowMs)).toISOString() },
      },
    };
  }
  if (isComputeClaimUnavailable(problemCode)) {
    return {
      content: "",
      recoveryDisplay: {
        kind: "recovery_code",
        code: problemCode,
      },
    };
  }
  if (!problemCode || !RETEST_COVERAGE_PROBLEM_CODES.has(problemCode)) {
    return { content: backendMessage, recoveryDisplay: null };
  }
  return {
    content: "",
    recoveryDisplay: { kind: "coverage_recovery", code: problemCode },
  };
}


export function applyEmptyFinalFallback(
  messages: Message[],
  options: Readonly<{
    assistantId: string;
    finalMessageId?: string;
    content: string;
    finalActions: NonNullable<Message["actions"]>;
    recoveryDisplay?: Message["recoveryDisplay"];
    strategyPathContext?: Message["strategyPathContext"];
    assistantRecoveryCode?: Message["assistantRecoveryCode"];
    discovery?: Message["discovery"];
    memoryRecalls?: Message["memoryRecalls"];
    finalPayload: Record<string, unknown>;
    action: Parameters<
      typeof settleOpenConfirmationsFromFinalPayload
    >[2]["action"];
    hasFailedAction: boolean;
  }>,
): Message[] {
  // A final frame that owns no visible terminal artifact still yields a
  // visible assistant turn: the localized turn-failure copy, the frame's
  // sidecars, and the same confirmation settle a prose-bearing final runs.
  return normalizeDurableRetryActionHistory(
    settleOpenConfirmationsFromFinalPayload(
      replaceOrAppendFinalAssistantMessage(messages, options.assistantId, {
        id: options.finalMessageId ?? options.assistantId,
        role: "ai",
        kind: "text",
        content: options.content,
        actions:
          options.finalActions.length > 0 ? options.finalActions : undefined,
        recoveryDisplay: options.recoveryDisplay,
        strategyPathContext: options.strategyPathContext,
        assistantRecoveryCode: options.assistantRecoveryCode,
        discovery: options.discovery,
        memoryRecalls: options.memoryRecalls,
        researchSources: researchSourcesForFinalPayload(options.finalPayload),
        researchDegradedCode: researchDegradedCodeFromMetadata(options.finalPayload),
        nextExperiments:
          nextExperimentRowsFromMetadata(options.finalPayload) ?? undefined,
      }),
      options.finalPayload,
      {
        action: options.action,
        finalActions: options.finalActions,
        hasFailedAction: options.hasFailedAction,
      },
    ),
  );
}
