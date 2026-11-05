import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  actionHasCardScopedOwnership,
  visibleComposerActions,
} from "../lib/chat-action-ownership";
import {
  confirmationRowKey,
  confirmationStatusAllowsActions,
} from "../components/chat/confirmation-display";
import { visibleComposerResponseActions } from "../lib/chat-recovery-display";
import type { ChatActionOption } from "../components/chat/types";

const root = join(import.meta.dir, "..");

describe("chat turn artifact UX", () => {
  test("shared action ownership keeps card actions out of composer and footer surfaces", () => {
    const actions: ChatActionOption[] = [
      { type: "run_backtest", label: "Run backtest", presentation: "confirmation" },
      { type: "change_dates", label: "Change dates", presentation: "confirmation" },
      { type: "change_asset", label: "Change asset", presentation: "confirmation" },
      { type: "adjust_assumptions", label: "Adjust assumptions", presentation: "confirmation" },
      { type: "cancel_confirmation", label: "Cancel", presentation: "confirmation" },
      { type: "show_breakdown", label: "Explain result", presentation: "result" },
      { type: "refine_strategy", label: "Refine idea", presentation: "result" },
      { type: "retry_failed_action", label: "Try again" },
      { type: "save_strategy", label: "Save", presentation: "result" },
      { id: "ask-follow-up", label: "Ask follow-up" },
      { id: "presentation-confirmation", label: "Presentation confirmation", presentation: "confirmation" },
      { id: "presentation-result", label: "Presentation result", presentation: "result" },
    ];

    expect(actions.filter(actionHasCardScopedOwnership).map((action) => action.label)).toEqual([
      "Run backtest",
      "Change dates",
      "Change asset",
      "Adjust assumptions",
      "Cancel",
      "Explain result",
      "Refine idea",
      "Save",
      "Presentation confirmation",
      "Presentation result",
    ]);
    expect(visibleComposerActions(actions).map((action) => action.label)).toEqual([
      "Try again",
      "Ask follow-up",
    ]);
  });

  test("retry stays icon-owned by its message instead of duplicating as a composer chip", () => {
    const retryAction = {
      type: "retry_last_turn",
      label: "Retry",
      value: "Retry",
    } satisfies ChatActionOption;
    const followUpAction = {
      id: "ask-follow-up",
      label: "Ask follow-up",
    } satisfies ChatActionOption;

    expect(
      visibleComposerResponseActions([retryAction, followUpAction]),
    ).toEqual([followUpAction]);
  });

  test("live unsupported-strategy alternatives stay once on their owning assistant", () => {
    const alternatives = [
      {
        id: "unsupported-strategy-rsi-threshold",
        label: "Use a supported RSI threshold rule",
        labelKey: "chat.simplification_options.rsi_threshold",
        type: "select_response_option",
        payload: {
          source_assistant_id: "assistant-strategy",
          option_id: "rsi_threshold",
          replacement_values: { simplify_logic: "rsi_only" },
        },
      },
      {
        id: "unsupported-strategy-buy-and-hold",
        label: "Compare with buy and hold",
        labelKey: "chat.simplification_options.buy_and_hold",
        type: "select_response_option",
        payload: {
          source_assistant_id: "assistant-strategy",
          option_id: "buy_and_hold",
          replacement_values: { strategy_type: "buy_and_hold" },
        },
      },
      {
        id: "unsupported-strategy-moving-average-crossover",
        label: "Use a supported moving-average crossover",
        labelKey: "chat.simplification_options.moving_average_crossover",
        type: "select_response_option",
        payload: {
          source_assistant_id: "assistant-strategy",
          option_id: "moving_average_crossover",
          replacement_values: {
            strategy_type: "signal_strategy",
            rule_family: "moving_average_crossover",
          },
        },
      },
    ] satisfies ChatActionOption[];
    const coverageAction = {
      id: "coverage-change-dates",
      label: "Change dates",
      type: "select_response_option",
      payload: {
        source_assistant_id: "assistant-coverage",
        option_id: "change_dates",
        replacement_values: { requested_field: "date_range" },
      },
    } satisfies ChatActionOption;
    const timeframeAction = {
      id: "unsupported-timeframe-option-1",
      label: "Retry with daily bars",
      type: "select_response_option",
      payload: {
        source_assistant_id: "assistant-timeframe",
        option_id: "option_1",
        replacement_values: { timeframe: "1D" },
      },
    } satisfies ChatActionOption;

    expect(new Set(alternatives.map((action) => action.id)).size).toBe(3);
    for (const alternative of alternatives) {
      expect(
        alternatives.filter((action) => action.id === alternative.id),
      ).toHaveLength(1);
    }
    expect(
      visibleComposerResponseActions([
        coverageAction,
        timeframeAction,
        ...alternatives,
      ]),
    ).toEqual([coverageAction, timeframeAction]);
    expect(alternatives.map((action) => action.payload)).toEqual([
      {
        source_assistant_id: "assistant-strategy",
        option_id: "rsi_threshold",
        replacement_values: { simplify_logic: "rsi_only" },
      },
      {
        source_assistant_id: "assistant-strategy",
        option_id: "buy_and_hold",
        replacement_values: { strategy_type: "buy_and_hold" },
      },
      {
        source_assistant_id: "assistant-strategy",
        option_id: "moving_average_crossover",
        replacement_values: {
          strategy_type: "signal_strategy",
          rule_family: "moving_average_crossover",
        },
      },
    ]);
  });

  test("confirmation cards share the premium artifact shell and avoid stale action duplication", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    // The card's view model is shared with Copy, so its composition is
    // asserted where it now lives (#509).
    const viewModel = readFileSync(
      join(root, "lib/confirmation-card-view-model.ts"),
      "utf-8",
    );

    expect(card).toContain("artifactStatusToneClassName");
    expect(card).not.toContain("const confirmationToneClasses");
    expect(card).toContain("confirmationDisplayState");
    expect(card).toContain("font-display text-[18px]");
    expect(card).not.toContain("{confirmation.summary}");
    expect(card).toContain("text-[#505a63] dark:text-[#8d969e]");
    expect(card).toContain("activeActions.length > 0");
    expect(message).toContain("disabled={turnInFlight}");
    expect(card).toContain("disabled={disabled}");
    expect(card).toContain("confirmation.confirmation_state === \"active\"");
    expect(card).toContain("confirmationCardViewModel");
    expect(viewModel).toContain("confirmationAssetTitle");
    expect(viewModel).toContain("confirmationAssumptionDisplay({");
    expect(viewModel).toContain("assetClass: confirmation.asset_class");
    expect(card).not.toContain("confirmation.rows.slice(0, 3)");
    expect(card).not.toContain("sm:grid-cols-3");
    expect(card).not.toContain("opacity-70");
  });

  test("confirmation status icons reflect status semantics, not localized labels", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );

    expect(card).toContain("CONFIRMATION_STATUS_ICON_STATE");
    expect(card).toContain("satisfies Record<StrategyConfirmationStatus, ConfirmationStatusIconState>");
    expect(card).toContain("function confirmationStatusIcon(");
    expect(card).toContain("TERMINAL_CONFIRMATION_STATUSES");
    expect(card).toContain("!TERMINAL_CONFIRMATION_STATUSES.has(status)");
    expect(card).toContain("data-confirmation-status={displayState.status}");
    expect(card).not.toContain('if (status === "editing")');
    expect(card).toContain("editing: { icon: Pencil, isSpinning: false }");
    expect(card).toContain("ready_to_run: { icon: Play, isSpinning: false }");
    expect(card).toContain("request_sent: { icon: Send, isSpinning: false }");
    expect(card).toContain("could_not_run: { icon: TriangleAlert, isSpinning: false }");
    expect(card).toContain("run_complete: { icon: CheckCircle2, isSpinning: false }");
    expect(card).toContain("updated: { icon: RefreshCw, isSpinning: false }");
  });

  test("confirmation actions are gated by semantic status, not stale action arrays", () => {
    expect(confirmationStatusAllowsActions("ready_to_run")).toBe(true);
    expect(confirmationStatusAllowsActions("needs_change")).toBe(true);
    expect(confirmationStatusAllowsActions("updated")).toBe(true);
    expect(confirmationStatusAllowsActions("running")).toBe(false);
    expect(confirmationStatusAllowsActions("request_sent")).toBe(false);
    expect(confirmationStatusAllowsActions("run_complete")).toBe(false);
    expect(confirmationStatusAllowsActions("could_not_run")).toBe(false);
    expect(confirmationStatusAllowsActions("draft_canceled")).toBe(false);
    expect(confirmationStatusAllowsActions("not_completed")).toBe(false);

    const card = readFileSync(
      join(root, "components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/chat-message-projection.ts"),
      "utf-8",
    );

    expect(card).toContain("confirmationStatusAllowsActions(displayState.status)");
    expect(chat).toContain("confirmationStatusAllowsActions(status)");
  });

  test("confirmation row identity uses structured keys instead of translated labels", () => {
    expect(
      confirmationRowKey({
        label: "Capital inicial",
        labelKey: "chat.confirmation.rows.starting_capital",
      }),
    ).toBe("starting_capital");
    expect(confirmationRowKey({ label: "Capital inicial" })).toBeNull();
  });

  test("assistant turn controls render for artifact turns without duplicating card-scoped actions", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const ownership = readFileSync(
      join(root, "lib/chat-action-ownership.ts"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/chat-message-projection.ts"),
      "utf-8",
    );

    expect(ownership).toContain("export function actionHasCardScopedOwnership");
    expect(ownership).toContain("export function visibleComposerActions");
    expect(chat).toContain(
      "visibleComposerResponseActions(latestAi?.actions ?? [])",
    );
    expect(message).toMatch(
      /import \{\s*actionHasCardScopedOwnership\s*\} from "@\/lib\/chat-action-ownership";/,
    );
    expect(message).toContain("const footerMessageActions =");
    expect(message).toContain("!actionHasCardScopedOwnership(action)");
    expect(message).toContain("const shouldShowAssistantFooter =");
    expect(message).toContain("!isUser && !isStreaming");
    expect(message).toContain("{shouldShowAssistantFooter &&");
    expect(message).toContain("isLatest || rating || showOptions || Boolean(retryAction)");
    expect(message).toContain("group-hover:opacity-100");
    expect(message).toContain("focus-within:opacity-100");
    expect(message).not.toContain("const shouldShowTextFooter =");
  });

  test("card-scoped confirmation actions close when the send is accepted", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const handleSendStart = chat.indexOf("const handleSend =");
    const handleSendEnd = chat.indexOf("const receiptFollowup", handleSendStart);
    const handleSendBlock = chat.slice(handleSendStart, handleSendEnd);
    const consumeIndex = handleSendBlock.indexOf(
      "consumeConfirmationActionOnMessages",
    );

    expect(handleSendStart).toBeGreaterThan(-1);
    expect(handleSendBlock).not.toContain("admitSend");
    expect(consumeIndex).toBeGreaterThan(-1);
    expect(handleSendBlock).toContain("setMessages((prev) =>");
  });

  test("a send does not take the guest admission path", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const emptyChat = readFileSync(
      join(root, "components/chat/EmptyChatSurface.tsx"),
      "utf-8",
    );
    const handleSendStart = chat.indexOf("const handleSend =");
    const handleSendEnd = chat.indexOf("const receiptFollowup", handleSendStart);
    const handleSendBlock = chat.slice(handleSendStart, handleSendEnd);

    expect(handleSendBlock).toContain("sendAdmissionInFlightRef.current");
    expect(handleSendBlock).not.toContain("setGuestSubmissionPending");
    expect(handleSendBlock).not.toContain("admitSend");
    expect(emptyChat).not.toContain("guest.entry.sending");
    expect(emptyChat).not.toContain("guestSubmissionPending");
  });

  test("final recovery responses hydrate retry controls from structured metadata", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );

    expect(chat).toContain("retryLastTurnActionFromMetadata");
    expect(chat).toContain("const finalMessageId =");
    expect(chat).toContain("failedActionRetryActionFromMetadata(finalPayload)");
    expect(chat).toContain("retryLastTurnActionFromMetadata(finalPayload");
    expect(chat).not.toContain("Please retry in a moment");
  });

  test("async job cards only promise retry when the turn has a retry action", () => {
    const card = readFileSync(
      join(root, "components/chat/BacktestJobCard.tsx"),
      "utf-8",
    );
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );

    expect(card).toContain("canRetry?: boolean");
    expect(card).toContain("backtestJobCardCopy(job, { canRetry })");
    expect(card).toContain("artifactStatusToneClassName(copy.tone)");
    expect(card).not.toContain("const toneClasses");
    expect(message).toContain("canRetry={Boolean(retryAction)}");
  });

  test("result card keeps lifecycle completion neutral after save is retired", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );

    // Completion is passive muted text — never a success tone and no longer a
    // button-shaped pill. The retired Strategy save state must not return.
    expect(card).not.toContain('artifactStatusToneClassName("neutral")');
    expect(card).toContain(
      "Passive status, not an action: plain muted text",
    );
    expect(card).not.toContain('artifactStatusToneClassName("success")');
    expect(card).toContain("view.hero.tone === \"positive\"");
  });

  test("assistant more menu hides internal message ids", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );

    expect(message).toContain("chat.copy_plaintext");
    expect(message).toContain("chat.report_issue");
    expect(message).not.toContain("chat.copy_id");
    expect(message).not.toContain("handleCopy(message.id)");
  });

  test("stream error handling settles confirmation artifacts and offers no stale next moves", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const errorStart = chat.indexOf('if (event.event === "error")');
    const errorEnd = chat.indexOf('if (event.event === "final")', errorStart);
    const errorBlock = chat.slice(errorStart, errorEnd);

    expect(errorStart).toBeGreaterThan(-1);
    expect(errorBlock).toContain("retryLastTurnActionFromMetadata(errorPayload");
    // Stale options no longer need clearing on error: next-move rows render
    // only on the newest assistant message, and the error message replaces it.
    expect(chat).not.toContain("setInputActions");
    expect(errorBlock).toContain("settleOpenConfirmationsAfterStreamError(");
    expect(errorBlock).not.toContain("settleOpenConfirmationsAfterTextFinal(");
  });
});
