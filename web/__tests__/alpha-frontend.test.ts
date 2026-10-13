import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { join } from "node:path";
import i18next from "i18next";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import {
  ChatStreamError,
  parseChatStreamFrame,
  resultCardFromRun,
  streamChatMessage,
  type ChatStreamEvent,
} from "../lib/argus-api";
import { commandPaletteRequestIsCurrent } from "../lib/command-palette-items";
import { effectivePaletteLayout } from "../components/sidebar/command-palette/paletteLayout";
import ChatMessage from "../components/chat/ChatMessage";
import { standaloneStreamStatusVisible } from "../components/chat/chat-message-projection";
import type { Message } from "../components/chat/types";
import en from "../public/locales/en/common.json";

const root = join(import.meta.dir, "..");

async function renderConfirmationMessage(kind?: string, active = true) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", fallbackLng: false, resources: { en: { translation: en } } });
  const message = {
    id: "confirmation-message", role: "ai", kind: "strategy_confirmation",
    confirmation: {
      ...(kind === undefined ? {} : { kind }),
      confirmation_id: "confirmation-1",
      confirmation_state: active ? "active" : "superseded",
      title: "AAPL", status: active ? "ready_to_run" : "updated",
      statusLabel: active ? "Ready to run" : "Updated",
      rows: [{ key: "assets", label: "Assets", value: "AAPL" }],
      actions: [{ id: "run-backtest", type: "run_backtest", label: "Run backtest",
        payload: { confirmation_id: "confirmation-1" } }],
    },
  } as unknown as Message;
  return renderToStaticMarkup(createElement(
    I18nextProvider, { i18n }, createElement(ChatMessage, { message }),
  ));
}

function readChatImplementationSource(): string {
  return [
    readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8"),
    readFileSync(
      join(root, "components/chat/chat-message-projection.ts"),
      "utf-8",
    ),
  ].join("\n");
}

describe("Argus Alpha frontend contract", () => {
  test("maps API conversation_result_card into chat result payload", () => {
    const result = resultCardFromRun({
      id: "run-1",
      status: "completed",
      asset_class: "equity",
      symbols: ["TSLA"],
      allocation_method: "equal_weight",
      benchmark_symbol: "SPY",
      metrics: { aggregate: {}, by_symbol: {} },
      config_snapshot: {},
      created_at: "2026-04-24T00:00:00Z",
      conversation_result_card: {
        title: "TSLA RSI Mean Reversion",
        date_range: {
          start: "2025-04-23",
          end: "2026-04-23",
          display: "April 23, 2025 to April 23, 2026",
        },
        status_label: "Simulation Complete",
        rows: [
          {
            key: "total_return_pct",
            label: "Total Return (%)",
            value: "+12.4%",
          },
          {
            key: "cash_value",
            label: "Cash Value ($)",
            value: "$1.0k -> $2.0k",
          },
          {
            key: "benchmark_delta",
            label: "Vs benchmark",
            value: "+4.2 pts vs SPY",
          },
          { key: "max_drawdown_pct", label: "Max Drawdown", value: "-8.1%" },
        ],
        assumptions: ["Long-only.", "Benchmark: SPY."],
        actions: [{ type: "save_strategy", label: "Save strategy" }],
        benchmark_note: "Long-only. Benchmark: SPY.",
        chart: {
          kind: "portfolio_equity",
          series: [{ time: "2026-01-02", value: 10000 }],
          attribution: "TradingView Lightweight Charts",
        },
      },
    });

    expect(result.strategyName).toBe("TSLA RSI Mean Reversion");
    expect(result.period).toBe("April 23, 2025 to April 23, 2026");
    expect(result.metrics).toEqual([
      { key: "cash_value", label: "Ending value", value: "$1.0k -> $2.0k" },
      { key: "total_return_pct", label: "Total return", value: "+12.4%" },
      { key: "benchmark_delta", label: "Compared with SPY", value: "+4.2 pts vs SPY" },
      { key: "max_drawdown_pct", label: "Worst drop", value: "-8.1%" },
    ]);
    expect("benchmarkNote" in result).toBe(false);
    expect(result.chart?.kind).toBe("portfolio_equity");
  });

  test("legacy collections and strategies surfaces are removed", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const sidebar = readFileSync(
      join(root, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );
    const deleted = readFileSync(
      join(root, "components/settings/DeletedItemsView.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const flags = readFileSync(
      join(root, "lib/private-alpha-flags.ts"),
      "utf-8",
    );

    expect(flags).not.toContain("NEXT_PUBLIC_COLLECTIONS_ENABLED");
    expect(flags).not.toContain("NEXT_PUBLIC_STRATEGIES_ENABLED");
    expect(chat).not.toContain("collectionsEnabled");
    expect(chat).toContain("useRecentConversations");
    expect(chat).not.toContain("trigger_create_collection");
    expect(chat).not.toContain("CollectionsView");
    expect(chat).not.toContain("CollectionPicker");
    expect(sidebar).not.toContain("Collections");
    expect(deleted).not.toContain("collection");
    expect(deleted).toContain("items.filter(isDeletedItemVisible)");
    expect(deleted).not.toContain("strategy");
    expect(deleted).not.toContain("<Layers");
    expect(deleted).not.toContain("{item.type}");
    expect(palette).toContain("item.canManageConversation");
    expect(
      existsSync(join(root, "components/views/CollectionsView.tsx")),
    ).toBe(false);
    expect(
      existsSync(join(root, "components/chat/CollectionPicker.tsx")),
    ).toBe(false);
    expect(
      existsSync(join(root, "components/views/StrategiesView.tsx")),
    ).toBe(false);
  });

  test("chat header keeps the history options affordance", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const headerMenu = readFileSync(
      join(root, "components/chat/ChatHeaderMenu.tsx"),
      "utf-8",
    );

    expect(chat).toContain("<ChatHeaderMenu");
    expect(headerMenu).toContain(
      'aria-label={t("chat.chat_options", "Chat options")}',
    );
    expect(headerMenu).toContain("MoreVertical");
    expect(headerMenu).toContain("chat.rename_chat");
    expect(headerMenu).toContain("chat.pin_chat");
    expect(headerMenu).toContain("chat.unpin_chat");
    for (const source of [chat, headerMenu]) {
      expect(source).not.toContain("chat.copy_conversation_link");
      expect(source).not.toContain("handleCopyConversationLink");
      expect(source).not.toContain("chat.add_to_collection");
      expect(source).not.toContain('aria-label="Archived chats"');
    }
  });

  test("sidebar logo swap preserves toggle behavior and archives the legacy mark", () => {
    const sidebar = readFileSync(
      join(root, "components/sidebar/SidebarHeader.tsx"),
      "utf-8",
    );
    const logo = readFileSync(join(root, "components/ArgusLogo.tsx"), "utf-8");
    const legacyPath = join(root, "components/ArgusLogoLegacy.tsx");
    const faviconPath = join(root, "app/favicon.ico");

    expect(sidebar).toContain("onClick={onToggle}");
    expect(sidebar).toContain(
      '<PanelLeft className="h-5 w-5 text-black/60 dark:text-white/60" />',
    );
    // One brand on every surface: the approved Cuadrao mark in both themes, never the Argus mark.
    assert.ok(sidebar.includes("<CuadraoMark size={32}") && !sidebar.includes("ArgusLogo") && !sidebar.includes("useConversationSurface"));
    const mark = readFileSync(join(root, "components/CuadraoMark.tsx"), "utf-8");
    assert.ok(mark.includes('src="/brand/cuadrao-mark-light.svg"') && mark.includes('src="/brand/cuadrao-mark-dark.svg"'));
    expect(existsSync(legacyPath)).toBe(true);
    expect(existsSync(faviconPath)).toBe(true);

    const legacy = existsSync(legacyPath)
      ? readFileSync(legacyPath, "utf-8")
      : "";
    const favicon = existsSync(faviconPath)
      ? readFileSync(faviconPath)
      : Buffer.from([]);
    expect(legacy).toContain("Outer Portal - The Sandbox / Gateway");
    expect(legacy).toContain(
      '<circle cx="12" cy="15" r="1.5" fill="currentColor" />',
    );
    expect(favicon.length).toBeGreaterThan(1024);
    expect([...favicon.subarray(0, 4)]).toEqual([0, 0, 1, 0]);
    expect(logo).toContain("argus-angular-a-mark");
    expect(logo).toContain("vtracer-t120-polygon");
    expect(logo).toContain('viewBox="0 0 473 447"');
    expect(logo).toContain('fill="currentColor"');
    expect(logo).not.toContain("Outer Portal - The Sandbox / Gateway");
    expect(logo).not.toContain('stroke="currentColor"');
  });

  test("private-alpha defaults hide exploratory chat suggestions while keeping starter chips", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const emptyChat = readFileSync(
      join(root, "components/chat/EmptyChatSurface.tsx"),
      "utf-8",
    );
    const starterActions = readFileSync(
      join(root, "components/chat/StarterActions.tsx"),
      "utf-8",
    );
    const input = readFileSync(
      join(root, "components/chat/ChatInput.tsx"),
      "utf-8",
    );
    const flags = readFileSync(
      join(root, "lib/private-alpha-flags.ts"),
      "utf-8",
    );
    const envExample = readFileSync(join(root, ".env.local.example"), "utf-8");
    const enSource = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );
    const esSource = readFileSync(
      join(root, "public/locales/es-419/common.json"),
      "utf-8",
    );
    const en = JSON.parse(enSource);
    const es = JSON.parse(esSource);

    // The research rail replaced the exploratory-suggestions flag and retired
    // the composer typewriter; suggestions ship behind the rail flag instead.
    expect(flags).toContain("NEXT_PUBLIC_RESEARCH_RAIL_ENABLED");
    expect(flags).toContain("researchRailEnabled");
    expect(flags).not.toContain("chatExploratorySuggestionsEnabled");
    expect(envExample).toContain("NEXT_PUBLIC_RESEARCH_RAIL_ENABLED=false");
    expect(envExample).not.toContain(
      "NEXT_PUBLIC_CHAT_EXPLORATORY_SUGGESTIONS_ENABLED",
    );
    expect(emptyChat).toContain("researchRailEnabled");
    // No control gates the chips. They render whenever the empty chat does and
    // stop when it stops, so there is nothing to show, hide, or persist.
    expect(emptyChat).not.toContain("showSuggestions");
    expect(chat).not.toContain("showSuggestions");
    expect(en.chat.show_suggestions).toBeUndefined();
    expect(en.chat.hide_suggestions).toBeUndefined();
    expect(es.chat.show_suggestions).toBeUndefined();
    expect(es.chat.hide_suggestions).toBeUndefined();
    expect(starterActions).toContain("chat.starter_actions.tsla.value");
    expect(starterActions).toContain("chat.starter_actions.btc.value");
    expect(starterActions).toContain("chat.starter_actions.dca.value");
    expect(starterActions).toContain("chat.example_queries");
    expect(emptyChat).toContain("<StarterActions");
    expect(input).not.toContain("placeholder_prompts");
    expect(input).not.toContain("animState");
    expect(input).toContain("placeholder");
    expect(chat).toContain("chat.followup_placeholder");
    expect(en.chat.placeholder_prompts).toBeUndefined();
    expect(es.chat.placeholder_prompts).toBeUndefined();

    const starterAndPlaceholderText = [
      en.chat.starter_actions.tsla.value,
      en.chat.starter_actions.btc.value,
      en.chat.starter_actions.dca.value,
      es.chat.starter_actions.tsla.value,
      es.chat.starter_actions.btc.value,
      es.chat.starter_actions.dca.value,
      en.chat.example_queries.q1,
      en.chat.example_queries.q2,
      en.chat.example_queries.q3,
      es.chat.example_queries.q1,
      es.chat.example_queries.q2,
      es.chat.example_queries.q3,
    ].join("\n");

    expect(starterAndPlaceholderText).not.toContain("2024");
    expect(starterAndPlaceholderText).not.toContain("January 1");
    expect(starterAndPlaceholderText).not.toContain("December 31");
    expect(starterAndPlaceholderText).not.toContain("1 de enero");
    expect(starterAndPlaceholderText).not.toContain("31 de diciembre");
    expect(starterAndPlaceholderText).not.toContain("Strategy:");
    expect(starterAndPlaceholderText).not.toContain("Asset:");
    expect(starterAndPlaceholderText).not.toContain("Period:");
    expect(starterAndPlaceholderText).not.toContain("Estrategia:");
    expect(starterAndPlaceholderText).not.toContain("Activo:");
    expect(starterAndPlaceholderText).not.toContain("Periodo:");
    expect(en.chat.starter_actions.tsla.value).toBe(
      "Compare Apple with SPY over the last 12 months.",
    );
    expect(en.chat.starter_actions.btc.value).toBe(
      "What if I bought Bitcoin this year so far?",
    );
    expect(en.chat.starter_actions.dca.value).toBe(
      "What if I bought $250 of Nvidia every week over the last 12 months?",
    );
    expect(es.chat.starter_actions.tsla.value).toBe(
      "Compara Apple con SPY durante los últimos 12 meses.",
    );
    expect(es.chat.starter_actions.btc.value).toBe(
      "¿Qué habría pasado si compraba Bitcoin en lo que va del año?",
    );
    expect(es.chat.starter_actions.dca.value).toBe(
      "¿Qué habría pasado si compraba $250 de Nvidia cada semana durante el último año?",
    );
  });

  test("assistant turn controls use shared tooltips and robust clipboard copy", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );

    expect(message).toContain(
      'import { Tooltip } from "@/components/ui/Tooltip";',
    );
    expect(message).toContain(
      'import { writeClipboardText } from "@/lib/clipboard";',
    );
    expect(message).toContain("writeClipboardText(text)");
    expect(message).toContain("Tooltip content={t('chat.good_response')}");
    expect(message).toContain("Tooltip content={t('chat.poor_response')}");
    expect(message).toContain("Tooltip content={t('chat.more_actions')}");
    expect(message).not.toContain("navigator.clipboard.writeText");
  });

  test("chat result messages preserve assistant explanation next to card", () => {
    const chat = readChatImplementationSource();
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );

    expect(chat).toContain("content: message.content");
    // The card's gate is the shared settled-result check, which owns the kind test.
    expect(message).toContain("isSettledStrategyResult(message)");
    expect(
      readFileSync(join(root, "lib/chat-result-message.ts"), "utf-8"),
    ).toContain('message.kind === "strategy_result"');
    expect(message).toContain("const displayContent = getDisplayContent()");
    expect(message).toContain("displayContent &&");
    expect(message).toContain("<StrategyResultCard");
    expect(message).toContain("result={message.result}");
    expect(message.indexOf("<StrategyResultCard")).toBeLessThan(
      message.indexOf("displayContent &&"),
    );
  });

  test("failed-action retry stays a structured footer action and message menus close on focus loss", () => {
    const chat = readChatImplementationSource();
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const hydration = readFileSync(
      join(root, "lib/chat-message-hydration.ts"),
      "utf-8",
    );
    const retry = readFileSync(
      join(root, "lib/chat-retry-actions.ts"),
      "utf-8",
    );
    const sendState = readFileSync(
      join(root, "lib/chat-send-state.ts"),
      "utf-8",
    );

    expect(chat).toContain("hydrateTextMessageFromApi(message,");
    expect(hydration).toContain(
      "failedActionRetryActionFromMetadata(metadata)",
    );
    expect(hydration).toContain("retryLastTurnActionFromMetadata(metadata");
    expect(chat).toContain("retryLastTurnActionFromMessage(trimmed,");
    expect(chat).toContain("assistantMessageId: assistantId");
    expect(chat).toContain("retryLastTurnFailedAssistantIdFromAction(action)");
    expect(chat).toContain("retryLastTurnMessageFromAction(action)");
    expect(chat).toContain(
      "appendOrReplacePendingAssistantMessage(baseMessages",
    );
    expect(chat).toContain("failedAssistantId");
    expect(chat).toContain("retryLastTurnSendOptions({ failedAssistantId, requestMessageId })");
    expect(chat).toContain("keepLocalTranscript");
    expect(chat).toContain("requestMessageId");
    expect(retry).toContain("replacementAssistantId: input.failedAssistantId");
    expect(retry).toContain("keepLocalTranscript");
    expect(retry).toContain("renderUserMessage: false");
    expect(retry).toContain("renderUserMessage: true");
    expect(chat).toContain(
      "const persistedErrorMessageId = event.data.message_id?.trim()",
    );
    expect(chat).toContain("id: persistedErrorMessageId || m.id");
    expect(chat).toContain("isFailedActionRetry(action)");
    expect(retry).toContain("latest_failed_action_reference");
    expect(retry).toContain("launch_payload");
    expect(retry).toContain("failed_assistant_id");
    expect(retry).toContain('type: "retry_failed_action"');
    expect(retry).toContain('type: "retry_last_turn"');
    expect(retry).toContain("export function isRetryAction");
    expect(sendState).toContain(
      "export function appendOrReplacePendingAssistantMessage",
    );
    expect(sendState).toContain("message.id !== assistantId");
    expect(retry).not.toContain("content.includes");
    expect(retry).not.toContain(".match(");
    // Action labels localize where the actions now render: next-move rows own
    // labelKey interpolation since the floating composer strip was removed.
    expect(message).toContain(
      "const actionLabel = (action: ChatActionOption) =>",
    );
    expect(message).toContain("{actionLabel(action)}");
    expect(chat).toContain("const actionDisplayLabel = useCallback");
    expect(chat).toContain(
      "content: action?.type ? actionDisplayLabel(action) : trimmed",
    );
    expect(chat).not.toContain("content: action?.label ?? trimmed");
    expect(chat).not.toContain(
      "{action.label}\n                          </button>",
    );
    expect(message).toContain("? t(action.labelKey, {");
    expect(message).toContain("defaultValue: action.label,");
    expect(message).toContain(
      '(message.selectedAction ? actionLabel(message.selectedAction) : "")',
    );
    expect(message).toContain("const retryAction = message.actions?.find");
    expect(message).toContain("message.actions?.find(isRetryAction)");
    expect(message).toContain("const footerMessageActions =");
    expect(message).toContain("!actionHasCardScopedOwnership(action)");
    expect(message).toContain("const shouldShowAssistantFooter =");
    expect(message).toContain("!isUser && !isStreaming");
    expect(message).toContain("{shouldShowAssistantFooter &&");
    expect(message).toContain(
      "isLatest || rating || showOptions || Boolean(retryAction)",
    );
    expect(message).toContain("group-hover:opacity-100");
    expect(message).toContain("focus-within:opacity-100");
    expect(message).toContain("<RotateCcw");
    expect(message.indexOf("<ThumbsDown")).toBeLessThan(
      message.indexOf("<RotateCcw"),
    );
    expect(message.indexOf("<RotateCcw")).toBeLessThan(
      message.indexOf("<MoreHorizontal"),
    );
    expect(message).not.toContain("const optionsCloseTimeoutRef = useRef");
    expect(message).not.toContain("const scheduleOptionsClose = () =>");
    expect(message).not.toContain("onMouseLeave={scheduleOptionsClose}");
    expect(message).toContain("aria-expanded={showOptions}");
    expect(message).toContain(
      "isLatest || rating || showOptions || Boolean(retryAction)",
    );
    expect(message).toContain("onBlur={(event) =>");
    expect(message).toContain("setShowOptions(false)");
    expect(chat).toContain("const finalRetryActions = [");
    expect(chat).toContain("failedActionRetryActionFromMetadata(finalPayload)");
    expect(chat).toContain("const finalResponseActions =");
    expect(chat).toContain(
      "recoveryActionsFromMetadata(finalPayload, finalMessageId)",
    );
    expect(chat).toContain("...finalResponseActions");
    expect(chat).toContain("...finalRetryActions");
    expect(chat).toContain("mergeFinalTextMessage(m, {");
    expect(chat).toContain("finalActions: finalTextActions");
  });

  test("result cards render a separate trust strip and compact assumption details", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );
    const en = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );

    expect(card).toContain("TrustRail");
    expect(card).toContain("ExecutionDetails");
    expect(card).toContain("view.details");
    expect(card).toContain("result_trust_strip");
    expect(card).toContain("Result trust context");
    expect(card).not.toContain("result.assumptions.map");
    expect(en).toContain(
      "Historical simulation · No fees/slippage · Not advice",
    );
  });

  test("result readouts use a structured editorial treatment", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const css = readFileSync(join(root, "app/globals.css"), "utf-8");
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    expect(message).toContain("function ResultReadout");
    // Issue #249: the accessible section name is the localized label.
    expect(message).toContain("aria-label={label}");
    expect(message).toContain(
      'label={t("chat.result_readout.quick_take", "Quick take")}',
    );
    expect(message).toContain(
      '<div className="argus-result-section-label">{label}</div>',
    );
    expect(en.chat.result_readout.quick_take).toBe("Quick take");
    expect(es.chat.result_readout.quick_take).toBe("Lectura rápida");
    expect(css).toContain(".argus-result-readout::before");
    expect(css).toContain("text-wrap: pretty");
    expect(css).not.toContain("argus-result-readout shadow");
  });

  test("result breakdowns render as a distinct fact-grounded surface", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const css = readFileSync(join(root, "app/globals.css"), "utf-8");

    expect(message).toContain("function ResultBreakdown");
    expect(message).toContain(
      'ariaLabel={t("chat.result_breakdown.aria_label", "Result breakdown")}',
    );
    expect(message).toContain(
      'label={t("chat.result_breakdown.label", "Breakdown")}',
    );
    expect(message).toContain("argus-result-section-label");
    expect(message).toContain("{label}");
    expect(message).not.toContain(
      '<div className="argus-result-section-label">Breakdown</div>',
    );
    expect(message).toContain(
      'message.contentPresentation === "result_breakdown" && displayContent.trim()',
    );
    expect(chat).toContain('action?.type === "show_breakdown"');
    expect(chat).toContain("contentPresentation:");
    expect(css).toContain(".argus-result-breakdown::before");
    expect(css).toContain('content: ""');
    expect(css).toContain("border-left");
    expect(css).not.toContain("argus-result-breakdown shadow");
  });

  test("result card hides save by default while keeping explain and refine actions", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );
    const flags = readFileSync(
      join(root, "lib/private-alpha-flags.ts"),
      "utf-8",
    );
    const labelHelper = readFileSync(
      join(root, "lib/result-card-display.ts"),
      "utf-8",
    );
    const chart = readFileSync(
      join(root, "components/chat/ResultEquityChart.tsx"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );

    expect(card).toContain("<ResultEquityChart");
    expect(card).toContain('presentation="heroDeltaEvidence"');
    expect(card).toContain("appearanceOverride={appearance}");
    expect(flags).not.toContain("NEXT_PUBLIC_STRATEGIES_ENABLED");
    expect(card).not.toContain("strategiesEnabled");
    expect(card).not.toContain('action.type === "save_strategy"');
    expect(labelHelper).toContain('"Explain result"');
    expect(labelHelper).toContain('"Refine idea"');
    expect(card).not.toContain("<Save");
    expect(chat).not.toContain("handleSaveStrategyAction");
    expect(chart).toContain("BaselineSeries");
    expect(chart).toContain("createSeriesMarkers");
    expect(chart).toContain("buildVisibleSeriesMarkers");
    expect(chart).toContain("selectVisibleTradeMarkers");
    expect(chart).toContain("subscribeVisibleLogicalRangeChange");
    expect(chart).toContain("markersApi.setMarkers");
    expect(chart).toContain("resultChartAttributionLabel(chart.attribution)");
    expect(chart).toContain("attributionLogo: true");
    expect(chart).not.toContain("attributionLogo: false");
    expect(chart).toContain('data-testid="result-equity-chart-attribution"');
    expect(chart).toContain("RESULT_CHART_ATTRIBUTION_URL");
    expect(chart).toContain('from "@/lib/chart-attribution"');
    const launchAttributionDebt =
      "TO" +
      "DO(launch): Provide correct TradingView attribution before launch.";
    expect(chart).not.toContain(launchAttributionDebt);
    expect(chart).toContain('const CHART_POSITIVE_COLOR = "#70a38d"');
    expect(chart).toContain('const CHART_NEGATIVE_COLOR = "#b85c5c"');
    expect(chart).toContain('const BUY_POSITIVE_MARKER_COLOR = "#70a38d"');
    expect(chart).toContain('const SELL_NEGATIVE_MARKER_COLOR = "#b85c5c"');
    expect(chart).not.toContain("#315d97");
    expect(chart).not.toContain("#a98b2d");
    expect(chart).toContain('data-testid="result-equity-chart"');
    expect(chart).toContain("chartTimeLookupKey");
  });

  test("chat renders structured confirmation cards with card-scoped actions only", async () => {
    const chat = readChatImplementationSource();
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    const ownership = readFileSync(
      join(root, "lib/chat-action-ownership.ts"),
      "utf-8",
    );

    expect(api).toContain('event: "final"');
    expect(chat).toContain('kind: "strategy_confirmation"');
    expect(chat).toContain('latestAi?.kind === "strategy_confirmation"');
    expect(ownership).toContain("isCardScopedAction");
    expect(chat).toContain('from "@/lib/chat-action-ownership"');
    expect(chat).toContain("hasActiveArtifactActionSet(messages)");
    // Card-scoped actions never become conversational next-move rows; the row
    // list is filtered per message and suppressed while a card owns actions.
    expect(message).toContain("!actionHasCardScopedOwnership(action)");
    expect(chat).toContain("!hasActiveArtifactActionSet(messages)");
    expect(chat).not.toContain("setInputActions(confirmation.actions ?? [])");
    expect(chat).not.toContain("visibleInputActions(inputActions).map");
    expect(chat).not.toContain('event.event === "confirmation"');
    expect(chat).not.toContain('event.event === "result"');
    // The entrance motion belongs to the message that carries the actions now
    // that the floating composer strip is gone.
    expect(message).toContain("slide-in-from-bottom-2");
    expect(message).toContain("<StrategyConfirmationCard");
    const markup = await renderConfirmationMessage("backtest");
    expect(markup).toContain("argus-confirmation-reveal");
    expect(markup.match(/Run backtest/g)).toHaveLength(1);
    expect(message).toContain("onAction={onAction}");
  });

  test("artifact cards use compositor-safe reveal motion with a reduced-motion opt out", () => {
    const css = readFileSync(join(root, "app/globals.css"), "utf-8");
    const resultCard = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );
    const confirmationCard = readFileSync(
      join(root, "components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );

    expect(resultCard).toContain("argus-card-reveal");
    expect(resultCard).toContain("argus-result-reveal-positive");
    expect(resultCard).toContain("argus-result-reveal-caution");
    expect(confirmationCard).toContain("argus-card-reveal");
    expect(confirmationCard).toContain("argus-confirmation-reveal");
    expect(css).toContain(".argus-card-reveal");
    expect(css).toContain("will-change: transform, opacity, border-color;");
    expect(css).toContain("translate3d(0, 10px, 0)");
    expect(css).toContain("translate3d(0, 12px, 0)");
    expect(css).toContain("transform: translate3d(0, 0, 0) scale(1);");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("animation: none;");
  });

  test("next moves hide whenever any active card owns the conversation's actions", () => {
    const chat = readChatImplementationSource();

    const activeArtifactHelper = chat.slice(
      chat.indexOf("function hasActiveArtifactActionSet"),
      chat.indexOf("function consumeConfirmationActionOnMessages"),
    );

    expect(activeArtifactHelper).toContain("messages.some");
    expect(activeArtifactHelper).toContain(
      'confirmation.confirmation_state !== "active"',
    );
    expect(activeArtifactHelper).toContain("actionHasCardScopedOwnership");
    expect(activeArtifactHelper).not.toContain("latestAi");

    // The floating composer strip is gone. Its gating survives on the row list:
    // no next moves mid-turn or while a card owns actions. The in-flight lock
    // is shared with the composer so persistent rows cannot bypass it.
    const inFlight = chat.slice(
      chat.indexOf("const turnInFlight ="),
      chat.indexOf("const nextMovesEnabled ="),
    );
    expect(inFlight).toContain("visibleStreamStatus");
    expect(inFlight).toContain("isStreamingResponse");
    expect(inFlight).toContain("isHydratingConversation");
    const gate = chat.slice(
      chat.indexOf("const nextMovesEnabled ="),
      chat.indexOf("const latestAssistantContent"),
    );
    expect(gate).toContain("!turnInFlight");
    expect(gate).toContain("!hasActiveArtifactActionSet(messages)");
    expect(chat).toContain("nextMovesEnabled={nextMovesEnabled}");
    expect(chat).toContain("turnInFlight={turnInFlight}");
    expect(chat).not.toContain("const composerActions =");
  });

  test("chat supersedes older confirmation cards when a newer draft appears", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const artifactHistory = readFileSync(
      join(root, "components/chat/artifact-history.ts"),
      "utf-8",
    );
    const card = readFileSync(
      join(root, "components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );
    const types = readFileSync(join(root, "components/chat/types.ts"), "utf-8");
    // Row localization moved into the view model the card and Copy share (#509).
    const viewModel = readFileSync(
      join(root, "lib/confirmation-card-view-model.ts"),
      "utf-8",
    );

    expect(types).toContain(
      'confirmation_state?: "active" | "superseded" | "cancelled"',
    );
    expect(types).toContain("confirmation_id?: string");
    expect(chat).toContain("normalizeConfirmationHistory");
    expect(chat).toContain('from "./artifact-history"');
    expect(artifactHistory).toContain("supersedePriorConfirmations");
    expect(artifactHistory).toContain("function isTerminalConfirmation");
    expect(card).toContain("confirmationStatusFromPayload");
    expect(card).toContain("confirmationStatusLabelKey");
    expect(viewModel).toContain("confirmationRowKey(row)");
    expect(card).toContain("function confirmationDisplayState");
    expect(card).not.toContain("row.label.toLowerCase()");
    expect(viewModel).not.toContain("row.label.toLowerCase()");
    expect(card).not.toContain('normalizedLabel === "running"');
    expect(viewModel).toContain(
      't("chat.confirmation.selected_asset", "Selected asset")',
    );
  });

  test("chat supersedes active confirmations when a later turn asks for recovery", () => {
    const chat = readChatImplementationSource();
    const artifactHistory = readFileSync(
      join(root, "components/chat/artifact-history.ts"),
      "utf-8",
    );

    expect(chat).toContain("settleOpenConfirmationsAfterTextFinal");
    expect(artifactHistory).toContain("supersedeOpenConfirmations");
    expect(artifactHistory).toContain("could_not_run");
    expect(artifactHistory).toContain("confirmationStatusLabel");
    expect(artifactHistory).toContain('artifactType === "failed_action"');
    expect(chat).toContain("finalStageOutcome");
    expect(chat).toContain('finalStageOutcome === "await_user_reply"');
    expect(chat).toContain('finalStageOutcome === "needs_clarification"');
  });

  test("chat final payload accepts pending strategy metadata", () => {
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");

    expect(api).toContain("pending_strategy?");
    expect(api).toContain("missing_required_fields?: string[]");
    expect(api).toContain("strategy: Record<string, unknown>");
    expect(api).toContain("pending_resolution?");
  });

  test("confirmation action chips render as action transcript items", () => {
    const chat = readChatImplementationSource();
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const types = readFileSync(join(root, "components/chat/types.ts"), "utf-8");

    expect(types).toContain('"action"');
    expect(chat).toContain('kind: action?.type ? "action" : "text"');
    expect(chat).toContain("chatActionRequestFromAction");
    expect(chat).toContain("labelKey: action.labelKey");
    expect(chat).toContain("selectedAction: action");
    expect(chat).toContain("metadata.chat_action");
    expect(message).toContain('message.kind === "action"');
  });

  test("streaming backend errors keep backend detail when provided", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );

    expect(chat).toContain("chatStreamErrorText(");
    expect(chat).toContain("event.data.detail");
    expect(chat).toContain("err instanceof ChatStreamError && err.message");
  });

  test("chat stream parser consumes canonical data-only SSE frames", () => {
    const stage = parseChatStreamFrame(
      'data: {"type":"stage_start","stage":"execute"}',
    );
    const token = parseChatStreamFrame(
      'data: {"type":"token","content":"Running"}',
    );
    const error = parseChatStreamFrame(
      'data: {"type":"error","code":"agent_runtime_failure","message":"Something went wrong.","message_id":"assistant-persisted-1","retry_last_turn":{"message":"test AAPL"},"recovery":{"code":"runtime_failure","retryable":true,"language":"en"}}',
    );
    const done = parseChatStreamFrame("data: [DONE]");

    expect(stage).toEqual({ event: "stage_start", data: { stage: "execute" } });
    expect(token).toEqual({ event: "token", data: { text: "Running" } });
    expect(error).toEqual({
      event: "error",
      data: {
        code: "agent_runtime_failure",
        detail: "Something went wrong.",
        message_id: "assistant-persisted-1",
        retry_last_turn: { message: "test AAPL" },
        recovery: {
          code: "runtime_failure",
          retryable: true,
          language: "en",
        },
      },
    });
    expect(done).toEqual({ event: "done", data: { message_id: null } });
  });

  test("chat stream rejects truncated responses before done", async () => {
    const originalFetch = globalThis.fetch;
    const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    const encoder = new TextEncoder();
    const events: ChatStreamEvent[] = [];

    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'data: {"type":"stage_start","stage":"interpret"}\n\n',
                ),
              );
              controller.close();
            },
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "text/event-stream",
              "X-Request-Id": "request-a",
            },
          },
        ),
      )) as typeof fetch;

    let caught: unknown;
    try {
      await streamChatMessage("conversation-1", "test AAPL", "en", (event) => {
        events.push(event);
      });
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

    expect(events).toEqual([
      { event: "stage_start", data: { stage: "interpret" } },
    ]);
    expect(caught).toBeInstanceOf(ChatStreamError);
    expect((caught as ChatStreamError).code).toBe("stream_interrupted");
    expect((caught as ChatStreamError).requestId).toBe("request-a");
  });

  test("chat stream preserves its submitted request id when CORS hides the response header", async () => {
    const originalFetch = globalThis.fetch;
    const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    let submittedRequestId: string | null = null;

    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    globalThis.fetch = ((_input, init) => {
      submittedRequestId = new Headers(init?.headers).get("X-Request-Id");
      return Promise.resolve(
        new Response(
          new ReadableStream({ start: (controller) => controller.close() }),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
      );
    }) as typeof fetch;

    let caught: unknown;
    try {
      await streamChatMessage("conversation-1", "test AAPL", "en", () => {});
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

    expect(submittedRequestId).toBeTruthy();
    expect(caught).toBeInstanceOf(ChatStreamError);
    expect((caught as ChatStreamError).requestId).toBe(submittedRequestId);
  });

  test("chat stream preserves its submitted request id when fetch rejects before headers", async () => {
    const originalFetch = globalThis.fetch;
    const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    let submittedRequestId: string | null = null;

    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    globalThis.fetch = ((_input, init) => {
      submittedRequestId = new Headers(init?.headers).get("X-Request-Id");
      return Promise.reject(new TypeError("connection lost"));
    }) as typeof fetch;

    let caught: unknown;
    try {
      await streamChatMessage("conversation-1", "test AAPL", "en", () => {});
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

    expect(submittedRequestId).toBeTruthy();
    expect(caught).toBeInstanceOf(ChatStreamError);
    expect((caught as ChatStreamError).status).toBe(0);
    expect((caught as ChatStreamError).requestId).toBe(submittedRequestId);
  });

  test("chat stream treats backend error frames as terminal", async () => {
    const originalFetch = globalThis.fetch;
    const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    const encoder = new TextEncoder();
    const events: ChatStreamEvent[] = [];

    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    globalThis.fetch = (() =>
      Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'data: {"type":"error","code":"agent_runtime_failure","message":"Backtest provider timed out."}\n\n',
                ),
              );
              controller.close();
            },
          }),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      )) as typeof fetch;

    let caught: unknown;
    try {
      await streamChatMessage("conversation-1", "test AAPL", "en", (event) => {
        events.push(event);
      });
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

    expect(caught).toBeUndefined();
    expect(events).toEqual([
      {
        event: "error",
        data: {
          code: "agent_runtime_failure",
          detail: "Backtest provider timed out.",
          message_id: undefined,
        },
      },
    ]);
  });

  test("chat status is driven by backend stage_start events", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const locale = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );

    expect(chat).toContain('event.event === "stage_start"');
    expect(chat).toContain("toolProgressText(event.data.tool_progress ?? null, t)");
    expect(locale).not.toContain('"interpret": "Understanding your idea..."');
    expect(locale).not.toContain('"execute": "Running backtest..."');
  });

  test("latest pending assistant response hides feedback before stage_start arrives", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );

    const projection = readFileSync(
      join(root, "components/chat/chat-message-projection.ts"),
      "utf-8",
    );
    expect(chat).toContain("isStreamingResponse");
    expect(chat).toContain("messageStreamPresentation(");
    expect(chat).toContain("isWorkingMessage");
    expect(projection).toContain("latestAiIndex");
    expect(projection).toContain('(message.content ?? "") === ""');
    expect(chat).toContain("isStreaming={isWorkingMessage}");
    expect(message).toContain("const shouldShowAssistantFooter = !isUser && !isStreaming;");
    expect(message).toContain("{shouldShowAssistantFooter && (");
    expect(message).not.toContain("{copyFeedback && (");
  });

  test("stream status hides once assistant tokens are visible", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );

    const message: Message = { id: crypto.randomUUID(), role: "ai", kind: "text", content: "" };
    expect(standaloneStreamStatusVisible([message], true)).toBe(true);
    expect(standaloneStreamStatusVisible([{ ...message, content: "The answer has begun." }], true)).toBe(false);
    expect(chat).toContain("standaloneStreamStatusVisible(messages, Boolean(visibleStreamStatus))");
    expect(chat).toContain("{showStreamStatus && (");
  });

  test("chat composer prevents overlapping turns while stream is active", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const input = readFileSync(
      join(root, "components/chat/ChatInput.tsx"),
      "utf-8",
    );
    const emptyChat = readFileSync(
      join(root, "components/chat/EmptyChatSurface.tsx"),
      "utf-8",
    );

    expect(chat).toContain(
      "conversationActivity.isConversationLocked(targetConversationId)",
    );
    expect(chat).toContain(
      "conversationActivity.isConversationLocked(conversationId)",
    );

    expect(chat).toContain("sendAdmissionInFlightRef.current ||");
    expect(chat).toContain("sendAdmissionInFlightRef.current = true;");
    expect(`${chat}\n${emptyChat}`).toContain("<ChatInput");
    expect(chat).toContain("onSend={handleSend}");
    expect(emptyChat).toMatch(
      /const disabled =\s*isStreamingResponse \|\|\s*isHydratingConversation \|\|\s*guestSubmissionPending \|\|\s*guestSubmissionError === CAPTCHA_UNAVAILABLE_CODE/,
    );
    expect(emptyChat).toContain("disabled={disabled}");
    expect(chat).toContain("disabled={conversationComposerUnavailable}");
    expect(chat).toContain("placeholder={chatInputPlaceholder}");
    expect(chat).toContain('if (event.event === "final")');
    expect(chat).toContain(
      "createChatRequestSessionController",
    );
    expect(chat).toContain(
      'requestSessions.authorize(requestSession, "final")',
    );
    expect(chat).toContain(
      'requestSessions.authorize(\n            requestSession,\n            "title",',
    );
    expect(chat).toContain("finishRequestTransport(requestSession)");
    expect(chat).not.toContain("conversationActivity.settleRequest");
    expect(chat).not.toContain("setIsStreamingResponse(false);");
    expect(input).toContain("disabled?: boolean");
    expect(input).toContain("if (disabled) return;");
    expect(input).toContain("contentEditable={!disabled}");
    expect(input).toContain(
      "const sendButtonDisabled = composerIsEmpty || disabled;",
    );
    expect(input).toContain("disabled={sendButtonDisabled}");
  });

  test("chat restores jump-to-latest affordance without forced reading jumps", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const scrollControls = readFileSync(
      join(root, "components/chat/useChatScrollControls.ts"),
      "utf-8",
    );

    expect(chat).toContain("scrollContainerRef");
    expect(chat).toContain("showJumpToLatest");
    expect(chat.match(/<ConversationActivityJumpButton/g)).toHaveLength(1);
    expect(chat).not.toContain('aria-label="Jump to latest"');
    expect(scrollControls).toContain(
      "distanceFromBottom > JUMP_TO_LATEST_THRESHOLD_PX",
    );
    expect(chat).toContain("scrollToLatest");
    expect(chat).toContain("shouldAutoScrollRef.current");
  });

  test("chat hydrates persisted structured cards from message metadata", () => {
    const chat = readChatImplementationSource();
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    const artifactHistory = readFileSync(
      join(root, "components/chat/artifact-history.ts"),
      "utf-8",
    );

    expect(api).toContain("artifact_presentation_kind?");
    expect(chat).toContain("metadata.confirmation_card");
    expect(chat).toContain("metadata.result_card");
    expect(chat).toContain("isBreakdownActionMetadata(metadata)");
    expect(artifactHistory).toContain('chatAction.type === "show_breakdown"');
    expect(chat).toContain("resultCardFromConversationCard");
  });

  test("result actions carry canonical run and conversation context", () => {
    const chat = readChatImplementationSource();
    const resultActions = readFileSync(
      join(root, "lib/chat-result-actions.ts"),
      "utf-8",
    );

    expect(chat).toContain("hydrateResultActions");
    expect(resultActions).toContain("hydrateResultActions");
    expect(resultActions).toContain("runId: run.id");
    expect(resultActions).toContain("strategyId: run.strategy_id ?? null");
    expect(resultActions).toContain(
      "conversationId: run.conversation_id ?? undefined",
    );
    expect(chat).toContain("metadata.result_conversation_id");
    expect(chat).toContain("resultActionContextFromMetadata(metadata, card)");
    expect(chat).toContain("assetClassOrUndefined(factBank?.asset_class)");
    expect(chat).not.toContain('template: "",\n        assetClass: "equity"');
    expect(resultActions).toContain("resultActionRequiresRunContext");
    expect(resultActions).toContain(
      "hasResultActionContext(context.runId, context.conversationId)",
    );
    expect(resultActions).toContain('presentation: "result"');
  });

  test("artifact actions stay attached to historical cards", () => {
    const chat = readChatImplementationSource();

    expect(chat).toContain("markComposerActionsInactive");
    expect(chat).not.toContain(
      "prev.map((m) => ({ ...m, actions: undefined }))",
    );
    expect(chat).toContain("message.result.actions");
    expect(chat).toContain("message.confirmation.actions");
  });

  test.each([undefined, "backtest"])("only active recognized confirmation kind %p renders Run", async (kind) => {
    expect(await renderConfirmationMessage(kind)).toContain("Run backtest");
    expect(await renderConfirmationMessage(kind, false)).not.toContain("Run backtest");
    expect(await renderConfirmationMessage("future_calculation")).not.toContain("Run backtest");
  });

  test("result cards render only active artifact scoped actions", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );
    const resultActions = readFileSync(
      join(root, "lib/chat-result-actions.ts"),
      "utf-8",
    );
    expect(card).toContain('action.type === "show_breakdown"');
    expect(card).toContain('action.type === "refine_strategy"');
    expect(card).not.toContain('action.type === "save_strategy"');
    expect(card).toContain("isVisibleResultAction");
    expect(resultActions).toContain("VISIBLE_RESULT_ACTION_TYPES");
    expect(resultActions).toContain("isVisibleResultAction");
    expect(card).not.toContain("...resultActions.filter(");
    expect(resultActions).not.toContain("next_experiment");
    expect(resultActions).not.toContain("try_next");
    expect(resultActions).not.toContain('"save_strategy"');
  });

  test("legacy saved strategy metadata remains read-safe without a write action", () => {
    const chat = readChatImplementationSource();
    const types = readFileSync(join(root, "components/chat/types.ts"), "utf-8");

    expect(types).toContain("savedStrategyId?: string | null");
    expect(chat).toContain("hiddenSaveActionMessageIdsFromApi");
    expect(chat).toContain("saved_strategy_id");
    expect(chat).not.toContain("handleSaveStrategyAction");
    expect(chat).not.toContain("markResultCardSaved");
  });

  test("saved result state is not inferred from plain result strategy linkage", () => {
    const chat = readChatImplementationSource();

    const metadataHelper = chat.slice(
      chat.indexOf("function savedStrategyIdFromMetadata"),
      chat.indexOf("function savedStrategyIdFromFinalPayload"),
    );
    const finalPayloadHelper = chat.slice(
      chat.indexOf("function savedStrategyIdFromFinalPayload"),
      chat.indexOf("function resultRunIdFromFinalPayload"),
    );

    expect(metadataHelper).toContain("saved_strategy_id");
    expect(metadataHelper).not.toContain("result_strategy_id");
    expect(finalPayloadHelper).toContain("saved_strategy_id");
    expect(finalPayloadHelper).not.toContain("result_strategy_id");
  });

  test("assistant copy is artifact aware and visibly confirmed", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const toast = readFileSync(
      join(root, "components/chat/ChatToast.tsx"),
      "utf-8",
    );
    const en = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );
    const es = readFileSync(
      join(root, "public/locales/es-419/common.json"),
      "utf-8",
    );

    expect(message).toContain(
      'import { writeClipboardText } from "@/lib/clipboard";',
    );
    expect(message).toContain("await writeClipboardText(text)");
    expect(message).toContain(
      'onToast?: (message: string, variant?: "neutral" | "error") => void',
    );
    expect(message).toContain(
      't(copied ? "chat.copy_success" : "chat.copy_failed")',
    );
    expect(message).toContain('copied ? "neutral" : "error"');
    expect(message).not.toContain("absolute -left-12");
    expect(message).toContain("chat.copy_success");
    expect(message).toContain("chat.copy_failed");
    expect(message).toContain('message.kind === "strategy_confirmation"');
    expect(chat).toContain("onToast={showToast}");
    expect(chat).toContain("paddingBottom: 190 + dailyCap.height");
    expect(chat).toContain('className="h-28"');
    expect(toast).toContain("absolute inset-x-0 bottom-24");
    expect(toast).toContain("flex justify-center");
    // Success stays a polite status pill; failures escalate to an alert.
    expect(toast).toContain('role={isError ? "alert" : "status"}');
    expect(toast).toContain('aria-live={isError ? "assertive" : "polite"}');
    expect(toast).toContain("dark:bg-[#1f2225]");
    expect(chat).not.toContain("rounded-full bg-black dark:bg-white");
    expect(en).toContain('"copy_success": "Copied"');
    expect(es).toContain('"copy_failed": "No se pudo copiar"');
  });

  test("chat consumes result action chips after breakdown is requested", () => {
    const chat = readChatImplementationSource();

    // Result-card chip consumption is message-scoped and still live. The
    // composer-strip half of this mechanism went away with the strip itself.
    expect(chat).toContain("consumeResultActionOnMessages");
    expect(chat).toContain("consumedResultActionsFromApi");
    expect(chat).toContain("applyConsumedResultActions");
    expect(chat).toContain('action?.type === "show_breakdown"');
    expect(chat).toContain('latestAi?.kind === "strategy_result"');
    expect(chat).not.toContain("consumeInputAction");
    expect(chat).not.toContain("setInputActions");
  });

  test("chat resumes explicit conversation routes instead of creating a fresh one on reload", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const routing = readFileSync(
      join(root, "lib/chat-conversation-routing.ts"),
      "utf-8",
    );
    const initialSession = readFileSync(
      join(root, "components/chat/useInitialChatSession.ts"),
      "utf-8",
    );

    expect(routing).toContain("ACTIVE_CONVERSATION_QUERY_KEY");
    expect(`${chat}\n${initialSession}`).toContain("readActiveConversationRouteState");
    expect(chat).not.toContain("ACTIVE_CONVERSATION_STORAGE_KEY");
    expect(chat).not.toContain("readActiveConversationId()");
    expect(initialSession).toContain(
      "await navigateConversationTranscript(activeConversationId, userId, {",
    );
    expect(chat).toContain(
      "loadSavedConversationTranscript(targetConversationId)",
    );
    expect(chat).toContain(
      "const routeState = readActiveConversationRouteState();",
    );
    expect(chat).toContain("shouldStartConversationForVisibleEmptyChat({");
    expect(chat).toContain("visibleMessageCount: messages.length");
    expect(chat).toContain("hasStructuredAction: Boolean(action?.type)");
    expect(chat).toContain("await streamToConversation(targetConversationId);");
  });

  test("history menu reuses structured conversation hydration", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");

    expect(chat).toContain("hydrateMessagesFromApi");
    expect(chat).toContain("void loadConversation(item.id)");
    expect(chat).toContain("loadConversationForRun");
    expect(chat).toContain("getBacktestRun(item.id)");
    expect(api).toContain("export async function getBacktestRun");
    expect(chat).not.toContain(
      'kind: m.content.includes("result") ? "strategy_result" : "text"',
    );
  });

  test("spanish remains registered behind a feature flag", () => {
    const languages = readFileSync(
      join(root, "lib/language-features.ts"),
      "utf-8",
    );
    const i18n = readFileSync(join(root, "lib/i18n.ts"), "utf-8");

    expect(languages).toContain('code: "es-419"');
    expect(languages).toContain("NEXT_PUBLIC_ENABLE_SPANISH");
    expect(i18n).toContain("ENABLED_LANGUAGE_CODES");
  });

  test("chat sidebar opens a safe command palette instead of hydrating chat previews", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );

    expect(chat).toContain("ChatSidebar");
    expect(chat).toContain("ChatCommandPalette");
    expect(chat).toContain("searchOverlayOpen");
    expect(chat).not.toContain("ChatOmniSearch");
    expect(palette).toContain("searchGlobal");
    expect(palette).toContain("listHistory");
    expect(palette).toContain("onOpenConversation");
    expect(palette).not.toContain("getConversationMessages");
    expect(palette).not.toContain("hydrateMessagesFromApi");
    expect(palette).not.toContain("ChatMessage");
    expect(palette).not.toContain("streamChatMessage");
    expect(palette).not.toContain("handleAction");
  });

  test("chat command palette uses global search api and cursor pagination hooks", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const adapter = readFileSync(
      join(root, "lib/command-palette-items.ts"),
      "utf-8",
    );
    const dossier = readFileSync(
      join(
        root,
        "components/sidebar/command-palette/RunDossierView.tsx",
      ),
      "utf-8",
    );
    const api = ["lib/argus-api.ts", "lib/conversation-surface-api.ts"].map((file) => readFileSync(join(root, file), "utf-8")).join("\n");

    expect(palette).toContain("includeLedgerGroups: true");
    expect(palette).toContain("commandPaletteItemFromSearch");
    expect(palette).toContain("commandPaletteGroupsByLedgerState");
    expect(palette).not.toContain(
      't("command_palette.ledger.title", "Idea Ledger")',
    );
    expect(palette).not.toContain("command_palette.ledger.all_saved_ideas");
    expect(palette).toContain("decisionStateFilter === group.decision_state");
    expect(palette).toContain("clearSearchAndLedger();");
    expect(palette).toContain("group.count === 0");
    expect(palette).toContain(
      "commandPaletteSelectedRenderedPreview(\n    previewItem,\n    groupedItems,",
    );
    expect(palette).toContain("setPreviewItem(null)");
    expect(adapter).toContain("command_palette.open_conversation");
    expect(adapter).toContain('type: "chat" | "conversation"');
    expect(adapter).toContain("item.dossier");
    expect(adapter).toContain('activation: "open_conversation"');
    expect(adapter).toContain("export function commandPaletteStatusLabelKey");
    expect(adapter).toContain("export function commandPaletteStatusFallback");
    expect(adapter).not.toContain("commandPalettePreviewFields");
    expect(palette).toContain("<RunDossierView");
    expect(dossier).toContain("formatRunDossierSetup");
    expect(dossier).toContain("formatRunDossierMetrics");
    expect(palette).toContain("const activateItem = useCallback");
    expect(palette).not.toContain('item.activation === "select_preview"');
    expect(palette).toContain("onMouseEnter={() => setPreviewItem(item)}");
    expect(palette).toContain("onFocus={() => setPreviewItem(item)}");
    expect(palette).toContain("commandPaletteStatusLabelKey(item)");
    expect(palette).toContain("commandPaletteStatusFallback(item)");
    expect(palette).toContain(
      't("command_palette.clear_search", "Clear search")',
    );
    expect(palette).toContain('"Select a result to preview its details."');
    expect(palette).toContain("const openSourceConversation = useCallback");
    expect(palette).toContain("MessageSquare");
    expect(palette).toContain("md:flex-row");
    expect(palette).not.toContain("hidden w-[44%]");
    expect(palette).toContain('"command_palette.search_placeholder"');
    expect(palette).toContain('"Search Argus..."');
    expect(palette).toContain("maxLength={512}");
    expect(palette).toContain("loadMoreSearch");
    expect(api).toContain("cursor?: string");
    expect(api).toContain("decisionState?: DecisionState | null");
    expect(api).toContain("includeLedgerGroups?: boolean");
    expect(api).toContain(
      'searchParams.append("decision_state", decisionState)',
    );
    expect(api).toContain(
      'searchParams.append("include_ledger_groups", "true")',
    );
    expect(api).toContain("export async function searchGlobal");
  });

  test("transcript matches load the complete thread before focusing the message", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");

    expect(api).toContain("anchorMessageId?: string");
    expect(api).toContain(
      'searchParams.append("anchor_message_id", options.anchorMessageId)',
    );
    const turnAnchor = readFileSync(
      join(root, "components/chat/useTranscriptTurnAnchor.ts"),
      "utf-8",
    );
    expect(chat).toContain(
      "loadSavedConversationTranscript(targetConversationId)",
    );
    expect(chat).toContain("data-message-id={msg.id}");
    expect(chat).toContain("useTranscriptTurnAnchor({");
    expect(turnAnchor).toContain('element.scrollIntoView({ block: "center" })');
    expect(turnAnchor).toContain("element.focus({ preventScroll: true })");
    expect(palette).toContain(
      "commandPaletteOpenMessageId(item, openAtLeftOff)",
    );
    const anchoredNavigation = chat.slice(
      chat.indexOf("if (options.messageId)"),
      chat.indexOf("let renderedStaleSnapshot"),
    );
    expect(anchoredNavigation).not.toContain(
      "{ anchorMessageId: requestedMessageId }",
    );
    expect(anchoredNavigation).toContain(
      "loadSavedConversationTranscript(targetConversationId)",
    );
    expect(anchoredNavigation).toContain(
      "isCurrentAnchoredConversationRequest({",
    );
    expect(anchoredNavigation.match(/isCurrentRequest\(\)/g)).toHaveLength(2);
  });

  test("command palette highlights normalized search tokens without rewriting display text", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );

    expect(palette).toContain("<SearchHighlight");
    expect(palette).not.toContain("function highlightText");
  });

  test("result cards expose typed decision capture without prose parsing", () => {
    const card = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    const decisionsApi = readFileSync(join(root, "lib/decisions-api.ts"), "utf-8");
    const affordance = readFileSync(
      join(root, "components/chat/DecisionAffordance.tsx"),
      "utf-8",
    );

    expect(api).toContain("export async function createEvidenceDecision");
    expect(api).toContain("decision_state: DecisionState");
    // One affordance owns capture; the route follows the typed attachment.
    expect(decisionsApi).toContain("export async function saveDecision");
    expect(decisionsApi).toContain("export async function createMessageDecision");
    expect(decisionsApi).toContain('attachment.kind === "evidence_artifact"');
    expect(affordance).toContain("await saveDecision(attachment, {");
    expect(card).toContain('kind: "evidence_artifact", artifactId: result.evidenceArtifactId');
    expect(card).toContain("setSavedDecisionState(decision.decision_state)");
    expect(card).not.toContain("createEvidenceDecision");
    expect(affordance).toContain("decisionChipClassName");
    expect(affordance).toContain("border-[#5ba897]/18 bg-transparent");
    expect(affordance).toContain("draft.selectedState === state");
    expect(affordance).toContain("DECISION_NOTE_MAX_LENGTH");
    expect(affordance).toContain("nextDecisionNoteValue(");
    expect(affordance).not.toContain("maxLength={DECISION_NOTE_MAX_LENGTH}");
  });

  test("omnisearch dossier verbs reuse ordinary send and owner-checked decision paths", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const contract = readFileSync(
      join(root, "lib/run-dossier-contract.ts"),
      "utf-8",
    );

    expect(contract).toContain('type: "retest_run"');
    expect(contract).toContain(
      'window_policy: "preserve_start_ending_latest_available"',
    );
    expect(contract).toContain('contract_version: "argus_retest_run/v2"');
    expect(contract).not.toContain('contract_version: "argus_retest_run/v1"');
    // The typed envelope carries no client-authoritative setup.
    expect(contract).not.toContain("canonical_setup");
    expect(contract).not.toContain("send_text");
    expect(contract).toContain('type: "decision"');
    expect(palette).toContain("createEvidenceDecision");
    expect(palette).toContain("onRetest");
    expect(palette).toContain("canonicalMutationIdRef");
    expect(palette).toContain("searchRequestIdRef");
    expect(palette).toContain("includeLedgerGroups: true");
    const omnisearchActions = readFileSync(
      join(root, "components/chat/omnisearch-actions.ts"),
      "utf-8",
    );
    expect(chat).toContain("omnisearchActionHandlers(() => ({");
    expect(chat).toContain("onRetest={omnisearch.retest}");
    expect(omnisearchActions).toContain(
      "await deps.loadConversation(conversationId, undefined, true)",
    );
    expect(omnisearchActions).toContain(
      "if (!deps.isSourceConversationReady(conversationId)) return",
    );
    expect(omnisearchActions).toContain("void deps.send(action.label, action)");
    expect(palette).not.toContain("run_backtest");
  });

  test("omnisearch disables Retest while another turn owns the stream", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const dossier = readFileSync(
      join(
        root,
        "components/sidebar/command-palette/RunDossierView.tsx",
      ),
      "utf-8",
    );

    expect(chat).toContain("turnInFlight={turnInFlight}");
    expect(palette).toContain("turnInFlight?: boolean");
    expect(palette).toContain("retestDisabled={turnInFlight}");
    expect(dossier).toContain(
      "retestButtonDisabled = retestDisabled || retestUnavailable",
    );
    expect(dossier).toContain("disabled={retestButtonDisabled}");
    expect(dossier).toContain("disabled:cursor-not-allowed");
    expect(dossier).toContain("disabled:opacity-50");
  });

  test("omnisearch preserves the active turn when its conversation is selected", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const openSourceConversation = palette.slice(
      palette.indexOf("const openSourceConversation = useCallback"),
      palette.indexOf("const activateItem = useCallback"),
    );

    expect(chat).toContain("turnInFlight={turnInFlight}");
    expect(palette).toContain("turnInFlight?: boolean");
    expect(openSourceConversation).toContain(
      "commandPaletteConversationNavigationDisabled",
    );
    expect(openSourceConversation).toContain("activeConversationId");
    expect(openSourceConversation).toContain("return;");
    expect(palette).toContain("aria-disabled={isNavigationDisabled}");
    expect(palette).toContain("!selectedPreview.conversationId ||");
    expect(palette).toContain("selectedNavigationDisabled");
  });

  test("debounced omnisearch synchronizes rows and ledger counts under one request owner", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const debouncedSearch = palette.slice(
      palette.indexOf("debounceRef.current = setTimeout"),
      palette.indexOf(
        "return () =>",
        palette.indexOf("debounceRef.current = setTimeout"),
      ),
    );

    expect(debouncedSearch).toContain("includeLedgerGroups: true");
    expect(debouncedSearch).toContain(
      ".then(({ items, next_cursor, ledger_groups }) => {",
    );
    expect(debouncedSearch).toContain("setSearchResults(items)");
    expect(debouncedSearch).toContain("setSearchNextCursor(next_cursor)");
    expect(debouncedSearch).toContain("setLedgerGroups(ledger_groups ?? [])");
    expect(
      debouncedSearch.indexOf("commandPaletteRequestIsCurrent"),
    ).toBeLessThan(
      debouncedSearch.indexOf("setLedgerGroups(ledger_groups ?? [])"),
    );
  });

  test("deferred search keeps its query signature through transition and clear", async () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const searchEffect = palette.slice(
      palette.indexOf("const trimmed = query.trim()"),
      palette.indexOf("const isFiltering = query.trim().length > 0"),
    );
    const timerStart = searchEffect.indexOf(
      "debounceRef.current = setTimeout",
    );
    const timerBody = searchEffect.slice(timerStart);
    const captureStart = searchEffect.indexOf(
      "const capturedSignature = JSON.stringify",
    );

    expect(captureStart).toBeGreaterThanOrEqual(0);
    expect(captureStart).toBeLessThan(timerStart);
    expect(timerBody).not.toContain(
      "const capturedSignature = JSON.stringify",
    );

    const querySignature = JSON.stringify(["gold", false, null]);
    for (const nextSignature of [
      JSON.stringify(["silver", false, null]),
      JSON.stringify(["", false, null]),
    ]) {
      let currentSignature = querySignature;
      let currentRequestId = 0;
      const capturedSignature = currentSignature;
      const deferredOwner = new Promise<boolean>((resolve) => {
        setTimeout(() => {
          const capturedRequestId = ++currentRequestId;
          resolve(
            commandPaletteRequestIsCurrent({
              capturedSignature,
              capturedRequestId,
              currentSignature,
              currentRequestId,
            }),
          );
        }, 0);
      });

      currentSignature = nextSignature;
      currentRequestId += 1;

      expect(await deferredOwner).toBe(false);
    }
  });

  test("search retry cannot let a history failure replace successful results", async () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const historyRequestStart = palette.indexOf(
      "const requestId = ++historyRequestIdRef.current",
    );
    const historyEffect = palette.slice(
      palette.lastIndexOf("useEffect(() => {", historyRequestStart),
      palette.indexOf("const clearSearchAndLedger"),
    );

    expect(historyEffect).toContain("!isRecentsMode");
    expect(historyEffect).toContain(
      "searchSignatureRef.current !== RECENTS_SEARCH_SIGNATURE",
    );
    expect(historyEffect).toContain(
      "const capturedSignature = RECENTS_SEARCH_SIGNATURE",
    );

    const recentsSignature = JSON.stringify(["", false, null]);
    let currentSignature = JSON.stringify(["gold", false, null]);
    let readError: "search" | "history" | null = "search";
    let failHistory: (() => void) | null = null;
    const retryHistory = (): Promise<void> | null => {
      if (currentSignature !== recentsSignature) return null;
      return new Promise<void>((resolve) => {
        failHistory = () => {
          readError = "history";
          resolve();
        };
      });
    };

    const searchScopedHistoryRetry = retryHistory();
    readError = null;
    failHistory?.();
    if (searchScopedHistoryRetry) await searchScopedHistoryRetry;

    expect(searchScopedHistoryRetry).toBeNull();
    expect(readError).toBeNull();

    currentSignature = recentsSignature;
    const recentsHistoryRetry = retryHistory();
    failHistory?.();
    if (recentsHistoryRetry) await recentsHistoryRetry;

    expect(recentsHistoryRetry).not.toBeNull();
    expect(readError).toBe("history");
  });

  test("returning to Recents retries history after an ignored search-time failure", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const historyRequestStart = palette.indexOf(
      "const requestId = ++historyRequestIdRef.current",
    );
    const historyEffect = palette.slice(
      palette.lastIndexOf("useEffect(() => {", historyRequestStart),
      palette.indexOf("const refreshRecentsLedgerGroups"),
    );
    const clearSearchAndLedger = palette.slice(
      palette.indexOf("const clearSearchAndLedger"),
      palette.indexOf("const loadLedgerBrowse"),
    );
    const searchInputChange = palette.slice(
      palette.indexOf("onChange={(event) => {"),
      palette.indexOf(
        "placeholder={",
        palette.indexOf("onChange={(event) => {"),
      ),
    );

    expect(palette).toContain("const isRecentsMode =");
    expect(historyEffect).toContain("!isRecentsMode");
    expect(historyEffect).toContain(
      "[chatAvailable, isGuest, isRecentsMode, retryNonce, searchSurface, surface]",
    );
    expect(historyRequestStart).toBeLessThan(
      palette.indexOf("const trimmed = query.trim()"),
    );
    expect(
      clearSearchAndLedger.indexOf(
        "historyRequestIdRef.current += 1",
      ),
    ).toBeGreaterThanOrEqual(0);
    expect(
      clearSearchAndLedger.indexOf(
        "historyRequestIdRef.current += 1",
      ),
    ).toBeLessThan(
      clearSearchAndLedger.indexOf(
        "searchSignatureRef.current = RECENTS_SEARCH_SIGNATURE",
      ),
    );
    expect(clearSearchAndLedger).toContain(
      "searchSignatureRef.current !== RECENTS_SEARCH_SIGNATURE",
    );
    expect(
      clearSearchAndLedger.indexOf(
        "searchSignatureRef.current = RECENTS_SEARCH_SIGNATURE",
      ),
    ).toBeLessThan(clearSearchAndLedger.indexOf('setQuery("")'));
    expect(
      searchInputChange.indexOf("historyRequestIdRef.current += 1"),
    ).toBeGreaterThanOrEqual(0);
    expect(searchInputChange).toContain(
      "const nextSignature = JSON.stringify",
    );
    expect(searchInputChange).toContain(
      "nextSignature !== searchSignatureRef.current",
    );
    expect(
      searchInputChange.indexOf("historyRequestIdRef.current += 1"),
    ).toBeLessThan(
      searchInputChange.indexOf(
        "searchSignatureRef.current = nextSignature",
      ),
    );
    expect(
      searchInputChange.indexOf(
        "searchSignatureRef.current = nextSignature",
      ),
    ).toBeLessThan(searchInputChange.indexOf("setQuery(nextQuery)"));

    const recentsSignature = JSON.stringify(["", false, null]);
    let currentSignature = recentsSignature;
    let currentRequestId = 0;
    const startHistoryRead = (isRecentsMode: boolean) => {
      if (!isRecentsMode || currentSignature !== recentsSignature) return null;
      return {
        id: ++currentRequestId,
        signature: recentsSignature,
      };
    };
    const requestIsCurrent = (request: {
      id: number;
      signature: string;
    }) =>
      commandPaletteRequestIsCurrent({
        capturedSignature: request.signature,
        capturedRequestId: request.id,
        currentSignature,
        currentRequestId,
      });
    const updateSignature = (nextSignature: string) => {
      if (nextSignature !== currentSignature) currentRequestId += 1;
      currentSignature = nextSignature;
    };

    const initialHistory = startHistoryRead(true);
    expect(initialHistory).not.toBeNull();

    updateSignature(JSON.stringify(["gold", false, null]));
    expect(requestIsCurrent(initialHistory!)).toBe(false);
    expect(startHistoryRead(false)).toBeNull();

    updateSignature(recentsSignature);
    expect(requestIsCurrent(initialHistory!)).toBe(false);
    const returnedHistory = startHistoryRead(true);
    expect(returnedHistory).not.toBeNull();
    expect(requestIsCurrent(initialHistory!)).toBe(false);
    expect(requestIsCurrent(returnedHistory!)).toBe(true);

    const whitespaceSignature = JSON.stringify([" ".trim(), false, null]);
    updateSignature(whitespaceSignature);
    expect(requestIsCurrent(returnedHistory!)).toBe(true);
    updateSignature(recentsSignature);
    expect(requestIsCurrent(returnedHistory!)).toBe(true);
  });

  test("ledger counts stay scoped to the active query through transitions and clear", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const recentRecall = readFileSync(
      join(root, "lib/command-palette-recent-recall.ts"),
      "utf-8",
    );
    const recentsHistoryAndDossierRead = palette.slice(
      palette.indexOf("const requestId = ++historyRequestIdRef.current"),
      palette.indexOf("const clearSearchAndLedger"),
    );
    const clearSearchAndLedger = palette.slice(
      palette.indexOf("const clearSearchAndLedger"),
      palette.indexOf("const loadLedgerBrowse"),
    );
    const loadLedgerBrowse = palette.slice(
      palette.indexOf("const loadLedgerBrowse"),
      palette.indexOf(
        "useEffect(() =>",
        palette.indexOf("const loadLedgerBrowse"),
      ),
    );
    const searchInputChange = palette.slice(
      palette.indexOf("onChange={(event) => {"),
      palette.indexOf(
        "placeholder={t(",
        palette.indexOf("onChange={(event) => {"),
      ),
    );

    expect(recentsHistoryAndDossierRead).toContain(
      "const capturedSignature = RECENTS_SEARCH_SIGNATURE",
    );
    expect(recentsHistoryAndDossierRead).toContain(
      "commandPaletteRequestIsCurrent",
    );
    expect(recentsHistoryAndDossierRead).toContain(
      "loadCommandPaletteRecentRecall",
    );
    expect(recentRecall).toContain("includeLedgerGroups: true");
    expect(clearSearchAndLedger).toContain("setLedgerGroups([])");
    expect(clearSearchAndLedger).not.toContain("searchGlobal(");
    expect(loadLedgerBrowse).toContain("setLedgerGroups([])");
    expect(searchInputChange).toContain(
      "ledgerBrowseRequestIdRef.current += 1",
    );
    expect(searchInputChange).toContain("setLedgerGroups([])");
    expect(searchInputChange).not.toContain("searchGlobal(");
  });

  test("decision refresh invalidates an older Recents dossier enrichment", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const canonicalRefresh = palette.slice(
      palette.indexOf("const refreshCanonicalSearch"),
      palette.indexOf("const saveDecision"),
    );

    expect(canonicalRefresh).toContain("historyRequestIdRef.current += 1");
    expect(
      canonicalRefresh.indexOf("historyRequestIdRef.current += 1"),
    ).toBeLessThan(
      canonicalRefresh.indexOf(
        "const requestId = ++searchRequestIdRef.current",
      ),
    );
  });

  test("omnisearch canon pins keyboard, error truth, debounce, and mobile controls", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const dossierIntegration = readFileSync(
      join(root, "lib/command-palette-dossier-integration.ts"),
      "utf-8",
    );
    const initialHistoryFetch = palette.slice(
      palette.indexOf("const requestId = ++historyRequestIdRef.current"),
      palette.indexOf("const clearSearchAndLedger"),
    );
    const clearSearchAndLedger = palette.slice(
      palette.indexOf("const clearSearchAndLedger"),
      palette.indexOf("const loadLedgerBrowse"),
    );
    const loadLedgerBrowse = palette.slice(
      palette.indexOf("const loadLedgerBrowse"),
      palette.indexOf(
        "useEffect(() =>",
        palette.indexOf("const loadLedgerBrowse"),
      ),
    );
    const readErrorPanel = palette.slice(
      palette.indexOf(") : readError ? ("),
      palette.indexOf(") : displayItems.length"),
    );
    const loadMore = palette.slice(
      palette.indexOf("const loadMoreSearch"),
      palette.indexOf("const openSourceConversation"),
    );
    const refreshCanonicalSearch = palette.slice(
      palette.indexOf("const refreshCanonicalSearch"),
      palette.indexOf("const saveDecision"),
    );
    const saveDecision = palette.slice(
      palette.indexOf("const saveDecision"),
      palette.indexOf("const updateLocalTitle"),
    );

    expect(palette).toContain("const SEARCH_DEBOUNCE_MS = 200");
    expect(palette).toContain("searchQueryIsIndexable");
    expect(palette).toContain("command_palette.keep_typing");
    expect(palette).toContain("const ledgerBrowseRequestIdRef = useRef(0)");
    expect(initialHistoryFetch).toContain(
      "const capturedSignature = RECENTS_SEARCH_SIGNATURE",
    );
    expect(initialHistoryFetch).toContain("commandPaletteRequestIsCurrent");
    expect(initialHistoryFetch).toContain(
      "loadCommandPaletteRecentRecall",
    );
    expect(initialHistoryFetch).toContain("setLedgerGroups(");
    expect(loadLedgerBrowse).toContain("++ledgerBrowseRequestIdRef.current");
    expect(loadLedgerBrowse).not.toContain("++searchRequestIdRef.current");
    expect(clearSearchAndLedger).toContain(
      "ledgerBrowseRequestIdRef.current += 1",
    );
    expect(readErrorPanel).toContain('readError === "ledger" && isLedgerMode');
    expect(readErrorPanel).toContain(
      "void loadLedgerBrowse(decisionStateFilter)",
    );
    // The keyboard policy moved to its own hook; the palette hands it the rows.
    const paletteKeys = readFileSync(
      join(root, "components/sidebar/command-palette/useCommandPaletteKeys.ts"),
      "utf-8",
    );
    expect(palette).toContain("useCommandPaletteKeys({");
    expect(palette).toContain(
      "commandPaletteItemsInRenderedOrder(groupedItems)",
    );
    expect(paletteKeys).toContain("commandPaletteKeyboardAction");
    expect(paletteKeys).toContain("itemCount: keyboardItems.length");
    expect(paletteKeys).toContain("const item = keyboardItems[action.index]");
    expect(palette).toContain("const rowIndex = groupRowStart + itemIndex");
    expect(paletteKeys).toContain("targetIsSearchInput: event.target === inputRef.current");
    expect(paletteKeys).toContain("isEditableKeyboardTarget");
    expect(loadMore).toContain(
      "const capturedSignature = searchSignatureRef.current",
    );
    expect(loadMore).toContain(
      "const requestId = ++searchRequestIdRef.current",
    );
    expect(loadMore).toContain("commandPaletteRequestIsCurrent");
    expect(loadMore).toContain("isSavingDecision");
    expect(loadMore).not.toContain("setReadError");
    expect(loadMore).toContain("setIsLoadingMoreSearch(false)");
    expect(refreshCanonicalSearch).toContain("setIsLoadingMoreSearch(false)");
    expect(refreshCanonicalSearch).toContain(
      "ledgerBrowseRequestIdRef.current += 1",
    );
    expect(
      refreshCanonicalSearch.indexOf("ledgerBrowseRequestIdRef.current += 1"),
    ).toBeLessThan(
      refreshCanonicalSearch.indexOf("++searchRequestIdRef.current"),
    );
    expect(
      refreshCanonicalSearch.indexOf("setIsLoadingMoreSearch(false)"),
    ).toBeLessThan(
      refreshCanonicalSearch.indexOf("++searchRequestIdRef.current"),
    );
    expect(saveDecision.indexOf("await createEvidenceDecision")).toBeLessThan(
      saveDecision.indexOf("onMutated?.()"),
    );
    expect(saveDecision.indexOf("onMutated?.()")).toBeLessThan(
      saveDecision.indexOf("refreshCanonicalSearch:"),
    );
    expect(saveDecision).toContain("refreshLoadedHistory:");
    expect(dossierIntegration).toMatch(
      /Promise\.all\(\[\s*refreshCanonicalSearch\(\),\s*refreshLoadedHistory\(\),\s*\]\)/,
    );
    expect(saveDecision).not.toContain("setDecisionDraft");
    expect(
      saveDecision.slice(
        saveDecision.indexOf("refreshCanonicalSearch:"),
      ),
    ).not.toContain("setDecisionSaveFailed(true)");
    expect(refreshCanonicalSearch).toContain(': currentQuery');
    expect(refreshCanonicalSearch).toContain('? "search"');
    expect(refreshCanonicalSearch).toContain(': "history"');
    expect(saveDecision).not.toContain("capturedSignature");
    expect(saveDecision).not.toContain("const currentSignature");
    expect(refreshCanonicalSearch).toContain(
      "JSON.parse(capturedSignature)",
    );
    expect(refreshCanonicalSearch).toContain("q: currentQuery");
    expect(refreshCanonicalSearch).toContain(
      "commandPaletteCanonicalRecallLimit(",
    );
    expect(refreshCanonicalSearch).toContain("setRecentItems((current)");
    expect(refreshCanonicalSearch).toContain("retainRecalledRecentItems(");
    expect(refreshCanonicalSearch).toContain("currentQuery,");
    expect(refreshCanonicalSearch).toContain("currentLedgerMode,");
    expect(palette).toContain(
      "disabled={isLoadingMoreSearch || isSavingDecision}",
    );
    expect(palette).toContain("command_palette.read_error");
    expect(palette).toContain("command_palette.try_searching");
    // The mobile shell spec replaced pointer sniffing with the width bands:
    // touch on a wide screen keeps the desktop layout, and a narrow window on a
    // mouse machine gets the mobile one.
    expect(palette).not.toContain('window.matchMedia("(pointer: coarse)")');
    expect(palette).toContain("useResponsiveLayout()");
    expect(palette).toContain("effectivePaletteLayout(layoutMode, isBelowTablet)");
    expect(effectivePaletteLayout("expanded", true)).toBe("collapsed");
    expect(palette).toContain("text-[16px]");
    expect(palette).toContain("min-h-11");
  });

  test("chat command palette keeps safe hover management actions without chat hydration", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const rowActions = readFileSync(
      join(root, "components/sidebar/command-palette/rowActionItems.ts"),
      "utf-8",
    );
    const rowActionsView = readFileSync(
      join(root, "components/sidebar/command-palette/CommandPaletteRowActions.tsx"),
      "utf-8",
    );

    expect(chat).toContain("onMutated={refreshHistory}");
    expect(rowActions).toContain("Edit2");
    expect(rowActions).toContain("Archive");
    expect(rowActions).toContain("Trash2");
    expect(palette).toContain("editingId");
    expect(palette).toContain("editingTitle");
    expect(palette).toContain("handleRenameSave");
    expect(palette).toContain("handleArchive");
    expect(palette).toContain("handleDelete");
    expect(palette).toContain("patchConversation");
    expect(palette).toContain("apiDeleteConversation");
    expect(rowActionsView).toContain(
      'import { Tooltip } from "@/components/ui/Tooltip"',
    );
    // The eye reads the short verb, the same one Recents shows. The screen
    // reader hears the object too, because an icon-only control has no context.
    expect(rowActionsView).toContain("content={action.label}");
    expect(rowActionsView).toContain("aria-label={action.accessibleName}");
    for (const [visible, announced] of [
      ['t("common.rename", "Rename")', "command_palette.rename_conversation"],
      ['t("common.archive", "Archive")', "command_palette.archive_conversation"],
      ['t("common.delete", "Delete")', "command_palette.delete_conversation"],
    ]) {
      expect(rowActions).toContain(visible);
      expect(rowActions).toContain(announced);
    }
    expect(palette).not.toContain("getConversationMessages");
    expect(palette).not.toContain("hydrateMessagesFromApi");
    expect(palette).not.toContain("ChatMessage");
    expect(palette).not.toContain("streamChatMessage");
    expect(palette).not.toContain("handleAction");
  });

  test("successful search-result deletion refreshes backend-owned aggregates", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const confirmDeleteStart = palette.indexOf("const handleConfirmDelete");
    const confirmDelete = palette.slice(
      confirmDeleteStart,
      palette.indexOf("useEffect(() =>", confirmDeleteStart),
    );
    const refreshAfterMutation = palette.slice(
      palette.indexOf("const refreshAfterCanonicalMutation"),
      palette.indexOf("const saveDecision"),
    );

    expect(confirmDelete).toContain(
      "const mutationId = ++canonicalMutationIdRef.current",
    );
    expect(confirmDelete.indexOf("await apiDeleteConversation")).toBeLessThan(
      confirmDelete.indexOf("onMutated?.()"),
    );
    expect(confirmDelete.indexOf("onMutated?.()")).toBeLessThan(
      confirmDelete.indexOf(
        "await refreshAfterCanonicalMutation(mutationId)",
      ),
    );
    expect(refreshAfterMutation).toContain(
      "await refreshCanonicalSearch(currentSignature, mutationId)",
    );
    expect(refreshAfterMutation).toContain("setReadError(");
  });

  test("failed More keeps loaded results visible and isolates its retry state", () => {
    const palette = readFileSync(
      join(root, "components/sidebar/ChatCommandPalette.tsx"),
      "utf-8",
    );
    const loadMoreControl = readFileSync(
      join(root, "components/sidebar/CommandPaletteLoadMoreControl.tsx"),
      "utf-8",
    );
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(
        join(root, "public/locales/es-419/common.json"),
        "utf-8",
      ),
    );
    const loadMore = palette.slice(
      palette.indexOf("const loadMoreSearch"),
      palette.indexOf("const openSourceConversation"),
    );
    const loadMoreCatch = loadMore.slice(
      loadMore.indexOf("} catch {"),
      loadMore.indexOf("} finally {"),
    );
    const resultsRenderStart = palette.indexOf("displayItems.length === 0");
    const resultsRender = palette.slice(
      resultsRenderStart,
      palette.indexOf('layoutMode === "expanded"', resultsRenderStart),
    );

    expect(loadMore).toContain("setLoadMoreFailed(false)");
    expect(loadMoreCatch).toContain("setLoadMoreFailed(true)");
    expect(loadMoreCatch).not.toContain("setReadError");
    expect(loadMoreCatch).not.toContain("setSearchResults");
    expect(resultsRender).toContain("CommandPaletteLoadMoreControl");
    expect(resultsRender).toContain("failed={loadMoreFailed}");
    expect(resultsRender).toContain("onLoadMore={() => void loadMoreSearch()}");
    expect(loadMoreControl).toContain('"command_palette.load_more_error"');
    expect(loadMoreControl).toContain('"command_palette.retry_load_more"');
    expect(en.command_palette.load_more_error).toBe(
      "Argus couldn’t load more results. Your current results are still available.",
    );
    expect(es.command_palette.load_more_error).toBe(
      "Argus no pudo cargar más resultados. Tus resultados actuales siguen disponibles.",
    );
    expect(en.command_palette.retry_load_more).toBe("Try loading more");
    expect(es.command_palette.retry_load_more).toBe(
      "Intentar cargar más",
    );

    const loadedResults = ["first-page-a", "first-page-b"];
    const cursor = "next-page";
    const readError: "search" | null = null;
    let loadMoreFailed = false;
    loadMoreFailed = true;

    expect(loadedResults).toEqual(["first-page-a", "first-page-b"]);
    expect(cursor).toBe("next-page");
    expect(readError).toBeNull();
    expect(loadMoreFailed).toBeTrue();
  });

  test("chat schedules bounded history refreshes for async artifact naming", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const viewHelpers = readFileSync(
      join(root, "lib/chat-conversation-view-helpers.ts"),
      "utf-8",
    );

    expect(chat).toContain("function schedulePostTurnHistoryRefresh");
    expect(chat).toContain("listConversations");
    expect(chat).toContain("title_source");
    expect(chat).toContain("window.setTimeout");
    expect(viewHelpers).toContain("1500");
    expect(viewHelpers).toContain("5000");
    expect(viewHelpers).toContain("9000");
    expect(viewHelpers).toContain("13000");
    expect(chat).toContain(
      "session.identity.conversationId,",
    );
    const finishTransportStart = chat.indexOf("function finishRequestTransport");
    const finishTransportEnd = chat.indexOf("useEffect(", finishTransportStart);
    const finishTransport = chat.slice(finishTransportStart, finishTransportEnd);
    expect(finishTransport).toContain(
      "requestSessions.finishTransport(session)",
    );
    expect(finishTransport).toContain("requestSessions.isAccountCurrent(session)");
    expect(finishTransport).not.toContain("request_settled");
    expect(chat).toContain("Title/sidebar refresh is fail-open");
    expect(chat).toContain(
      "void refreshAndCheckTitle().catch(() => undefined);",
    );
  });

  test("feedback dialog provides rich feedback surfaces", () => {
    const dialog = readFileSync(
      join(root, "components/feedback/FeedbackDialog.tsx"),
      "utf-8",
    );

    expect(dialog).toContain("FeedbackType");
    expect(dialog).toContain("bugTitle");
    expect(dialog).toContain("steps");
    expect(dialog).toContain("expected");
    expect(dialog).toContain("actual");
    expect(dialog).toContain("includeConversationContext");
    expect(dialog).toContain("ChevronDown");
    expect(dialog).not.toContain("attachmentCount");
    expect(dialog).not.toContain("Paperclip");
    expect(dialog).not.toContain("type=\"file\"");
    expect(dialog).not.toContain("attachments_with_count");
    expect(dialog).not.toContain("Maximum 5 files");
    expect(dialog).toContain("General Feedback");
    expect(dialog).toContain("Report a Bug");
    expect(dialog).toContain("Request a Feature");
    expect(dialog).toContain("Include approved context from this conversation");
    expect(dialog).toContain("hasConversationContext");
    expect(dialog).toContain('event.key === "Escape"');
    expect(dialog).toContain('document.addEventListener("keydown"');
    expect(dialog).toContain('type === "bug"');
    expect(dialog).toContain('const title = "Provide feedback";');
    expect(dialog).toContain('"File a bug report."');
    expect(dialog).toContain('"Share feedback about your Argus experience."');
    expect(dialog).toContain('"What worked well in this response?"');
    expect(dialog).toContain('"What should be improved in this response?"');
    expect(dialog).toContain(
      "Approved conversation identifiers will be included. The transcript is not attached.",
    );
    expect(dialog).toContain(
      "No conversation transcript or contact information is attached.",
    );
    expect(dialog).toContain("Learn more");
    expect(dialog).not.toContain("Provide positive feedback");
    expect(dialog).not.toContain("Provide negative feedback");
    expect(dialog).not.toContain(
      "File a bug report, request a feature, or send general feedback.",
    );
    expect(dialog).not.toContain(
      "Tell us what made this response land or miss.",
    );
    expect(dialog).not.toContain("ThumbsUp");
    expect(dialog).not.toContain("ThumbsDown");

    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );
    for (const locale of [en, es]) {
      expect(locale.feedback).not.toHaveProperty("attachments");
      expect(locale.feedback).not.toHaveProperty("attachments_with_count");
      expect(locale.feedback).not.toHaveProperty("attach_files");
      expect(locale.feedback).not.toHaveProperty("attach_files_feature");
      expect(locale.feedback).not.toHaveProperty("max_files");
    }
  });

  test("chat feedback rating is posted directly while dialog remains available for deliberate feedback", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const en = JSON.parse(
      readFileSync(
        join(root, "public/locales/en/common.json"),
        "utf-8",
      ),
    );
    const es = JSON.parse(
      readFileSync(
        join(root, "public/locales/es-419/common.json"),
        "utf-8",
      ),
    );

    expect(chat).toContain("const handleMessageFeedback = useCallback");
    expect(chat).toContain(
      "void handleMessageFeedback(type, context, rating);",
    );
    expect(chat).toContain('type: "general"');
    expect(chat).toContain(
      "feedbackContextForSubmission(context, {",
    );
    expect(chat).toContain("includeConversationContext: true");
    expect(chat).toContain("tags: []");
    expect(chat).not.toContain("attachmentCount");
    expect(chat).toContain('t("feedback.rating_message_fallback", { rating })');
    expect(chat).toContain("openFeedbackDialogState(type, context, rating, conversationId)");
    expect(
      en.feedback.rating_message_fallback,
    ).toContain("{{rating}}");
    expect(
      es.feedback.rating_message_fallback,
    ).toContain("{{rating}}");
  });

  test("chat message feedback controls fill only the selected thumb glyph", () => {
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const feedbackContext = readFileSync(
      join(root, "lib/chat-message-feedback-context.ts"),
      "utf-8",
    );

    expect(message).toContain("text-[#191c1f] dark:text-white");
    expect(message).toContain("selectedFeedbackClass");
    expect(message).toContain("selectedFeedbackIconClass");
    expect(message).toContain(
      'rating === "positive" ? selectedFeedbackIconClass : ""',
    );
    expect(message).toContain(
      'rating === "negative" ? selectedFeedbackIconClass : ""',
    );
    expect(message).not.toContain('rating === null || rating === "positive"');
    expect(message).not.toContain('rating === null || rating === "negative"');
    expect(message).not.toContain(
      "bg-[#5a677d]/12 text-[#5a677d] dark:bg-[#c9c9cd]/12 dark:text-[#c9c9cd]",
    );
    expect(message).not.toContain("scale-110");
    expect(message).not.toContain(
      "bg-black text-white dark:bg-white dark:text-black",
    );
    expect(message).not.toContain("bg-[#5ba897]/15 text-[#5ba897]");
    expect(message).not.toContain("bg-[#d66d75]/15 text-[#d66d75]");
    expect(message).toContain("MessageSquareWarning");
    expect(message).toContain("chat.report_issue");
    expect(message).toContain('onFeedback?.("rating"');
    expect(message).not.toContain("postFeedback");
    expect(message).toContain("conversationId?: string | null");
    expect(message).toContain(
      "feedbackContextForMessage(message, conversationId, extra)",
    );
    expect(feedbackContext).toContain("conversation_id: conversationId");
    expect(chat).toContain("conversationId={conversationId}");
  });

  test("profile menu is isolated from sidebar hover expansion", () => {
    const sidebar = readFileSync(
      join(root, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );
    const profileMenu = readFileSync(
      join(root, "components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );

    expect(profileMenu).toContain('import { createPortal } from "react-dom"');
    expect(profileMenu).toContain("data-profile-menu-surface");
    expect(profileMenu).toContain("handleSubmenuToggle");
    expect(profileMenu).toContain("createPortal(menu, document.body)");
    expect(sidebar).toContain("isPointerInsideSidebarRef");
    expect(sidebar).toContain("if (isProfileMenuOpen) return");
  });

  test("profile modal uses gated language shortcuts and the in-app deletion command", () => {
    const profileMenu = readFileSync(
      join(root, "components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    const languageFeatures = readFileSync(
      join(root, "lib/language-features.ts"),
      "utf-8",
    );
    const deleteRequestDialog = readFileSync(
      join(root, "components/sidebar/ProfileDeleteRequestDialog.tsx"),
      "utf-8",
    );
    const detailsDialog = readFileSync(
      join(root, "components/sidebar/ProfileDetailsDialog.tsx"),
      "utf-8",
    );
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    const en = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );
    const es = readFileSync(
      join(root, "public/locales/es-419/common.json"),
      "utf-8",
    );

    expect(languageFeatures).toContain("languageDisplayAbbreviation");
    expect(languageFeatures).toContain("localeForLanguage");
    // The dialog's markup lives in ProfileDetailsDialog; the menu keeps the
    // state and the requests behind it.
    expect(detailsDialog).toContain("ENABLED_LANGUAGES");
    expect(detailsDialog).toContain("languageDisplayAbbreviation");
    expect(profileMenu).toContain("localeForLanguage");
    // Lane 6: the delete button runs the deletion command; with the command
    // off (404) it falls back to the support ticket. Success or in_progress
    // signs out on the result; Done leaves. See account-deletion-api.test.ts.
    expect(profileMenu).toContain("requestAccountDeletion(currentLanguage)");
    expect(profileMenu).toContain("onLogout();");
    expect(deleteRequestDialog).toContain(
      "settings.profile.request_deletion.in_progress",
    );
    expect(detailsDialog).toContain("argus-profile-language-trigger");
    expect(detailsDialog).toContain("absolute right-0 top-full");
    // Both dialogs live in their own components, because a body-portaled
    // aria-modal surface has to register its own back, Escape, and focus.
    expect(deleteRequestDialog).toContain(
      "settings.profile.request_deletion.title",
    );
    expect(detailsDialog).toContain("useModalSurface");
    expect(profileMenu).toContain("settings.profile.language_save_error");
    expect(detailsDialog).not.toContain(
      "overflow-hidden rounded-[10px] border border-black/5 bg-black/[0.015]",
    );
    expect(profileMenu).not.toContain('profile?.language ?? "en"');
    expect(api).toContain('"account_deletion_request"');
    const deletionApi = readFileSync(
      join(root, "lib/account-deletion-api.ts"),
      "utf-8",
    );
    expect(deletionApi).toContain('"/account/delete"');
    expect(deletionApi).toContain("JSON.stringify({ confirm: true })");
    expect(deletionApi).toContain('type: "account_deletion_request"');
    expect(deletionApi).toContain('code === "account_deletion_incomplete"');
    expect(deleteRequestDialog).toContain(
      "settings.profile.request_deletion.requested",
    );
    expect(deleteRequestDialog).toContain(
      "settings.profile.request_deletion.confirm",
    );
    expect(deleteRequestDialog).toContain(
      "settings.profile.request_deletion.unavailable",
    );
    expect(en).toContain('"title": "Delete your account?"');
    expect(en).toContain(
      "Permanently delete your Cuadrao account and your data.",
    );
    expect(en).toContain("Your account and your data will be deleted, and this");
    expect(en).toContain("Your account is deleted. You're signed out.");
    expect(en).toContain("Your account is being deleted. You're signed out now");
    expect(en).toContain('show as \\"Former member.\\"');
    expect(en).not.toContain("Support will follow up by email.");
    expect(es).toContain('"title": "¿Eliminar tu cuenta?"');
    expect(es).toContain(
      "Elimina para siempre tu cuenta de Cuadrao y tus datos.",
    );
    expect(es).toContain("Tu cuenta y tus datos se eliminarán, y no");
    expect(es).toContain("Tu cuenta está eliminada. Ya cerraste sesión.");
    expect(es).toContain("Estamos eliminando tu cuenta.");
  });

  test("profile menu groups data controls preferences and legal links", () => {
    const profileMenu = readFileSync(
      join(root, "components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    const en = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );
    const es = readFileSync(
      join(root, "public/locales/es-419/common.json"),
      "utf-8",
    );
    const enCatalog = JSON.parse(en);
    const esCatalog = JSON.parse(es);

    const dataStart = profileMenu.indexOf('{activeSubmenu === "data"');
    const preferencesStart = profileMenu.indexOf(
      '{activeSubmenu === "settings"',
    );
    const legalStart = profileMenu.indexOf('{activeSubmenu === "help"');
    expect(dataStart).toBeGreaterThan(-1);
    expect(preferencesStart).toBeGreaterThan(dataStart);
    expect(legalStart).toBeGreaterThan(preferencesStart);

    const dataBlock = profileMenu.slice(dataStart, preferencesStart);
    const preferencesBlock = profileMenu.slice(preferencesStart, legalStart);
    const legalBlock = profileMenu.slice(legalStart);

    expect(en).toContain('"title": "Data Controls"');
    expect(en).toContain('"title": "Preferences"');
    expect(en).toContain('"title": "Help & Legal"');
    expect(en).toContain('"usage": "Usage"');
    expect(es).toContain('"title": "Controles de datos"');
    expect(es).toContain('"title": "Preferencias"');
    expect(es).toContain('"title": "Ayuda y legal"');
    expect(es).toContain('"usage": "Uso"');

    expect(dataBlock).toContain("settings.data.security");
    expect(dataBlock).toContain("settings.data.usage");
    expect(dataBlock).not.toContain("cursor-not-allowed");
    expect(dataBlock).toContain("settings.profile.delete_account");
    expect(dataBlock).toContain("settings.profile.delete_account_note");
    expect(dataBlock).toContain("handleOpenDeleteRequest");
    expect(dataBlock).toContain("hover:bg-[#d66d75]/10");
    expect(preferencesBlock).toContain("settings.preferences.title");
    expect(preferencesBlock).toContain("settings.app.appearance");
    expect(preferencesBlock).toContain("settings.app.language");
    expect(preferencesBlock).toContain("settings.app.sidebar");
    expect(preferencesBlock).not.toContain("settings.app.security");
    expect(legalBlock).toContain("keyboard_shortcuts.menu_item");
    expect(legalBlock).toContain("settings.help.terms");
    expect(legalBlock).toContain("settings.help.privacy");
    expect(legalBlock).toContain('href="/terms"');
    expect(legalBlock).toContain('href="/privacy"');
    expect(legalBlock).not.toContain("settings.help.release_notes");
    expect(enCatalog.settings.help).not.toHaveProperty("release_notes");
    expect(esCatalog.settings.help).not.toHaveProperty("release_notes");
    expect(profileMenu).toContain('href="/terms"');
    expect(profileMenu).toContain('href="/privacy"');
  });

  test("alpha legal pages exist and disclose terms privacy and providers", () => {
    const termsPath = join(root, "app/terms/page.tsx");
    const privacyPath = join(root, "app/privacy/page.tsx");
    const legalPagePath = join(root, "components/legal/AlphaLegalPage.tsx");

    expect(existsSync(termsPath)).toBe(true);
    expect(existsSync(privacyPath)).toBe(true);
    expect(existsSync(legalPagePath)).toBe(true);

    const terms = readFileSync(termsPath, "utf-8");
    const privacy = readFileSync(privacyPath, "utf-8");
    const legalPage = readFileSync(legalPagePath, "utf-8");
    const en = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );
    const es = readFileSync(
      join(root, "public/locales/es-419/common.json"),
      "utf-8",
    );

    expect(terms).toContain('kind="terms"');
    expect(terms).toContain('from "@/lib/support-email"');
    expect(terms).not.toContain("TODO");
    expect(privacy).toContain('kind="privacy"');
    expect(privacy).toContain('from "@/lib/support-email"');
    expect(privacy).not.toContain("TODO");

    expect(legalPage).toContain('"use client"');
    expect(legalPage).toContain("useTranslation");
    expect(legalPage).toContain("legal.terms.title");
    expect(legalPage).toContain("legal.privacy.title");
    expect(legalPage).toContain("font-display");
    expect(legalPage).toContain("body_before_email");
    expect(legalPage).toContain("mailto:${supportEmail}");

    expect(en).toContain('"effective_date": "Effective date: August 7, 2026"');
    expect(en).toContain('"title": "No investment advice"');
    expect(en).toContain("not a broker");
    expect(en).toContain("Historical simulations are hypothetical");
    expect(en).toContain("OpenRouter");
    expect(en).toContain("Supabase");
    expect(en).toContain("Render");
    expect(en).toContain("Alpaca");
    expect(en).toContain("Kraken");
    expect(en).toContain("TradingView Lightweight Charts");
    expect(en).toContain("PostHog");
    expect(en).toContain("prompts may be sent");

    expect(es).toContain(
      '"effective_date": "Fecha de entrada en vigor: 7 de agosto de 2026"',
    );
    expect(es).toContain("No es asesoría de inversión");
    expect(es).toContain("Argus no es broker");
    expect(es).toContain("Las simulaciones históricas son hipotéticas");
    expect(es).toContain("OpenRouter");
    expect(es).toContain("Supabase");
    expect(es).toContain("Render");
    expect(es).toContain("Alpaca");
    expect(es).toContain("Kraken");
    expect(es).toContain("TradingView Lightweight Charts");
    expect(es).toContain("PostHog");
    expect(es).toContain("prompts puede enviarse");
  });

  test("profile menu delete all conversations is recoverable and outcome-aware", () => {
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const sidebar = readFileSync(
      join(root, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );
    const profileMenu = readFileSync(
      join(root, "components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    const en = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );
    const es = readFileSync(
      join(root, "public/locales/es-419/common.json"),
      "utf-8",
    );

    expect(api).toContain("export async function deleteAllConversations");
    expect(api).toContain("deleted_count: number");
    expect(profileMenu).toContain("onDeleteAllConversations?: () => void");
    expect(profileMenu).toContain("onDeleteAllConversations?.()");
    expect(profileMenu).toContain("hover:bg-[#d66d75]/10");
    expect(profileMenu).not.toContain(
      "cursor-not-allowed items-center gap-2.5 px-3.5 py-2 text-[13px] text-[#d66d75]/40",
    );
    expect(sidebar).toContain("deleteAllConversations");
    expect(sidebar).toContain("isDeleteAllDialogOpen");
    expect(sidebar).toContain("settings.data.delete_all_confirm.title");
    expect(sidebar).toContain("response.deleted_count");
    expect(sidebar).toContain("onAllConversationsDeleted?.()");
    expect(sidebar).toContain("settings.data.delete_all_success");
    expect(sidebar).toContain("settings.data.delete_all_empty");
    expect(sidebar).toContain("settings.data.delete_all_error");
    expect(chat).toContain("handleAllConversationsDeleted");
    expect(chat).toContain("resetToEmptyChatSurface();");
    expect(chat).toContain("onToast={showToast}");
    expect(en).toContain("delete_all_success_one");
    expect(en).toContain("Moved {{count}} conversation to Recently Deleted.");
    expect(es).toContain("delete_all_success_one");
    expect(es).toContain(
      "Se movió {{count}} conversación a Borrados recientemente.",
    );
  });

  test("interactive controls expose pointer cursor affordance globally", () => {
    const globals = readFileSync(join(root, "app/globals.css"), "utf-8");

    expect(globals).toContain("button:not(:disabled)");
    expect(globals).toContain('[role="button"]:not([aria-disabled="true"])');
    expect(globals).toContain("a[href]");
    expect(globals).toContain("label[for]");
    expect(globals).toContain("cursor: pointer;");
    expect(globals).toContain("button:disabled");
    expect(globals).toContain('[aria-disabled="true"]');
    expect(globals).toContain("cursor: not-allowed;");
  });

  test("legacy auth routes redirect into the front door auth states", () => {
    const login = readFileSync(join(root, "app/login/page.tsx"), "utf-8");
    const signup = readFileSync(join(root, "app/signup/page.tsx"), "utf-8");

    expect(login).toContain('redirect("/?auth=login")');
    expect(signup).toContain('redirect("/?auth=signup")');
  });

  test("account recovery and session controls expose localized dedicated surfaces", () => {
    const forgot = join(root, "app/auth/forgot-password/page.tsx");
    const recovery = join(root, "app/auth/recovery/page.tsx");
    const security = join(root, "app/account/security/page.tsx");
    const recoveryRoute = join(root, "app/api/auth/recovery/route.ts");
    const authForm = readFileSync(
      join(root, "components/auth/AuthForm.tsx"),
      "utf-8",
    );
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    expect(authForm).toContain("/auth/forgot-password");
    expect(existsSync(forgot)).toBe(true);
    expect(existsSync(recovery)).toBe(true);
    expect(existsSync(security)).toBe(true);
    expect(existsSync(recoveryRoute)).toBe(true);
    expect(en.auth.recovery.generic_sent).toBeTruthy();
    expect(es.auth.recovery.generic_sent).toBeTruthy();
    expect(en.account_security.sessions.sign_out_others).toBeTruthy();
    expect(es.account_security.sessions.sign_out_others).toBeTruthy();
    expect(en.common.confirm).toBe("Confirm");
    expect(es.common.confirm).toBe("Confirmar");
    expect(en.account_security.session_check_unavailable).toBeTruthy();
    expect(es.account_security.session_check_unavailable).toBeTruthy();
  });

  test("profile menu Security row navigates to account security and closes the menu", () => {
    const menu = readFileSync(
      join(root, "components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    const securityLabel = menu.indexOf('t("settings.data.security"');
    expect(securityLabel).toBeGreaterThan(-1);
    const securityButton = menu.slice(
      menu.lastIndexOf("<button", securityLabel),
      securityLabel,
    );
    expect(securityButton).toContain(
      'navigateFromOverlay("/account/security", onClose)',
    );
    expect(securityButton).not.toContain("disabled");
    expect(securityButton).not.toContain("cursor-not-allowed");
    expect(en.settings.data.security).toBeTruthy();
    expect(es.settings.data.security).toBeTruthy();

    const usageLabel = menu.indexOf('t("settings.data.usage"');
    expect(usageLabel).toBeGreaterThan(-1);
    const usageButton = menu.slice(
      menu.lastIndexOf("<button", usageLabel),
      usageLabel,
    );
    expect(usageButton).toContain('openModal("usage")');
    expect(usageButton).not.toContain("disabled");
    expect(usageButton).not.toContain("cursor-not-allowed");
  });

  test("landing redirects authenticated sessions straight into chat", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");

    expect(page).toContain("await getMe()");
    expect(page).toContain("router.replace(postAuthPath())");
    expect(page).toContain("skipAuthenticatedRedirect");
    expect(page).toContain("<CuadraoLockup width={268} />");
    expect(page).toContain("font-display flex w-full max-w-sm");
  });

  test("landing front door adapts signup and login inline", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");
    const authForm = readFileSync(
      join(root, "components/auth/AuthForm.tsx"),
      "utf-8",
    );

    expect(authForm).toContain("Eye");
    expect(authForm).toContain("EyeClosed");
    expect(authForm).not.toContain("EyeOff");
    expect(authForm).toContain("showPassword");
    expect(authForm).toContain('type={showPassword ? "text" : "password"}');
    expect(authForm).toContain("auth.password.show");
    expect(authForm).toContain("auth.password.hide");
    expect(page).toContain("signupWithEmail");
    expect(page).toContain("loginWithEmail");
    expect(page).toContain(
      'type AuthMode = "intro" | "request" | "signup" | "login"',
    );
    expect(page).toContain('updateAuthMode("request")');
    expect(page).toContain('updateAuthMode("signup")');
    expect(page).toContain('const showLogin = () => updateAuthMode("login")');
    expect(page).toContain('href="/terms"');
    expect(page).toContain('href="/privacy"');
    expect(page).not.toContain('const authHref = "/chat"');
    expect(page).not.toContain("href={authHref}");
    expect(page).not.toContain('href="/login"');
    expect(page).not.toContain('href="#"');
  });

  test("auth exits return to the clean front door", () => {
    const chatPage = readFileSync(join(root, "app/chat/page.tsx"), "utf-8");
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );

    expect(chatPage).toContain("authLoginPathFromSearch");
    expect(chatPage).not.toContain('redirect("/login")');
    expect(chat).toContain("leaveSession(");
    expect(chat).not.toContain('window.location.href = "/?auth=login"');
    expect(chat).not.toContain('window.location.href = "/login"');
  });

  test("ordinary logout leaves only after provider revocation and clears private state", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const flow = readFileSync(join(root, "lib/logout-flow.ts"), "utf-8");
    const logoutHandler = chat.slice(
      chat.indexOf("const handleLogout = async ("),
      chat.indexOf("const handleCancelConfirmationAction"),
    );

    expect(logoutHandler).toContain("settings.logout_error");
    expect(logoutHandler).toContain("resetToEmptyChatSurface()");
    expect(logoutHandler).toContain("clearHistory()");
    expect(flow).toContain('result?.revocation === "failed"');
    expect(flow.indexOf("deps.clearLocalState()")).toBeLessThan(
      flow.indexOf("deps.navigate(signedOutLanding(deps.businessBuild, deps.accountDeleted))"),
    );
  });

  test("front door auth states stay interactive during auth entry", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");

    expect(page).toContain(
      'authMode === "signup" ||\n    authMode === "login"',
    );
    expect(page).toContain('params.get("preview") === "true"');
  });

  test("no settings surface offers a subscription", () => {
    // The only subscription section lived in the unreachable full-page view.
    expect(existsSync(join(root, "components/views/SettingsView.tsx"))).toBe(
      false,
    );
    expect(readFileSync(join(root, ".env.local.example"), "utf-8")).not.toContain(
      "NEXT_PUBLIC_ARGUS_SHOW_SUBSCRIPTION",
    );
  });

  test("sidebar keeps omnisearch enabled without legacy strategy navigation", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const sidebar = readFileSync(
      join(root, "components/sidebar/ChatSidebar.tsx"),
      "utf-8",
    );
    const flags = readFileSync(
      join(root, "lib/private-alpha-flags.ts"),
      "utf-8",
    );

    expect(flags).not.toContain("NEXT_PUBLIC_STRATEGIES_ENABLED");
    expect(flags).toContain("NEXT_PUBLIC_OMNISEARCH_ENABLED");
    expect(flags).toContain(
      'process.env.NEXT_PUBLIC_OMNISEARCH_ENABLED !== "false"',
    );
    expect(chat).toMatch(
      /omnisearchEnabled &&\s*\(!isGuest \|\| canUseOmnisearch\) &&\s*searchOverlayOpen/,
    );
    expect(sidebar).not.toContain("strategiesEnabled");
    expect(sidebar).toContain("omnisearchEnabled");
    expect(sidebar).toContain("{omnisearchEnabled && (");
    expect(sidebar).not.toContain('onNavigate("strategies")');
    expect(sidebar).toContain("common.recents");
  });

  test("strategies view is no longer shipped", () => {
    expect(
      existsSync(join(root, "components/views/StrategiesView.tsx")),
    ).toBe(false);
  });

  test("no shadow utility classes are used in chat input", () => {
    const file = readFileSync(
      join(root, "components/chat/ChatInput.tsx"),
      "utf-8",
    );
    expect(file).not.toContain("shadow");
  });

  test("chat hides backend enum labels and technical runtime errors", () => {
    const input = readFileSync(
      join(root, "components/chat/ChatInput.tsx"),
      "utf-8",
    );
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const locale = readFileSync(
      join(root, "public/locales/en/common.json"),
      "utf-8",
    );

    expect(input).toContain("displayDiscoveryDescription");
    expect(input).toContain("Currency Pair");
    expect(chat).not.toContain("event.data.detail || t('chat.error_backtest')");
    expect(locale).not.toContain("Check that the API is running");
    expect(locale).not.toContain("add the asset, amount, and time period");
  });

  test("chat stream errors preserve status for stale conversation recovery", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");

    expect(api).toContain("class ChatStreamError");
    expect(api).toContain("response.status");
    expect(chat).toContain("err instanceof ChatStreamError");
    expect(chat).toContain("err.status === 404");
    expect(chat).toContain("clearActiveConversationPointer()");
    expect(chat).toContain("await streamToConversation(conversation.id)");
  });

  test("apiFetch does not leak request options to the console", () => {
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    expect(api).not.toContain("[argus-api] Fetching");
  });
});
