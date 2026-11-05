"use client";

import { useState, useRef, useEffect } from "react";
import { ThumbsUp, ThumbsDown, MoreHorizontal, Copy, MessageSquareWarning, RotateCcw } from "lucide-react";
import SafeMarkdown from "@/components/chat/SafeMarkdown";
import { useTranslation } from "react-i18next";
import SharedConversationMessage from "./SharedConversationMessage";
import StrategyResultCard from "./StrategyResultCard";
import ToolResultCard from "./ToolResultCard";
import { answerAssumptionsText, type ToolRecompute } from "@/lib/tool-result-card";
import { ComputedAnswerDecision } from "./DecisionAffordance";
import StrategyConfirmationCard from "./StrategyConfirmationCard";
import BacktestJobCard from "./BacktestJobCard";
import DiscoverySourcesPanel from "./DiscoverySourcesPanel";
import { researchSourcesDisplay } from "@/lib/research-sources-display";
import MemoryRecallNote from "./MemoryRecallNote";
import { RetestReceipt } from "./RetestReceipt";
import { RETEST_ACTION_TYPE } from "@/lib/chat-retest";
import NextMoveRow, {
  NextMoveDetail,
  NextMoveSeparator,
  NextMoveTicker,
  NextMoveTitle,
} from "./NextMoveRow";
import NextStepsSection from "./NextStepsSection";
import { messageNextSteps } from "@/lib/chat-next-steps";
import {
  type ChatActionOption,
  type ChatMention,
  type ConfirmationDirectEditPayload,
  Message,
} from "./types";
import type { DecisionState } from "@/lib/argus-api";
import { normalizeAssistantDisplayText } from "@/lib/chat-display-text";
import { chatMessageCopyText } from "@/lib/chat-message-copy-text";
import { resultMessageReadoutText } from "@/lib/result-readout-display";
import { writeClipboardText } from "@/lib/clipboard";
import { isRetryAction } from "@/lib/chat-retry-actions";
import {
  recoveryDisplayText,
  recoveryNoticeUnderAnswer,
  wearsQuietFailureNotice,
} from "@/lib/chat-recovery-display";
import { feedbackContextForMessage } from "@/lib/chat-message-feedback-context";
import { Tooltip } from "@/components/ui/Tooltip";
import FailureNotice from "./FailureNotice";
import {
  retryableNoticeBodyClass,
  retryableNoticeContainerClass,
  retryableNoticeIconClass,
  retryableNoticeRetryPillClass,
} from "@/lib/failure-treatment";
import { GUEST_COMPUTE_CLAIM_RETRY_IN_KEY } from "@/lib/compute-claim-error";
import { useRetryAfterCountdown } from "@/lib/use-retry-after-countdown";
import { isSettledStrategyResult } from "@/lib/chat-result-message";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { actionHasCardScopedOwnership } from "@/lib/chat-action-ownership";
import { confirmationPeriodAdjustmentText } from "@/lib/confirmation-period-adjustment";
import { confirmationBenchmarkAdjustmentText } from "@/lib/confirmation-benchmark-adjustment";
import { confirmationEditDisclosureText } from "@/lib/confirmation-edit-disclosure";
import { pendingArtifactCardFromPayload } from "@/lib/pending-artifact-card";
import { discoveryEscalationCopyPlan } from "@/lib/chat-discovery-escalation";
import { EntityToken } from "./entity-token";
import { toolRecomputeEligible } from "@/lib/tool-result-recompute";
import { messageMentionPieces } from "./mention-rendering";


type ChatMessageProps = {
  message: Message;
  onAction?: (action: ChatActionOption) => void;
  onToolRecompute?: ToolRecompute;
  /** Opens another conversation: a continued result, or the chat it came from. */
  onOpenConversation?: (conversationId: string) => void;
  onDirectEdit?: (
    confirmationId: string,
    edit: ConfirmationDirectEditPayload,
  ) => Promise<void>;
  onFeedback?: (type: "bug" | "feature" | "general" | "rating", context: Record<string, unknown>, rating?: "positive" | "negative") => void;
  onToast?: (message: string, variant?: "neutral" | "error") => void;
  isLatest?: boolean;
  latestMessageId?: string | null;
  isStreaming?: boolean;
  conversationId?: string | null;
  nextMovesEnabled?: boolean;
  turnInFlight?: boolean;
  isGuest?: boolean;
  canSaveDecision?: boolean;
  memoryProposalEnabled?: boolean;
  onDecisionUnavailable?: (artifactId: string) => void;
  onDecisionSaved?: (decisionState: DecisionState) => void;
  onRequestSearchUpgrade?: () => void;
  resumeDecisionArtifactId?: string | null;
  onDecisionResumeHandled?: () => void;
};

const retryIconButtonClass =
  "inline-flex items-center justify-center rounded-full text-black/60 transition-all duration-200 hover:bg-black/5 hover:text-black dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white";

export default function ChatMessage({
  message,
  onAction,
  onDirectEdit,
  onToolRecompute,
  onOpenConversation,
  onFeedback,
  onToast,
  isLatest,
  latestMessageId,
  isStreaming,
  conversationId,
  nextMovesEnabled = true,
  turnInFlight = false,
  isGuest = false,
  canSaveDecision = true,
  memoryProposalEnabled = false,
  onDecisionUnavailable,
  onDecisionSaved,
  onRequestSearchUpgrade,
  resumeDecisionArtifactId,
  onDecisionResumeHandled,
}: ChatMessageProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? "en";
  const { isBelowTablet } = useResponsiveLayout();
  const isUser = message.role === "user";
  const confirmation = pendingArtifactCardFromPayload(message.confirmation);
  const [rating, setRating] = useState<"positive" | "negative" | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const [anchorSourceIndex, setAnchorSourceIndex] = useState<number | null>(
    null,
  );
  const [menuPosition, setMenuPosition] = useState<"top" | "bottom">("bottom");
  const optionsRef = useRef<HTMLDivElement>(null);
  const selectedFeedbackClass =
    "hover:bg-black/5 dark:hover:bg-white/10 text-[#191c1f] dark:text-white";
  const idleFeedbackClass =
    "hover:bg-black/5 dark:hover:bg-white/10 text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white";
  const selectedFeedbackIconClass = "fill-current";
  const feedbackContext = (extra: Record<string, string | number | boolean> = {}) =>
    feedbackContextForMessage(message, conversationId, extra);

  const toggleOptions = (e: React.MouseEvent) => {
    if (!showOptions) {
      const buttonRect = e.currentTarget.getBoundingClientRect();
      // If the button is too close to the bottom of the screen (e.g. within 160px), map the popup upwards
      if (buttonRect.bottom + 160 > window.innerHeight) {
        setMenuPosition("top");
      } else {
        setMenuPosition("bottom");
      }
      setShowOptions(true);
    } else {
      setShowOptions(false);
    }
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (optionsRef.current && !optionsRef.current.contains(event.target as Node)) {
        setShowOptions(false);
      }
    }

    function handleScroll() {
      setShowOptions(false);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShowOptions(false);
      }
    }

    if (showOptions) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
      // Use capture phase to ensure we catch the scroll event from the inner container natively
      window.addEventListener("scroll", handleScroll, true);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [showOptions]);

  const handleRating = (newRating: "positive" | "negative") => {
    if (rating === newRating) {
      setRating(null);
    } else {
      setRating(newRating);
      onFeedback?.("rating", feedbackContext(), newRating);
    }
  };

  const getCopyText = () => chatMessageCopyText(message, t, locale);

  const handleCopy = async (text = getCopyText()) => {
    const copied = await writeClipboardText(text);
    onToast?.(
      t(copied ? "chat.copy_success" : "chat.copy_failed"),
      copied ? "neutral" : "error",
    );
  };

  // An answer with a recovery keeps its content; the notice renders under it.
  const noticeUnderAnswer = !isUser && recoveryNoticeUnderAnswer(message.recoveryDisplay);
  const getDisplayContent = () => {
    if (!isUser && isStreaming && message.contentPresentation === "result_breakdown") {
      return t("chat.status.working");
    }
    const readout = resultMessageReadoutText(message, t, locale);
    if (readout !== null) return readout;
    const content = message.content ?? "";
    if (!isUser && message.recoveryDisplay && !noticeUnderAnswer) {
      const recovered = recoveryDisplayText(message.recoveryDisplay, t, locale);
      if (recovered.trim()) {
        return recovered;
      }
    }
    return isUser ? content : normalizeAssistantDisplayText(content);
  };

  const actionLabel = (action: ChatActionOption) =>
    action.labelKey
      ? t(action.labelKey, {
          defaultValue: action.label,
          ...((action.payload ?? {}) as Record<string, unknown>),
        })
      : action.label;
  const retryAction = message.actions?.find(isRetryAction);
  const retryAfterRemaining = useRetryAfterCountdown(retryAction?.availableAtMs);
  const retryReady = retryAfterRemaining <= 0;
  const retryActionLabel = retryAction
    ? retryReady
      ? actionLabel(retryAction)
      : t(GUEST_COMPUTE_CLAIM_RETRY_IN_KEY, { count: retryAfterRemaining })
    : "";
  const userRecoveryText =
    isUser && message.recoveryDisplay
      ? recoveryDisplayText(message.recoveryDisplay, t, locale).trim()
      : "";
  const footerMessageActions = (message.actions ?? []).filter(
    (action) => !isRetryAction(action) && !actionHasCardScopedOwnership(action),
  );
  const shouldShowAssistantFooter = !isUser && !isStreaming;
  // Next moves answer the newest question only. Older groups are settled by the
  // reply that followed them, so they stop rendering rather than staying
  // tappable — the guard the floating composer strip used to provide.
  const showNextMoveRows =
    shouldShowAssistantFooter &&
    Boolean(isLatest) &&
    nextMovesEnabled &&
    footerMessageActions.length > 0;
  const footerVisibilityClass =
    isLatest || rating || showOptions || Boolean(retryAction)
      ? "opacity-100"
      : "pointer-events-none opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 focus-within:pointer-events-auto focus-within:opacity-100";
  const displayContent = getDisplayContent();
  // The amber notice: in place of a failed reply, or under an answer given
  // without a lookup that failed.
  const retryableNotice = (text: string) => (
    <div
      role="status"
      className={`${retryableNoticeContainerClass} max-w-[min(100%,660px)]`}
    >
      <MessageSquareWarning className={retryableNoticeIconClass} aria-hidden="true" />
      <div className={retryableNoticeBodyClass}>
        <SafeMarkdown>{text}</SafeMarkdown>
      </div>
      {retryAction ? (
        <button
          type="button"
          disabled={!retryReady}
          aria-disabled={!retryReady}
          onClick={() => {
            if (!retryReady) return;
            onAction?.(retryAction);
          }}
          className={`${retryableNoticeRetryPillClass} disabled:pointer-events-none disabled:opacity-50 disabled:hover:bg-transparent`}
        >
          {retryActionLabel}
        </button>
      ) : null}
    </div>
  );
  const assumedInputsLine = answerAssumptionsText(message, t, locale);
  const researchSourcesOpen = researchSourcesDisplay(Boolean(message.researchDegradedCode));
  // Chips carry domains and the drawer owns the list; zero sources is the
  // ungrounded marker (derived, never asserted). Canon: DESIGN.md §11.
  const discoverySourcesLineText =
    isUser ||
    !message.discovery ||
    message.discovery.sources.length > 0
      ? ""
      : t("chat.discovery_results.unsourced_line", {
          defaultValue: "From general knowledge, not a current search",
        });
  const confirmationPeriodLeadIn = confirmationPeriodAdjustmentText(
    confirmation?.period_adjustment,
    (key, options) => t(key, options),
    i18n.resolvedLanguage ?? i18n.language ?? "en",
  );
  const confirmationBenchmarkLeadIn = confirmationBenchmarkAdjustmentText(
    confirmation?.benchmark_adjustment,
    (key, options) => t(key, options),
  );
  const confirmationEditDisclosureLeadIn = confirmationEditDisclosureText(
    confirmation?.edit_disclosure,
    t,
  );

  if (isUser && message.kind === "action") {
    const actionText =
      displayContent ||
      (message.selectedAction ? actionLabel(message.selectedAction) : "");
    const showRetestReceipt =
      Boolean(message.retestReceipt) ||
      (message.selectedAction?.type === RETEST_ACTION_TYPE &&
        message.retestReceiptPending === true);
    return (
      <div className="flex w-full flex-col items-end animate-in fade-in slide-in-from-bottom-2 duration-300">
        {showRetestReceipt ? (
          <RetestReceipt
            receipt={message.retestReceipt ?? null}
            actionLabel={actionText}
            pending={message.retestReceiptPending === true}
          />
        ) : (
          <div className="max-w-[85%] rounded-full border border-black/10 bg-black/[0.03] px-4 py-2.5 text-[14px] font-medium leading-[1.45] text-black/75 dark:border-white/12 dark:bg-white/[0.06] dark:text-white/75">
            {actionText}
          </div>
        )}
        <UserTurnRecovery
          recoveryText={userRecoveryText}
          retryAction={retryAction}
          retryLabel={retryAction ? actionLabel(retryAction) : ""}
          onAction={onAction}
        />
      </div>
    );
  }

  if (message.sharedConversation) return <SharedConversationMessage message={message} />;

  if (isUser) {
    return (
      <div className="flex w-full flex-col items-end animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="max-w-[85%] bg-black/5 dark:bg-white/10 text-black dark:text-white px-5 py-3.5 rounded-[24px] rounded-br-sm text-[16px] leading-[1.5] tracking-[0.24px] font-normal">
          <UserMessageContent content={displayContent} mentions={message.mentions ?? []} />
        </div>
        <UserTurnRecovery
          recoveryText={userRecoveryText}
          retryAction={retryAction}
          retryLabel={retryAction ? actionLabel(retryAction) : ""}
          onAction={onAction}
        />
      </div>
    );
  }

  return (
    <div className="flex w-full justify-start animate-in fade-in slide-in-from-bottom-2 duration-300 group relative">
      {shouldShowAssistantFooter && (
        <Tooltip content={t('chat.copy_plaintext')} side="left">
          <button
            onClick={() => {
              void handleCopy();
            }}
            className="absolute -left-10 top-1 opacity-0 group-hover:opacity-40 hover:!opacity-100 transition-opacity p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/10 text-black dark:text-white"
            aria-label={t('chat.copy_plaintext')}
          >
            <Copy className="w-4 h-4" />
          </button>
        </Tooltip>
      )}
      <div className="flex max-w-[85%] flex-col">
        <div className="flex flex-col mt-1.5">
          {isSettledStrategyResult(message) ? (
            <div className="flex w-full max-w-[min(100%,660px)] flex-col gap-4">
              <StrategyResultCard
                result={message.result}
                onAction={onAction}
                canSaveDecision={canSaveDecision}
                memoryProposalEnabled={memoryProposalEnabled}
                onDecisionUnavailable={onDecisionUnavailable}
                onDecisionSaved={onDecisionSaved}
                resumeDecisionArtifactId={resumeDecisionArtifactId}
                onDecisionResumeHandled={onDecisionResumeHandled}
              />
              {displayContent && (
                <ResultReadout
                  content={displayContent}
                  label={t("chat.result_readout.quick_take", "Quick take")}
                />
              )}
            </div>
          ) : message.kind === "backtest_job" && message.backtestJob &&
            (message.contentPresentation !== "result_breakdown" || !isStreaming) ? (
            <div className="w-full max-w-[min(100%,660px)]">
              <BacktestJobCard
                job={message.backtestJob}
                canRetry={Boolean(retryAction)}
                failureMessage={displayContent}
                onRetry={
                  retryAction ? () => onAction?.(retryAction) : undefined
                }
                retryLabel={retryAction ? actionLabel(retryAction) : undefined}
              />
            </div>
          ) : message.kind === "strategy_confirmation" && confirmation?.kind === "backtest" ? (
            <div className="flex w-full max-w-[min(100%,660px)] flex-col gap-3">
              {confirmationPeriodLeadIn ? (
                <p className="text-[15px] leading-[1.55] tracking-[0.2px] text-black/75 dark:text-white/75">
                  {confirmationPeriodLeadIn}
                </p>
              ) : null}
              {confirmationBenchmarkLeadIn ? (
                <p className="text-[15px] leading-[1.55] tracking-[0.2px] text-black/75 dark:text-white/75">
                  {confirmationBenchmarkLeadIn}
                </p>
              ) : null}
              {confirmationEditDisclosureLeadIn ? (
                <p
                  data-testid="confirmation-edit-disclosure"
                  className="text-[15px] leading-[1.55] tracking-[0.2px] text-black/75 dark:text-white/75"
                >
                  {confirmationEditDisclosureLeadIn}
                </p>
              ) : null}
              <StrategyConfirmationCard
                confirmation={confirmation}
                disabled={turnInFlight}
                onAction={onAction}
                onDirectEdit={
                  onDirectEdit && confirmation.confirmation_id
                    ? (edit) =>
                        onDirectEdit(confirmation.confirmation_id!, edit)
                    : undefined
                }
              />
            </div>
          ) : message.contentPresentation === "result_readout" ? (
            <ResultReadout content={displayContent} label={t("chat.result_readout.quick_take", "Quick take")} />
          ) : message.contentPresentation === "result_breakdown" && displayContent.trim() ? (
            <ResultBreakdown
              ariaLabel={t("chat.result_breakdown.aria_label", "Result breakdown")}
              content={displayContent}
              label={t("chat.result_breakdown.label", "Breakdown")}
              isWorking={Boolean(isStreaming)}
            />
          ) : !isUser && message.assistantRecoveryCode && !noticeUnderAnswer ? (
            // Infrastructure failure is visibly a failure: no result chrome,
            // no normal-answer bubble (issue #249).
            retryableNotice(displayContent)
          ) : !isUser && !noticeUnderAnswer && wearsQuietFailureNotice(message.recoveryDisplay) ? (
            // A rejected action or a lookup that cannot be retried is still a
            // failure statement; it must not read as an ordinary answer, only
            // quieter than amber.
            <FailureNotice
              className="max-w-[min(100%,660px)]"
              testId={
                message.recoveryDisplay?.kind === "artifact_action_recovery"
                  ? "artifact-action-failure-notice"
                  : "recovery-failure-notice"
              }
            >
              <SafeMarkdown>
                {displayContent}
              </SafeMarkdown>
            </FailureNotice>
          ) : (
            <div className="text-black dark:text-white text-[16px] leading-[1.6] tracking-[0.24px] prose dark:prose-invert max-w-none">
              <SafeMarkdown>
                {displayContent}
              </SafeMarkdown>
            </div>
          )}
          {assumedInputsLine ? (
            <p data-answer-assumptions className="mt-3 max-w-[min(100%,660px)] text-sm text-black/60 dark:text-white/60">{assumedInputsLine}</p>
          ) : null}

          {!isUser && message.continuedFrom && onOpenConversation ? (
            <button type="button" data-continued-from={message.continuedFrom.conversationId}
              onClick={() => { if (message.continuedFrom) onOpenConversation(message.continuedFrom.conversationId); }}
              className="mt-3 inline-flex min-h-11 items-center text-left text-[13px] text-black/50 underline decoration-black/20 underline-offset-4 transition-colors hover:text-black dark:text-white/50 dark:decoration-white/20 dark:hover:text-white">
              {t("tools.compute.continued_from")}
            </button>
          ) : null}
          {!isUser && message.toolJobs?.map((pending) => <div key={pending.call_id} className="mt-3 w-full max-w-[min(100%,660px)]">
            <BacktestJobCard job={pending.job} canRetry={false} />
          </div>)}
          {!isUser && message.hasUnavailableToolResults ? <p role="status" className="mt-3 text-sm text-black/60 dark:text-white/60">{t("tools.card.unavailable")}</p> : null}
          {!isUser && message.toolResultCards?.filter((card) => !(card.card_type === "backtest" && message.result) && !message.toolJobs?.some((pending) => pending.artifact_id === card.artifact_id && pending.call_id === card.call_id)).map((card) => (
            <div key={`${card.artifact_id}-${card.input_revision}`} className="mt-3 w-full max-w-[min(100%,660px)]">
              <ToolResultCard card={card} onRecompute={onToolRecompute} disabled={!toolRecomputeEligible(message.id, latestMessageId, turnInFlight || Boolean(isStreaming))} />
            </div>
          ))}
          {noticeUnderAnswer ? (
            <div data-recovery-under-answer className="mt-3 w-full max-w-[min(100%,660px)]">
              {message.assistantRecoveryCode ? (
                retryableNotice(recoveryDisplayText(message.recoveryDisplay, t, locale))
              ) : (
                <FailureNotice testId="recovery-failure-notice">
                  <SafeMarkdown>
                    {recoveryDisplayText(message.recoveryDisplay, t, locale)}
                  </SafeMarkdown>
                </FailureNotice>
              )}
            </div>
          ) : null}

          {!isUser && !isStreaming && message.memoryRecalls?.length ? (
            <MemoryRecallNote recalls={message.memoryRecalls} />
          ) : null}
          {/* Any computed answer offers a decision; guests resume on cards only. */}
          {!isUser && !isStreaming && message.computation && canSaveDecision ? (
            <ComputedAnswerDecision
              message={message}
              conversationId={conversationId}
              onOpenConversation={onOpenConversation}
              onSaved={(decision) => onDecisionSaved?.(decision.decision_state)}
            />
          ) : null}
          {!isUser && !isStreaming && message.discovery && (
            <div className="mt-3 flex w-full max-w-[min(100%,660px)] flex-col gap-2">
              <div className="flex flex-col divide-y divide-black/8 dark:divide-white/8">
                {message.discovery.candidates.map((candidate) => {
                  const sendText = t("chat.discovery_results.test_candidate", {
                    symbol: candidate.symbol,
                    defaultValue: "Backtest {{symbol}}",
                  });
                  // One row vocabulary: the same verb the rail's rows use,
                  // with the name leading and the ticker as its badge. The
                  // sent text stays the backend-owned action string.
                  const testVerb = t("chat.next_experiments.test_verb", {
                    defaultValue: "Test",
                  });
                  const hasName =
                    Boolean(candidate.name) && candidate.name !== candidate.symbol;
                  // One chip per row: the first corroborating source. Cheap
                  // rows carry no indices, so they stay chipless by shape.
                  const chipIndex = candidate.source_indices?.[0];
                  const chipSource =
                    chipIndex === undefined
                      ? undefined
                      : message.discovery?.sources[chipIndex];
                  return (
                    <NextMoveRow
                      key={candidate.symbol}
                      ariaLabel={sendText}
                      disabled={turnInFlight}
                      onClick={() =>
                        onAction?.({
                          type: "select_discovery_candidate",
                          label: sendText,
                          labelKey: "chat.discovery_results.test_candidate",
                          value: sendText,
                          payload: {
                            symbol: candidate.symbol,
                            name: candidate.name,
                            asset_class: candidate.asset_class,
                          },
                        })
                      }
                    >
                      <NextMoveTitle>
                        {testVerb}
                        {hasName ? ` ${candidate.name}` : ""}{" "}
                        <NextMoveTicker>{candidate.symbol}</NextMoveTicker>
                      </NextMoveTitle>
                      {candidate.reason_text ? (
                        <>
                          <NextMoveSeparator>·</NextMoveSeparator>
                          <NextMoveDetail>{candidate.reason_text}</NextMoveDetail>
                        </>
                      ) : null}
                      {chipSource ? (
                        // Plain span: interactive content is invalid inside
                        // the row button; the sources button is the keyboard path.
                        <span
                          onClick={(event) => {
                            event.stopPropagation();
                            setAnchorSourceIndex(chipIndex ?? null);
                            setShowSources(true);
                          }}
                          className="ms-1.5 inline-flex translate-y-[-1px] cursor-pointer items-center rounded-full border border-black/10 px-1.5 py-px align-middle text-[11px] leading-[1.4] text-black/45 transition-colors hover:border-black/25 hover:text-black/70 dark:border-white/12 dark:text-white/45 dark:hover:border-white/30 dark:hover:text-white/75"
                        >
                          {chipSource.domain}
                        </span>
                      ) : null}
                    </NextMoveRow>
                  );
                })}
                {message.discovery.sources.length === 0 &&
                message.discovery.can_request_search &&
                isLatest ? (
                  (() => {
                    const searchLabel = t(
                      "chat.discovery_results.search_current",
                      { defaultValue: "Search for current results" },
                    );
                    const copyPlan = discoveryEscalationCopyPlan(
                      message.discovery,
                    );
                    const assetKind = t(copyPlan.assetKindKey, {
                      defaultValue: copyPlan.assetKindDefaultValue,
                    });
                    // Restate the relationship: peer/comparison query_summary
                    // is bare symbols, and "search for: AAPL" reads as a test.
                    const searchSendText = t(
                      copyPlan.messageKey,
                      {
                        query: copyPlan.query,
                        assetKind,
                        defaultValue: copyPlan.messageDefaultValue,
                      },
                    );
                    return (
                      <NextMoveRow
                        ariaLabel={searchLabel}
                        disabled={turnInFlight}
                        onClick={() =>
                          // Typeless: a typed option is validated against the
                          // latest turn's options and rejected as stale.
                          onAction?.({
                            label: searchSendText,
                            value: searchSendText,
                          })
                        }
                      >
                        <NextMoveTitle>{searchLabel}</NextMoveTitle>
                      </NextMoveRow>
                    );
                  })()
                ) : null}
              </div>
              {isGuest &&
              isLatest &&
              message.discovery.sources.length === 0 &&
              message.discovery.can_request_search === false &&
              onRequestSearchUpgrade ? (
                // Upsell on appetite, never on apology: this renders only on
                // the honest exhausted answer, where the hidden search row sat.
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 rounded-[14px] border border-[#5ba897]/25 bg-[#5ba897]/[0.08] px-3 py-2.5">
                  <p className="min-w-0 text-[13px] leading-[1.45] text-[#3f6658] dark:text-[#9fccbd]">
                    {t("chat.discovery_results.allowance_banner", {
                      defaultValue: "Grounded search allowance used",
                    })}
                  </p>
                  <button
                    type="button"
                    onClick={onRequestSearchUpgrade}
                    className="shrink-0 rounded-full border border-[#5ba897]/40 px-3 py-1.5 text-[13px] font-medium text-[#3f6658] transition-colors hover:bg-[#5ba897]/15 dark:text-[#b4d5c8] dark:hover:bg-[#5ba897]/20"
                  >
                    {t("chat.discovery_results.allowance_banner_cta", {
                      defaultValue: "Sign in for more searches",
                    })}
                  </button>
                </div>
              ) : null}
              {discoverySourcesLineText ||
              message.discovery.sources.length > 0 ? (
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-black/8 pt-2 dark:border-white/8">
                  {discoverySourcesLineText ? (
                    <p className="min-w-0 text-[12px] leading-[1.5] tracking-[0.2px] text-black/50 [overflow-wrap:anywhere] dark:text-white/50">
                      {discoverySourcesLineText}
                    </p>
                  ) : null}
                  {message.discovery.sources.length > 0 ? (
                    <button
                      type="button"
                      onClick={() => setShowSources(true)}
                      className="relative z-10 shrink-0 text-[12px] leading-[1.5] tracking-[0.2px] text-black/50 underline-offset-2 transition-colors after:absolute after:inset-x-0 after:top-1/2 after:h-11 after:min-w-11 after:-translate-y-1/2 after:content-[''] hover:text-black/80 hover:underline dark:text-white/50 dark:hover:text-white/80"
                    >
                      {t("chat.discovery_results.sources_panel_open", {
                        count: message.discovery.sources.length,
                        defaultValue: "{{count}} sources ›",
                        defaultValue_one: "{{count}} source ›",
                      })}
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          )}

          {/* One sources surface for every rail shape: the model never writes
              a citation line, and this renders only what the backend sidecar
              carried. */}
          {!message.discovery && (message.researchSources?.length ?? 0) > 0 ? (
            <div className="mt-2 flex w-full max-w-[min(100%,660px)]">
              <button
                type="button"
                onClick={() => setShowSources(true)}
                data-testid="research-sources-open"
                className="relative z-10 shrink-0 text-[12px] leading-[1.5] tracking-[0.2px] text-black/50 underline-offset-2 transition-colors after:absolute after:inset-x-0 after:top-1/2 after:h-11 after:min-w-11 after:-translate-y-1/2 after:content-[''] hover:text-black/80 hover:underline dark:text-white/50 dark:hover:text-white/80"
              >
                {t(researchSourcesOpen.openKey, {
                  count: message.researchSources?.length ?? 0,
                  defaultValue: researchSourcesOpen.openFallback,
                  defaultValue_one: researchSourcesOpen.openFallbackOne,
                })}
              </button>
            </div>
          ) : null}

          {!message.discovery &&
          showSources &&
          (message.researchSources?.length ?? 0) > 0 ? (
            <DiscoverySourcesPanel
              onClose={() => {
                setShowSources(false);
                setAnchorSourceIndex(null);
              }}
              sidecar={{
                sources: message.researchSources ?? [],
                retrieved_at: "",
              }}
              withheld={Boolean(message.researchDegradedCode)}
            />
          ) : null}

          {message.discovery && showSources ? (
            <DiscoverySourcesPanel
              onClose={() => {
                setShowSources(false);
                setAnchorSourceIndex(null);
              }}
              sidecar={message.discovery}
              anchorIndex={anchorSourceIndex}
            />
          ) : null}

          {/* One next-move list is the sanctioned surface for any message that
              carries one (results, answers about them, grounded knowledge
              answers); only mid-turn composition suppresses it. */}
          {shouldShowAssistantFooter && Boolean(isLatest) && !turnInFlight && (
            <NextStepsSection
              steps={messageNextSteps(message)}
              disabled={turnInFlight}
              isBelowTablet={isBelowTablet}
              locale={locale}
              onAction={onAction}
              sourceRunId={
                message.result?.runId ??
                message.nextExperimentsSourceRunId ??
                undefined
              }
              t={t}
            />
          )}

          {showNextMoveRows && (
            <div className="mt-2 flex w-full max-w-[min(100%,660px)] flex-col divide-y divide-black/8 dark:divide-white/8">
              {footerMessageActions.map((action) => (
                <NextMoveRow
                  key={action.id ?? action.type ?? action.label}
                  onClick={() => onAction?.(action)}
                >
                  <NextMoveTitle>{actionLabel(action)}</NextMoveTitle>
                </NextMoveRow>
              ))}
            </div>
          )}

          {shouldShowAssistantFooter && (
            <div className="flex items-start justify-end gap-4 mt-2">
              <div
                className={`relative flex shrink-0 items-center gap-1.5 transition-opacity ${footerVisibilityClass}`}
                ref={optionsRef}
                onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                    setShowOptions(false);
                  }
                }}
              >
                <Tooltip content={t('chat.good_response')} side="top">
                  <button
                    className={`p-1.5 rounded-full transition-all duration-200 group/thumb ${ rating === "positive" ? selectedFeedbackClass : idleFeedbackClass }`}
                    aria-label={t('chat.good_response')}
                    onClick={() => handleRating("positive")}
                  >
                    <ThumbsUp className={`w-3.5 h-3.5 ${rating === "positive" ? selectedFeedbackIconClass : ""}`} />
                  </button>
                </Tooltip>
                <Tooltip content={t('chat.poor_response')} side="top">
                  <button
                    className={`p-1.5 rounded-full transition-all duration-200 group/thumb ${ rating === "negative" ? selectedFeedbackClass : idleFeedbackClass }`}
                    aria-label={t('chat.poor_response')}
                    onClick={() => handleRating("negative")}
                  >
                    <ThumbsDown className={`w-3.5 h-3.5 ${rating === "negative" ? selectedFeedbackIconClass : ""}`} />
                  </button>
                </Tooltip>
                {/* The failure block owns the retry control; the footer only
                    offers it for messages without that block. */}
                {retryAction &&
                  !message.assistantRecoveryCode &&
                  message.kind !== "backtest_job" && (
                  <Tooltip content={actionLabel(retryAction)} side="top">
                    <button
                      type="button"
                      className={`${retryIconButtonClass} p-1.5`}
                      aria-label={actionLabel(retryAction)}
                      onClick={() => onAction?.(retryAction)}
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                    </button>
                  </Tooltip>
                )}
                <Tooltip content={t('chat.more_actions')} side="top">
                  <button
                    onClick={toggleOptions}
                    className="p-1.5 rounded-full hover:bg-black/5 dark:hover:bg-white/10 text-black/60 dark:text-white/60 hover:text-black dark:hover:text-white transition-colors"
                    aria-label={t('chat.more_actions')}
                    aria-haspopup="menu"
                    aria-expanded={showOptions}
                  >
                    <MoreHorizontal className="w-3.5 h-3.5" />
                  </button>
                </Tooltip>

                {/* Popover Menu */}
                {showOptions && (
                  <div
                    className={`absolute ${menuPosition === "bottom" ? "top-full mt-2" : "bottom-full mb-2"} right-0 w-[220px] bg-white dark:bg-[#1f2225] rounded-[24px] border border-black/5 dark:border-white/5 py-2 z-50 animate-in fade-in zoom-in-95 duration-200`}
                    role="menu"
                  >
                    <button
                      className="w-full flex items-center gap-4 px-5 py-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left text-black dark:text-white text-[15px] font-medium"
                      role="menuitem"
                      onClick={() => { void handleCopy(); setShowOptions(false); }}
                    >
                      <Copy className="w-4 h-4 text-black/60 dark:text-white/60" />
                      {t('chat.copy_plaintext')}
                    </button>
                    <button
                      className="w-full flex items-center gap-4 px-5 py-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left text-black dark:text-white text-[15px] font-medium"
                      role="menuitem"
                      onClick={() => { setShowOptions(false); onFeedback?.("bug", feedbackContext()); }}
                    >
                      <MessageSquareWarning className="w-4 h-4 text-black/60 dark:text-white/60" />
                      {t('chat.report_issue')}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function UserTurnRecovery({
  recoveryText,
  retryAction,
  retryLabel,
  onAction,
}: {
  recoveryText: string;
  retryAction?: ChatActionOption;
  retryLabel: string;
  onAction?: (action: ChatActionOption) => void;
}) {
  if (!recoveryText && !retryAction) {
    return null;
  }
  return (
    <div className="mt-2 flex max-w-[85%] flex-wrap items-center justify-end gap-2">
      {recoveryText ? (
        <p
          data-testid="user-turn-recovery"
          className="text-right text-[13px] leading-[1.45] text-black/55 dark:text-white/55"
        >
          {recoveryText}
        </p>
      ) : null}
      {retryAction ? (
        <Tooltip content={retryLabel} side="top">
          <button
            type="button"
            data-testid="user-turn-retry"
            aria-label={retryLabel}
            onClick={() => onAction?.(retryAction)}
            className={`${retryIconButtonClass} min-h-11 min-w-11`}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      ) : null}
    </div>
  );
}

function ResultReadout({
  content,
  label,
}: {
  content: string;
  label: string;
}) {
  return (
    <section aria-label={label}>
      <div className="argus-result-section-label">{label}</div>
      <div className="argus-result-readout prose dark:prose-invert max-w-none">
        <SafeMarkdown>
          {content}
        </SafeMarkdown>
      </div>
    </section>
  );
}

function ResultBreakdown({
  ariaLabel,
  content,
  label,
  isWorking,
}: {
  ariaLabel: string;
  content: string;
  label: string;
  isWorking: boolean;
}) {
  return (
    <section aria-label={ariaLabel} aria-busy={isWorking || undefined}>
      <div className="argus-result-section-label">{label}</div>
      <div className="argus-result-breakdown prose dark:prose-invert max-w-none">
        <SafeMarkdown>
          {content}
        </SafeMarkdown>
      </div>
    </section>
  );
}

function UserMessageContent({ content, mentions }: { content: string; mentions: ChatMention[] }) {
  if (mentions.length === 0) return <>{content}</>;
  const pieces = messageMentionPieces(content, mentions);

  return (
    <>
      {pieces.map((piece, index) =>
        piece.kind === "text" ? (
          <span key={`text-${index}`}>{piece.text}</span>
        ) : (
          <EntityToken
            key={`${piece.mention.id}-${index}`}
            kind={piece.mention.type}
            surface="transcript"
            title={piece.mention.description ?? piece.mention.label}
          >
            {piece.text}
          </EntityToken>
        ),
      )}
    </>
  );
}
