import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

describe("chat archive/delete lifecycle source contract", () => {
  test("chat switching routes cold misses through the bounded transcript cache", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const loadConversationStart = chat.indexOf("const loadConversation = async (");
    const loadConversationEnd = chat.indexOf("const loadConversationForRun", loadConversationStart);
    const loadConversation = chat.slice(loadConversationStart, loadConversationEnd);

    expect(loadConversationStart).toBeGreaterThan(-1);
    expect(chat).toContain("new TranscriptSessionCache<SavedConversationTranscript>()");
    expect(loadConversation).toContain(
      "convId, undefined, { messageId, scrollToLatest }",
    );
    expect(loadConversation).not.toContain('setStreamStatus(t("common.loading"))');
    expect(chat).toContain('phase === "loading"');
    expect(chat).toContain("setMessages([])");
    expect(chat).toContain("COLD_TRANSCRIPT_RETRIEVAL_DELAY_MS");
    expect(chat).toContain("loadAllConversationMessagePages(");
    expect(chat).toContain("loadSavedConversationTranscript(targetConversationId, signal)");
  });

  test("conversation retrieval is transcript-owned accessible and localized", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const retrieval = readFileSync(
      join(root, "components/chat/ConversationRetrievalState.tsx"),
      "utf-8",
    );
    const announcement = retrieval.slice(
      retrieval.indexOf("export function ConversationRetrievalAnnouncement"),
      retrieval.indexOf("export default function ConversationRetrievalState"),
    );
    const visibleRetrievalState = retrieval.slice(
      retrieval.indexOf("export default function ConversationRetrievalState"),
    );
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    expect(chat).toContain('data-testid="conversation-transcript-region"');
    expect(chat).toContain('data-conversation-id={conversationId ?? undefined}');
    expect(chat).toContain('role="region"');
    expect(chat).toContain('aria-label={t("common.conversation", "Conversation")}');
    expect(chat).toContain(
      "aria-busy={isHydratingConversation}",
    );
    expect(announcement).toContain(
      'data-testid="conversation-retrieval-announcement"',
    );
    expect(announcement).toContain('className="sr-only"');
    expect(announcement).toContain('role="status"');
    expect(announcement).toContain('aria-live="polite"');
    expect(visibleRetrievalState).toContain(
      'data-testid="conversation-retrieval-state"',
    );
    expect(visibleRetrievalState).toContain('aria-hidden="true"');
    expect(visibleRetrievalState).not.toContain('role="status"');
    expect(visibleRetrievalState).not.toContain('aria-live="polite"');
    expect(retrieval).toContain("motion-reduce:animate-none");
    expect(en.chat.opening_conversation).toBe("Opening conversation…");
    expect(es.chat.opening_conversation).toBe("Abriendo la conversación…");
    expect(en.chat.error_open_conversation).toBe(
      "Couldn’t open this conversation.",
    );
    expect(es.chat.error_open_conversation).toBe(
      "No se pudo abrir esta conversación.",
    );
  });

  test("transcript cache lifecycle clears auth and evicts only transcript mutations", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const lifecycle = readFileSync(
      join(root, "components/chat/useChatSurfaceLifecycle.ts"),
      "utf-8",
    );
    const polling = readFileSync(
      join(root, "lib/chat-run-reconciliation.ts"),
      "utf-8",
    );

    expect(chat).toContain("clearAuthenticatedState()");
    expect(chat).toContain('"message_send"');
    expect(chat).toContain('"retry"');
    expect(lifecycle).toContain("onConversationRemoved");
    expect(lifecycle).not.toContain("onAllConversationsDeleted");
    expect(chat).toContain('"conversation_delete"');
    expect(polling).toContain("onDurableCompletion");
    expect(chat).toContain('"durable_job_completion"');
  });

  test("active archive and delete navigate away from the removed chat", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const sidebar = readFileSync(join(root, "components/sidebar/ChatSidebar.tsx"), "utf-8");
    const palette = readFileSync(join(root, "components/sidebar/ChatCommandPalette.tsx"), "utf-8");

    expect(chat).toContain("handleConversationRemoved");
    expect(chat).toContain("historyItemBelongsToConversation");
    expect(chat).toContain("setHistoryItems((prev) =>");
    expect(chat).toContain("onConversationRemoved={handleConversationRemoved}");
    expect(sidebar).toContain("function historyConversationId");
    expect(sidebar).toContain("const itemConversationId = historyConversationId(item)");
    expect(sidebar).toContain("item.id === itemConversationId ? item : { ...item, id: itemConversationId }");
    expect(sidebar).toContain('aria-current={isActiveConversation ? "page" : undefined}');
    expect(sidebar).toContain('data-active-conversation={isActiveConversation ? "true" : undefined}');
    expect(sidebar).toContain('e.key === " "');
    expect(sidebar).toContain("focus-visible:ring-2");
    expect(sidebar).toContain("onConversationRemoved?.(id)");
    expect(sidebar).toContain("onConversationRemoved?.(pendingDeleteId)");
    expect(palette).toContain("onConversationRemoved?.(item.conversationId)");
    expect(palette).toContain("onConversationRemoved?.(pendingDeleteItem.conversationId)");
  });

  test("stale or deleted active chats reset to a lazy empty chat instead of creating a new stored conversation", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const initBlock = readFileSync(
      join(root, "components/chat/useInitialChatSession.ts"),
      "utf-8",
    );
    const lifecycle = readFileSync(
      join(root, "components/chat/useChatSurfaceLifecycle.ts"),
      "utf-8",
    );
    const removedStart = lifecycle.indexOf("const handleConversationRemoved");
    const removedEnd = lifecycle.indexOf(
      "return {",
      removedStart,
    );
    const removedBlock = lifecycle.slice(removedStart, removedEnd);

    expect(chat).toContain("resetToEmptyChatSurface");
    expect(initBlock).not.toContain("await createConversation(resolvedLanguage)");
    expect(initBlock).not.toContain("readActiveConversationIdFromUrl() ?? readActiveConversationId()");
    expect(initBlock).toContain("resetToEmptyChatSurface");
    expect(initBlock).toContain("navigateConversationTranscript");
    expect(initBlock).toContain("bootstrap: true");
    expect(chat).toContain("if (snapshot.messages.length === 0)");
    expect(chat).toContain('import { useRouter } from "next/navigation";');
    expect(chat).toContain("const router = useRouter();");
    expect(chat).toContain("router.replace(clearedRoute, { scroll: false });");
    expect(removedBlock).toContain("resetToEmptyChatSurface");
    expect(removedBlock).not.toContain("startNewChat()");
  });

  test("a missing bootstrap conversation is pruned without removing an interactive failure", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const viewHelpers = readFileSync(
      join(root, "lib/chat-conversation-view-helpers.ts"),
      "utf-8",
    );
    const navigationStart = chat.indexOf(
      "async function navigateConversationTranscript(",
    );
    const navigationEnd = chat.indexOf(
      "// ── Init conversation",
      navigationStart,
    );
    const navigation = chat.slice(navigationStart, navigationEnd);

    expect(viewHelpers).toContain(
      "function isMissingConversationLoadError(error: unknown)",
    );
    expect(navigation).toContain("options.bootstrap &&");
    expect(navigation).toContain("isMissingConversationLoadError(state.error)");
    expect(navigation).toContain("setHistoryItems((current) =>");
    expect(navigation).toContain("!historyItemBelongsToConversation(");
    expect(navigation).toContain("targetConversationId");
  });

  test("restoring archived or deleted chats refreshes visible history", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const sidebar = readFileSync(join(root, "components/sidebar/ChatSidebar.tsx"), "utf-8");
    const profileMenu = readFileSync(join(root, "components/sidebar/ProfileMenu.tsx"), "utf-8");
    const profilePanels = readFileSync(join(root, "components/sidebar/ProfileSettingsPanels.tsx"), "utf-8");
    const archived = readFileSync(join(root, "components/settings/ArchivedChatsView.tsx"), "utf-8");
    const deleted = readFileSync(join(root, "components/settings/DeletedItemsView.tsx"), "utf-8");

    expect(chat).toContain("onHistoryMutated={refreshHistory}");
    expect(sidebar).toContain("onHistoryMutated={onHistoryMutated}");
    expect(profileMenu).toContain("onHistoryMutated?: () => void");
    // The menu threads it to the panel dispatch, which owns the panels.
    expect(profileMenu).toContain("onHistoryMutated={onHistoryMutated}");
    expect(profilePanels).toContain("onRestored={onHistoryMutated}");
    expect(archived).toContain("onRestored?: () => void");
    expect(archived).toContain("onRestored?.()");
    expect(deleted).toContain("onRestored?: () => void");
    expect(deleted).toContain("onRestored?.()");
  });

  test("persisted result cards are validated before structured hydration", () => {
    const projection = readFileSync(
      join(root, "components/chat/chat-message-projection.ts"),
      "utf-8",
    );
    const hydration = readFileSync(join(root, "lib/chat-message-hydration.ts"), "utf-8");
    const hydrateStart = projection.indexOf(
      "export function hydrateMessagesFromApi(",
    );
    const hydrateBlock = projection.slice(hydrateStart);

    expect(hydration).toContain("export function isHydratableResultCard(");
    expect(hydrateBlock).toContain(
      "isHydratableResultCard(metadata.result_card)",
    );
    expect(hydrateBlock).not.toContain(
      "metadata.result_card &&\n        Array.isArray(metadata.result_card.rows)",
    );
  });

  test("header delete requires a selected chat and confirmation", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const shortcuts = readFileSync(join(root, "lib/keyboard-shortcuts.ts"), "utf-8");
    const headerMenu = readFileSync(
      join(root, "components/chat/ChatHeaderMenu.tsx"),
      "utf-8",
    );

    const dialog = readFileSync(join(root, "components/chat/ConversationDeleteDialog.tsx"), "utf-8");
    expect(dialog).toContain('import { ConfirmDialog } from "@/components/ui/ConfirmDialog";');
    expect(chat).toContain('import type { KeyboardDeleteRequest } from "@/lib/keyboard-shortcuts";');
    expect(chat).toContain("useState<KeyboardDeleteRequest | null>(null)");
    expect(shortcuts).toContain("export type KeyboardDeleteRequest = {");
    expect(shortcuts).toContain("conversationId: string;");
    expect(shortcuts).toContain("showKeyboardHints: boolean;");
    expect(chat).toContain("const [isDeletingHeaderChat, setIsDeletingHeaderChat] = useState(false);");
    expect(chat).toContain("if (!conversationId) return;");
    expect(chat).toContain("setPendingHeaderDelete({ conversationId, showKeyboardHints: fromKeyboardShortcut });");
    expect(chat).toContain("deleteConversation(pendingHeaderDelete.conversationId)");
    expect(chat).toContain("handleConversationRemoved(pendingHeaderDelete.conversationId);");
    expect(chat).toContain("pending={pendingHeaderDelete}");
    expect(dialog).toContain("isOpen={Boolean(pending)}");
    expect(dialog).toContain("showKeyboardHints={pending?.showKeyboardHints}");
    expect(chat).toContain('currentView === "chat" &&');
    expect(chat).toContain("conversationId &&");
    expect(chat).toContain("canManageConversation ? (");
    expect(chat).toContain("isDeleting={isDeletingHeaderChat}");
    expect(headerMenu).toContain("disabled={isDeleting}");
  });

  test("chat disclaimer appears only after conversation activity and is localized", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const legal = readFileSync(join(root, "components/chat/ChatLegalNotice.tsx"), "utf-8");
    const en = JSON.parse(readFileSync(join(root, "public/locales/en/common.json"), "utf-8"));
    const es = JSON.parse(readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"));
    const coldStartBranchStart = chat.indexOf("{messages.length === 0 ? (");
    const coldStartBranchEnd = chat.indexOf(") : (", coldStartBranchStart);
    const coldStartBranch = chat.slice(coldStartBranchStart, coldStartBranchEnd);
    const conversationComposerStart = chat.indexOf("Input fade + bar");
    const conversationComposerEnd = chat.indexOf("</div>\n                </div>\n              </>", conversationComposerStart);
    const conversationComposer = chat.slice(conversationComposerStart, conversationComposerEnd);

    expect(chat).toContain("const showConversationDisclaimer = shouldShowConversationDisclaimer(");
    expect(coldStartBranch).not.toContain("chat.disclaimer");
    expect(conversationComposer).toContain(
      "showRegisteredDisclaimer={showConversationDisclaimer}",
    );
    expect(legal).toContain('data-testid="chat-disclaimer"');
    expect(legal).toContain('"chat.disclaimer"');
    expect(legal).toContain("text-[13px]");
    expect(legal).toContain("font-normal");
    expect(legal).toContain("text-black/40 dark:text-white/40");
    expect(en.chat.disclaimer).toBe("Argus can make mistakes. For education only. Not financial advice.");
    expect(es.chat.disclaimer).toBe("Argus puede equivocarse. Solo con fines educativos. No es asesoría financiera.");
  });

  test("guest expiry copy is gone and the registered disclaimer stays on both layouts", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const emptyChat = readFileSync(join(root, "components/chat/EmptyChatSurface.tsx"), "utf-8");
    const legal = readFileSync(join(root, "components/chat/ChatLegalNotice.tsx"), "utf-8");
    const sidebar = readFileSync(join(root, "components/sidebar/ChatSidebar.tsx"), "utf-8");

    expect(existsSync(join(root, "components/guest/GuestLegalFooter.tsx"))).toBe(false);
    expect(`${chat}\n${emptyChat}`.match(/<ChatLegalNotice/g)?.length).toBe(2);
    expect(`${chat}\n${emptyChat}`).not.toContain("temporaryExpiresAt=");
    expect(legal).not.toContain("GuestLegalFooter");
    expect(sidebar).not.toContain("guest-sidebar-expiry");
    expect(sidebar).not.toContain("temporaryExpiresAt");
  });

  test("the adjacent user-turn Retry control keeps a 44px minimum tap target", () => {
    const message = readFileSync(join(root, "components/chat/ChatMessage.tsx"), "utf-8");
    const retryStart = message.indexOf('data-testid="user-turn-retry"');
    const retryEnd = message.indexOf("</button>", retryStart);
    const retryButton = message.slice(retryStart, retryEnd);

    expect(retryStart).toBeGreaterThan(-1);
    expect(retryEnd).toBeGreaterThan(retryStart);
    expect(retryButton).toContain("min-h-11");
    expect(retryButton).toContain("min-w-11");
    expect(retryButton).not.toContain("min-h-9");
  });

  test("durable retry matches the assistant footer icon treatment without losing its label", () => {
    const message = readFileSync(join(root, "components/chat/ChatMessage.tsx"), "utf-8");
    const assistantRetryStart = message.indexOf(
      "<Tooltip content={actionLabel(retryAction)}",
    );
    const assistantRetryEnd = message.indexOf("</button>", assistantRetryStart);
    const assistantRetryButton = message.slice(
      assistantRetryStart,
      assistantRetryEnd,
    );
    const userRetryStart = message.indexOf('data-testid="user-turn-retry"');
    const userRetryEnd = message.indexOf("</button>", userRetryStart);
    const userRetryButton = message.slice(userRetryStart, userRetryEnd);

    expect(message).toContain("const retryIconButtonClass");
    expect(assistantRetryButton).toContain("retryIconButtonClass");
    expect(userRetryButton).toContain("retryIconButtonClass");
    expect(userRetryButton).toContain("aria-label={retryLabel}");
    expect(message).toContain("<Tooltip content={retryLabel}");
    expect(userRetryButton).not.toContain("\n          {retryLabel}\n");
  });

  test("ordinary transport ambiguity follows durable pages and never builds composer retry", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const hydration = readFileSync(join(root, "lib/chat-message-hydration.ts"), "utf-8");
    const catchStart = chat.indexOf("try {\n        await streamToConversation");
    const catchEnd = chat.indexOf("// \u2500\u2500 Action routing", catchStart);
    const sendCatch = chat.slice(catchStart, catchEnd);

    expect(catchStart).toBeGreaterThan(-1);
    expect(sendCatch).toContain("resolveOrdinaryTransportAmbiguityView");
    expect(sendCatch).toContain("loadAllConversationMessagePages");
    expect(sendCatch).toContain("conversationLoadFailureMessage");
    expect(sendCatch).toContain('t("chat.status.checking")');
    expect(sendCatch.indexOf('setStreamStatus(t("chat.status.checking"))')).toBeLessThan(
      sendCatch.indexOf("await resolveOrdinaryTransportAmbiguityView"),
    );
    expect(sendCatch).toContain("signal: requestSession.controller.signal");
    expect(sendCatch).toContain(
      'requestSessions.authorize(requestSession, "ambiguity")',
    );
    expect(sendCatch).toContain(
      "settleRetestReceiptProjection(view.messages, current, userMsg.id)",
    );
    expect(sendCatch).toContain("finishRequestTransport(requestSession)");
    expect(sendCatch).not.toContain("conversationActivity.settleRequest");
    expect(chat).not.toContain("cancelOrdinaryTransportReconciliation();");
    expect(hydration).toContain("resolveOrdinaryTransportAmbiguity");
    expect(hydration).toContain('resolution.kind !== "terminal"');
    expect(hydration).toContain("message.id !== fallback.assistantId");
    expect(sendCatch).not.toContain(
      "actions: retryLastTurnAction ? [retryLastTurnAction] : m.actions",
    );
  });

  test("text and structured ordinary turns snapshot ids before paged reconciliation", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const sendStart = chat.indexOf("const handleSend = async");
    const sendEnd = chat.indexOf("// \u2500\u2500 Action routing", sendStart);
    const send = chat.slice(sendStart, sendEnd);

    expect(send).toContain('action?.type !== "run_backtest"');
    expect(send).toContain("snapshotOrdinaryTransportMessageIds");
    expect(send).toContain("ordinaryTransportMessageIds");
    expect(send).toContain("resolveOrdinaryTransportAmbiguityView");
    expect(send).not.toContain(
      'const isOrdinaryTransportAmbiguity =\n        !action?.type',
    );
    const ambiguityStart = send.indexOf("if (isOrdinaryTransportAmbiguity)");
    const ambiguityEnd = send.indexOf(
      "const confirmationId = ambiguousRunConfirmationId",
      ambiguityStart,
    );
    expect(send.slice(ambiguityStart, ambiguityEnd)).not.toContain(
      "streamToConversation(",
    );
  });

  test("successful durable decisions invalidate the owning transcript cache", () => {
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const message = readFileSync(
      join(root, "components/chat/ChatMessage.tsx"),
      "utf-8",
    );
    const card = readFileSync(
      join(root, "components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );
    const cache = readFileSync(
      join(root, "lib/chat-transcript-session-cache.ts"),
      "utf-8",
    );
    // The shared affordance calls onSaved only after the durable write
    // succeeded, so the card's callback is the success slice.
    const decisionSuccessStart = card.indexOf(
      "onSaved: async (decision) => {",
    );
    const decisionSuccessEnd = card.indexOf(
      "if (!memoryProposalEnabled) return;",
      decisionSuccessStart,
    );
    const decisionSuccess = card.slice(
      decisionSuccessStart,
      decisionSuccessEnd,
    );
    expect(decisionSuccessStart).toBeGreaterThan(-1);
    expect(decisionSuccessEnd).toBeGreaterThan(decisionSuccessStart);
    expect(decisionSuccess).toContain(
      "setSavedDecisionState(decision.decision_state)",
    );
    expect(decisionSuccess).toContain(
      "onDecisionSaved?.(decision.decision_state)",
    );
    expect(decisionSuccess.indexOf("setSavedDecisionState")).toBeLessThan(
      decisionSuccess.indexOf("onDecisionSaved?.("),
    );
    expect(message).toContain(
      "onDecisionSaved?: (decisionState: DecisionState) => void",
    );
    expect(message).toContain("onDecisionSaved={onDecisionSaved}");
    expect(chat).toContain("onDecisionSaved={(decisionState) =>");
    expect(chat).toContain(
      'invalidateTranscriptForMutation(conversationId, "durable_result_action")',
    );
    expect(cache).toContain('| "durable_result_action"');
  });

});
