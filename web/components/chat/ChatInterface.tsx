"use client";

import { useCallback, useMemo, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useReceiptFollowup, readReceiptFollowup } from "./useReceiptFollowup";
import { useProfileUpdates } from "@/components/chat/useProfileUpdates";
import { useTranslation } from "react-i18next";
import { currentAuthLoginPath, signedInHomePath } from "@/lib/landing-intent";
import ChatCommandPalette from "@/components/sidebar/ChatCommandPalette";
import { KeyboardShortcutSurfaces } from "@/components/keyboard/KeyboardShortcutSurfaces";
import { useChatKeyboardShortcuts } from "@/components/keyboard/useChatKeyboardShortcuts";
import ChatSidebar from "@/components/sidebar/ChatSidebar";
import { useSidebarPreference } from "@/components/sidebar/useSidebarPreference";
import SidebarPreferenceModal from "@/components/settings/SidebarPreferenceModal";
import ConversationActivityAnnouncement from "@/components/chat/ConversationActivityAnnouncement";
import ConversationActivityRail from "@/components/chat/ConversationActivityRail";
import { ConversationActivityPresentationProvider } from "@/components/chat/ConversationActivityIndicator";
import { ConversationActivityJumpButton } from "@/components/chat/ConversationActivityJumpButton";
import ChatLegalNotice from "@/components/chat/ChatLegalNotice";
import ChatToast from "@/components/chat/ChatToast";
import { useChatToast } from "@/components/chat/useChatToast";
import EmptyChatSurface from "@/components/chat/EmptyChatSurface";
import {
  useInitialChatSession,
  type ProfileState,
} from "@/components/chat/useInitialChatSession";
import { executeChatTranscriptUpdateScroll, useChatScrollControls } from "@/components/chat/useChatScrollControls";
import { useChatSurfaceLifecycle } from "@/components/chat/useChatSurfaceLifecycle";
import { useArchiveActiveConversation } from "@/components/chat/useArchiveActiveConversation";
import { toggleConversationUnread } from "@/components/chat/toggleConversationUnread";
import { useRecentConversations } from "@/components/chat/useRecentConversations";
import { conversationActivityMutationNoticeDescriptor, useConversationActivity } from "@/components/chat/useConversationActivity";
import { useConversationTranscriptFreshness } from "./useConversationTranscriptFreshness";
import { loadSavedConversationTranscript, type SavedConversationTranscript } from "@/lib/conversation-transcript-freshness";
import { chatFinalPayloadOwnsVisibleTerminalArtifact, clearConversationActivityTranscript, conversationActivityMutationRequiresCanonicalHydration, createConversationActivityTerminalReadinessSession, createConversationActivityTranscriptReadiness, promoteCanonicalConversationActivityTranscript, synchronizeConversationViewRefs, useConversationActivityViewport } from "@/components/chat/useConversationActivityViewport";
import GuestExperienceSurfaces from "@/components/guest/GuestExperienceSurfaces";
import GuestHeader from "@/components/guest/GuestHeader";
import ExpiredGuestSession from "@/components/guest/ExpiredGuestSession";
import {
  useGuestExperience,
  useGuestSendBridge,
  type GuestResumeSend,
} from "@/components/guest/useGuestExperience";
import {
  createConversation,
  deleteConversation,
  postFeedback,
  getBacktestRun,
  listConversations,
  logoutFromApi,
  patchConversation,
  getMe,
  resultCardFromRun,
  streamChatMessage,
  ChatStreamError,
  type ChatStreamEvent,
  type ChatActionRequest,
  type HistoryItem,
  type BacktestRun, type BacktestJobResponse,
  type SearchConversationItem,
} from "@/lib/argus-api";
import { endSessionKeepingSurface, type LogoutOptions } from "@/lib/account-deletion-api";
import type { KeyboardDeleteRequest } from "@/lib/keyboard-shortcuts";
import { businessPilotEnabled, omnisearchEnabled, researchRailEnabled } from "@/lib/private-alpha-flags";
import { leaveSession } from "@/lib/logout-flow";
import {
  useTranscriptTurnAnchor,
  type PendingMessageAnchor,
  type PendingScrollRestore,
} from "@/components/chat/useTranscriptTurnAnchor";
import {
  durableRetryLastTurnFromStreamError,
  failedActionRetryActionFromMetadata,
  hasFailedActionMetadata,
  isRetryAction,
  normalizeDurableRetryActionHistory,
  retryLastTurnActionFromMetadata,
  retryLastTurnActionFromMessage,
  retryLastTurnChatActionFromAction,
  retryLastTurnFailedAssistantIdFromAction,
  retryLastTurnMessageFromAction,
  retryLastTurnRequestMessageIdFromAction,
  retryLastTurnSendOptions,
  retryLoadConversationIdFromAction,
} from "@/lib/chat-retry-actions";
import { RETEST_ACTION_TYPE, applyRetestReceipt, retestReceiptFromFinalPayload, settleRetestReceiptProjection } from "@/lib/chat-retest";
import { omnisearchActionHandlers } from "./omnisearch-actions";
import { projectedTranscriptAnchorId } from "@/lib/chat-retry-action-history";
import {
  clearActiveConversationPointer,
  isCurrentAnchoredConversationRequest,
  readActiveConversationRouteState,
  rememberActiveConversationId,
  shouldApplyConversationOwnedUpdate,
  shouldStartConversationForVisibleEmptyChat,
  targetConversationIdForSend,
} from "@/lib/chat-conversation-routing";
import {
  conversationLoadFailureMessage,
  shouldShowEmptyChatSurface,
  shouldShowConversationDisclaimer,
} from "@/lib/chat-conversation-load-state";
import {
  COLD_TRANSCRIPT_RETRIEVAL_DELAY_MS,
  historyItemBelongsToConversation,
  isMissingConversationLoadError,
  POST_TURN_TITLE_REFRESH_DELAYS_MS,
} from "@/lib/chat-conversation-view-helpers";
import { activeConfirmationIdFrom } from "@/lib/chat-confirmation-peers";
import { toolResultRecomputeHandler } from "@/lib/tool-result-recompute";
import { answerAssumptionsFromMetadata, toolCardsFromMetadata, hasUnavailableToolCards, toolProgressText } from "@/lib/tool-result-card";
import { mergeFinalTextMessage } from "@/lib/chat-final-message";
import { resultReadoutContentFromMetadata } from "@/lib/result-readout-content";
import { resultReadoutFacts } from "@/lib/result-readout-facts";
import {
  discoveryCandidateMention,
  discoverySidecarFromMetadata,
  researchDegradedCodeFromMetadata,
  researchSourcesForFinalPayload,
} from "@/lib/chat-discovery-sidecar";
import {
  recoveryActionsFromMetadata,
  recoveryDisplayFromMetadata,
  retryableAssistantRecoveryCode,
} from "@/lib/chat-recovery-display";
import {
  nextExperimentRowsFromMetadata,
  nextExperimentsSourceRunIdFromMetadata,
} from "@/lib/chat-next-experiments";
import { nextStepsFromMetadata } from "@/lib/chat-next-steps";
import {
  loadAllConversationMessagePages,
  resolveOrdinaryTransportAmbiguityView,
  snapshotOrdinaryTransportMessageIds,
  strategyPathContextFromMetadata,
} from "@/lib/chat-message-hydration";
import {
  hydrateResultActionsForRun,
} from "@/lib/chat-result-actions";
import {
  appendOrReplacePendingAssistantMessage,
  replaceOrAppendFinalAssistantMessage,
} from "@/lib/chat-send-state";
import {
  applyBacktestJobUpdate,
  backtestJobFromFinalPayload,
  toolJobsFromMetadata,
  backtestJobMessage,
} from "@/lib/chat-backtest-jobs";
import {
  applyRecoverableRunReconciliation,
  ambiguousRunConfirmationId,
  applyReconciledBacktestJobResponse,
  getBacktestJobByAction,
  reconcileAmbiguousRunResponse,
  throwIfAmbiguousRunSseError,
  throwIfAmbiguousRunStreamTermination,
  useBacktestJobPolling,
} from "@/lib/chat-run-reconciliation";
import { isConfirmationAction } from "@/lib/chat-action-ownership";
import { createConversationActivityCausalClock } from "@/lib/conversation-activity-state";
import {
  createChatRequestSessionController,
  type ChatRequestSession,
  visibleRequestStatus,
} from "@/lib/chat-request-session";
import { sidebarOpenAfterTransientNavigation } from "@/lib/sidebar-mode-state";
import {
  TranscriptSessionCache,
  type TranscriptMutation,
  type TranscriptNavigationState,
} from "@/lib/chat-transcript-session-cache";
import { renamePrefillTitle } from "@/lib/chat-title-display";
import { useActiveConversationTitle } from "@/lib/chat-header-title-state";
import ChatHeaderMenu from "./ChatHeaderMenu";
import { ShareReceiptPanel } from "./ShareReceiptAction";
import { ReceiptConversationProvider, ReceiptConversationTurn, ReceiptSelectionComposer } from "./ReceiptConversationSelection";
import { evidenceReceiptSharingEnabled } from "@/lib/private-alpha-flags";
import ChatHeaderTitle from "./ChatHeaderTitle";
import ChatInput from "./ChatInput";
import ChatMessage from "./ChatMessage";
import ConversationRetrievalState, {
  ConversationRetrievalAnnouncement,
  InitialConversationRetrievalState,
} from "./ConversationRetrievalState";
import FeedbackDialog from "../feedback/FeedbackDialog";
import { feedbackContextForSubmission } from "@/lib/feedback-context";
import { pendingArtifactCardFromPayload } from "@/lib/pending-artifact-card";
import {
  type ChatActionOption,
  type Message,
} from "./types";
import { confirmationSupersedingHandlers } from "./confirmation-superseding";
import {
  chatActionRequestFromAction, chatHttpErrorDisplay, applyChatHttpErrorToMessages, settleAdmissionTransportReadiness,
  applyEmptyFinalFallback,
  chatStreamErrorText,
  consumeConfirmationActionOnMessages,
  hasActiveArtifactActionSet,
  hydrateMessagesFromApi,
  isFailedActionRetry,
  markComposerActionsInactive,
  messageStreamPresentation,
  messagesWithSavedDecisionState,
  settleOpenConfirmationsFromFinalPayload,
  standaloneStreamStatusVisible,
} from "./chat-message-projection";
import { openFeedbackDialogState, type ChatFeedbackDialogState } from "./feedback-dialog-state";
import FeedbackAsk from "../feedback/FeedbackAsk";
import { messageElementRegistrar } from "./transcript-element-refs";
import { usePendingBreakdownRecovery } from "./usePendingBreakdownRecovery";
import { retirePendingBreakdown } from "@/lib/pending-result-breakdown";
import { isGuestSimulationConversionRejection } from "@/lib/guest-conversion-recovery";
import { useGuestEntryError } from "@/lib/guest-entry-error";
import SidebarShell from "@/components/sidebar/SidebarShell";
import ChatShellMenuTrigger from "@/components/chat/ChatShellMenuTrigger";
import GuestSettingsMenu from "@/components/guest/GuestSettingsMenu";
import { useMobileShell } from "@/components/chat/useMobileShell";
import { memoryRecallsFromFinalPayload, useMemoryChrome } from "./memory-chrome";
import {
  isStarterSelectionMetadata,
  type GuestPendingSubmission,
  type SendOptions,
  type SendSelection,
} from "./chat-send-selection";
export {
  hydrateMessagesFromApi,
  latestInputActions,
  settleOpenConfirmationsFromFinalPayload,
} from "./chat-message-projection";
import {
  applyConfirmationActionEffects,
  confirmationActionEffectFromAction,
  consumeResultActionOnMessages,
  normalizeConfirmationHistory,
  settleConfirmationAfterActionTransportError,
  settleOpenConfirmationsAfterStreamError,
} from "./artifact-history";
import { randomId } from "@/lib/random-id";
import { SEND_BUSY_FALLBACK, SEND_GENERIC_FALLBACK, sendRefusal } from "@/lib/send-refusal";
import { useDailyCapNotice } from "./useDailyCapNotice";
import { useChatAccountBoundary } from "./useChatAccountBoundary";
import { authenticatedRequestHeaders, ChatAccountChangedError } from "@/lib/chat-auth-ownership";
import { useChatWorkspace, visibleShellView, workspaceChatAvailable, type ChatShellView } from "./ChatWorkspace";
import ConversationDeleteDialog from "./ConversationDeleteDialog";
import { useChatShellBridge, WorkspaceMain, workspaceComposerProps } from "./WorkspaceMain";
type View = ChatShellView;

const JUMP_TO_LATEST_THRESHOLD_PX = 240;
export function ChatHeaderHeading({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <h1 className="font-display pointer-events-auto min-w-0 flex-1 truncate text-left text-[17px] font-semibold tracking-tight text-black/80 dark:text-white/80 tablet:text-[18px]">
      {children}
    </h1>
  );
}
// ─── Component ────────────────────────────────────────────────────────────────
export default function ChatInterface() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const [account, setAccount] = useState<Awaited<
    ReturnType<typeof getMe>
  > | null>(null);
  const dailyCap = useDailyCapNotice(account?.user.id);
  const [profileState, setProfileState] = useState<ProfileState>("probing");
  const [expiredPublicAccountAccessEnabled, setExpiredPublicAccountAccessEnabled] =
    useState(false);
  const authenticatedUserIdRef = useRef<string | null>(null);
  const refreshAccount = useCallback(async (expectedUserId?: string) => {
    const nextAccount = await getMe(expectedUserId);
    if (nextAccount === null) return null;
    authenticatedUserIdRef.current = nextAccount.user.id;
    setAccount(nextAccount);
    const resolvedLanguage = nextAccount.user.language ?? i18n.language;
    if (resolvedLanguage && resolvedLanguage !== i18n.language) {
      await i18n.changeLanguage(resolvedLanguage);
    }
    setProfileState("established");
    return nextAccount;
  }, [i18n]);
  const { onProfileUpdated, greetingName } = useProfileUpdates(account, setAccount);
  const [messages, setMessages] = useState<Message[]>([]);
  // Long-lived handlers (the undo toast) need the current transcript, not
  // the render that created them.
  const latestMessagesRef = useRef<Message[]>([]);
  useEffect(() => {
    latestMessagesRef.current = messages;
  }, [messages]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const workspace = useChatWorkspace();
  const [shellView, setCurrentView] = useState<View>(() => workspace?.initialView ?? "chat");
  const currentView = visibleShellView(workspace, shellView);
  const { isSidebarOpen, setIsSidebarOpen, sidebarMode, handleSetSidebarMode, toggleSidebar } = useSidebarPreference(workspace?.id, account?.user.id);
  const mobileShell = useMobileShell();
  const [searchOverlayOpen, setSearchOverlayOpen] = useState(false);
  const [showChatOptions, setShowChatOptions] = useState(false);
  const [pendingHeaderDelete, setPendingHeaderDelete] = useState<KeyboardDeleteRequest | null>(null);
  const [isDeletingHeaderChat, setIsDeletingHeaderChat] = useState(false);
  const [headerRenameValue, setHeaderRenameValue] = useState("");
  const [isRenamingHeaderChat, setIsRenamingHeaderChat] = useState(false);
  const [isSavingHeaderRename, setIsSavingHeaderRename] = useState(false);
  const [isPinningHeaderChat, setIsPinningHeaderChat] = useState(false);
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [activityCausalClock] = useState(createConversationActivityCausalClock);
  const [activityTranscriptReadiness] = useState(createConversationActivityTranscriptReadiness);
  const {
    historyItems,
    historyActivityRevision,
    setHistoryItems,
    historyNextCursor,
    isLoadingMoreHistory,
    hasRequestedOlderHistory,
    historyLoadMoreError,
    loadHistoryPage,
    clearHistory,
    loadMoreHistory,
    refreshHistory,
    refreshHistoryForActivity,
  } = useRecentConversations({
    enabled: workspace?.chatAvailable !== false,
    guestExpiresAt: account?.guest?.expires_at,
    activityCausalClock,
  });
  const [guestSubmissionPending, setGuestSubmissionPending] = useState(false);
  const [isHydratingConversation, setIsHydratingConversation] = useState(false);
  const [showConversationRetrievalState, setShowConversationRetrievalState] =
    useState(false);
  const [failedConversationId, setFailedConversationId] = useState<string | null>(null);
  const { toast, showToast, hideToast } = useChatToast();
  const [isRecentsExpanded, setIsRecentsExpanded] = useState(true);
  const [feedbackState, setFeedbackState] = useState<ChatFeedbackDialogState>({ isOpen: false, type: "general" });
  const [isSidebarPreferenceModalOpen, setIsSidebarPreferenceModalOpen] =
    useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const latestActivitySentinelRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const postTurnHistoryRefreshTimersRef = useRef<number[]>([]);
  const activeConversationIdRef = useRef<string | null>(null);
  const hasAcceptedUserInputRef = useRef(Boolean(readReceiptFollowup()));
  const guestSendRef = useRef<GuestResumeSend | null>(null);
  const sendAdmissionInFlightRef = useRef(false);
  const guestSubmissionRetryRef = useRef<GuestPendingSubmission | null>(null);
  const guestEntry = useGuestEntryError(guestSubmissionRetryRef);
  const currentViewRef = useRef<View>("chat");
  const [transcriptSessionCache] = useState(
    () => new TranscriptSessionCache<SavedConversationTranscript>(),
  );
  const coldRetrievalTimerRef = useRef<number | null>(null);
  const coldRetrievalConversationIdRef = useRef<string | null>(null);
  const readyTranscriptConversationIdRef = useRef<string | null>(null);
  const pendingScrollRestoreRef = useRef<PendingScrollRestore>(null);
  const pendingMessageAnchorRef = useRef<PendingMessageAnchor>(null);
  const messageElementRefs = useRef(new Map<string, HTMLDivElement>());
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const canApplyConversationOwnedUpdate = useCallback(
    (targetConversationId?: string | null) =>
      shouldApplyConversationOwnedUpdate({
        targetConversationId,
        activeConversationId: activeConversationIdRef.current,
      }),
    [],
  );
  const invalidateTranscriptForMutation = useCallback(
    (targetConversationId: string, mutation: TranscriptMutation) => {
      const userId = account?.user.id;
      if (!userId) return;
      transcriptSessionCache.invalidateForMutation({
        userId,
        conversationId: targetConversationId,
        mutation,
      });
      if (
        readyTranscriptConversationIdRef.current === targetConversationId &&
        conversationActivityMutationRequiresCanonicalHydration(mutation)
      ) {
        clearConversationActivityTranscript(activityTranscriptReadiness, readyTranscriptConversationIdRef);
      }
    },
    [account?.user.id, activityTranscriptReadiness, transcriptSessionCache],
  );
  const conversationActivity = useConversationActivity({
    historyItems,
    historyActivityRevision,
    activeConversationId: currentView === "chat" ? conversationId : null,
    accountScopeKey: account?.user.id ?? null,
    refreshHistory: refreshHistoryForActivity,
    invalidateInactiveTranscript: (id) => invalidateTranscriptForMutation(id, "durable_job_completion"),
    onMutationNotice: (notice) => {
      const descriptor = conversationActivityMutationNoticeDescriptor(notice);
      showToast(t(descriptor.key, descriptor.defaultValue), descriptor.variant);
    },
    causalClock: activityCausalClock,
  });
  const recordLoadedTranscript = useConversationTranscriptFreshness({
    inputs: () => {
      const record = conversationActivity.state.byConversationId[conversationId ?? ""];
      return { accountId: account?.user.id ?? null, conversationId: currentView === "chat" ? conversationId : null, latestMessageId: record?.canonical?.latest_message_id ?? null, activityRevision: Math.max(historyActivityRevision, record?.serverRevision ?? 0), requestId: record?.request?.requestId ?? null, ready: !isHydratingConversation && readyTranscriptConversationIdRef.current === conversationId, visibleMessages: messages };
    },
    invalidate: (id) => invalidateTranscriptForMutation(id, "durable_job_completion"),
    readyTranscriptConversationIdRef, activityTranscriptReadiness, pendingScrollRestoreRef,
    scrollContainerRef, shouldAutoScrollRef, setMessages,
  });
  const [requestSessions] = useState(() =>
    createChatRequestSessionController({
      activity: conversationActivity,
      accountScopeKey: account?.user.id ?? null,
      routeContext: {
        activeConversationId: conversationId,
        currentView,
        routeState: readActiveConversationRouteState(),
      },
    }),
  );
  const isStreamingResponse = conversationActivity.isConversationLocked(conversationId);
  const visibleStreamStatus = visibleRequestStatus(streamStatus, isStreamingResponse);
  const handleDurableJobCompletion = useCallback((response: BacktestJobResponse) => {
      // A research answer rides the job response and is already projected
      // in place by the poller, like a run result; nothing here reloads.
      const targetConversationId = response.job.conversation_id;
      invalidateTranscriptForMutation(targetConversationId, "durable_job_completion");
      promoteCanonicalConversationActivityTranscript({ conversationId: targetConversationId, activeConversationIdRef, currentViewRef, readyTranscriptConversationIdRef, transcriptReadiness: activityTranscriptReadiness });
    }, [activityTranscriptReadiness, invalidateTranscriptForMutation]);
  useBacktestJobPolling(messages, canApplyConversationOwnedUpdate, setMessages, handleDurableJobCompletion);
  const handlePendingBreakdownSettled = useCallback((targetConversationId: string) => {
    invalidateTranscriptForMutation(targetConversationId, "durable_result_action");
    promoteCanonicalConversationActivityTranscript({ conversationId: targetConversationId, activeConversationIdRef, currentViewRef, readyTranscriptConversationIdRef, transcriptReadiness: activityTranscriptReadiness });
    void refreshHistory();
  }, [activityTranscriptReadiness, invalidateTranscriptForMutation, refreshHistory]);
  usePendingBreakdownRecovery(messages, conversationId, setMessages, t("chat.error_load"), handlePendingBreakdownSettled);

  const retireActiveTranscriptPresentationForNavigation = useCallback(() => {
    setStreamStatus(null);
  }, []);

  const clearColdTranscriptRetrieval = useCallback(() => {
    if (coldRetrievalTimerRef.current !== null) {
      window.clearTimeout(coldRetrievalTimerRef.current);
      coldRetrievalTimerRef.current = null;
    }
    coldRetrievalConversationIdRef.current = null;
    setShowConversationRetrievalState(false);
  }, []);

  const cancelTranscriptNavigation = useCallback(() => {
    transcriptSessionCache.cancelActiveNavigation();
    clearColdTranscriptRetrieval();
    pendingScrollRestoreRef.current = null;
    clearConversationActivityTranscript(activityTranscriptReadiness, readyTranscriptConversationIdRef);
    setFailedConversationId(null);
    setIsHydratingConversation(false);
  }, [activityTranscriptReadiness, clearColdTranscriptRetrieval, transcriptSessionCache]);

  useLayoutEffect(() => {
    requestSessions.synchronizeAccountScope(account?.user.id ?? null);
    requestSessions.updateRouteContext({
      activeConversationId: conversationId,
      currentView,
      routeState: readActiveConversationRouteState(),
    });
  }, [account?.user.id, conversationId, currentView, requestSessions]);

  useLayoutEffect(() => {
    synchronizeConversationViewRefs(activeConversationIdRef, currentViewRef, conversationId, currentView);
  }, [conversationId, currentView]);

  const resetToEmptyChatSurface = useCallback(
    (nextConversationId: string | null = null, view: View = "chat") => {
      cancelTranscriptNavigation();
      retireActiveTranscriptPresentationForNavigation();
      if (nextConversationId) {
        rememberActiveConversationId(nextConversationId);
      } else {
        const clearedRoute = clearActiveConversationPointer();
        if (clearedRoute) router.replace(clearedRoute, { scroll: false });
      }
      synchronizeConversationViewRefs(activeConversationIdRef, currentViewRef, nextConversationId, view);
      hasAcceptedUserInputRef.current = false;
      setConversationId(nextConversationId);
      setMessages([]);
      setStreamStatus(null);
      setIsHydratingConversation(false);
      setShowChatOptions(false);
      setIsRenamingHeaderChat(false);
      setHeaderRenameValue("");
      setCurrentView(view);
    },
    [
      cancelTranscriptNavigation,
      retireActiveTranscriptPresentationForNavigation,
      router,
    ],
  );

  const accountBoundary = useChatAccountBoundary(account?.user.id ?? null, requestSessions, () => {
    transcriptSessionCache.clearAuthenticatedState();
    guestSubmissionRetryRef.current = null;
    clearHistory();
    resetToEmptyChatSurface();
  });

  useLayoutEffect(() => {
    authenticatedUserIdRef.current = account?.user.id ?? null;
  }, [account?.user.id]);

  // ── History ────────────────────────────────────────────────────────────────

  function schedulePostTurnHistoryRefresh(
    targetConversationId?: string | null,
    isAccountCurrent: () => boolean = () => true,
  ) {
    let settled = false;

    const refreshAndCheckTitle = async () => {
      if (settled || !isAccountCurrent()) return;
      try {
        await loadHistoryPage(null, false);
        if (!targetConversationId) return;
        const { items } = await listConversations({ limit: 50, surface: workspace?.conversationSurface });
        const conversation = items.find(
          (item) => item.id === targetConversationId,
        );
        if (
          conversation?.title_source === "ai_generated" ||
          conversation?.title_source === "user_renamed"
        ) {
          settled = true;
          await loadHistoryPage(null, false);
        }
      } catch {
        // Title/sidebar refresh is fail-open; later scheduled attempts can still pick it up.
      }
    };

    for (const delay of POST_TURN_TITLE_REFRESH_DELAYS_MS) {
      const timerId = window.setTimeout(() => {
        void refreshAndCheckTitle().catch(() => undefined);
      }, delay);
      postTurnHistoryRefreshTimersRef.current.push(timerId);
    }
  }

  function finishRequestTransport(session: ChatRequestSession) {
    if (!requestSessions.finishTransport(session)) return false;
    schedulePostTurnHistoryRefresh(
      session.identity.conversationId,
      () => requestSessions.isAccountCurrent(session),
    );
    return true;
  }
  useEffect(
    () => () => {
      for (const timerId of postTurnHistoryRefreshTimersRef.current) {
        window.clearTimeout(timerId);
      }
      postTurnHistoryRefreshTimersRef.current = [];
      transcriptSessionCache.clearAuthenticatedState();
      if (coldRetrievalTimerRef.current !== null) {
        window.clearTimeout(coldRetrievalTimerRef.current);
      }
    },
    [transcriptSessionCache],
  );

  useEffect(() => {
    if (!isSidebarOpen) {
      setIsRecentsExpanded(false);
    }
  }, [isSidebarOpen]);

  const closeDrawer = mobileShell.closeDrawer;
  const closeTransientSidebar = useCallback(() => {
    // Navigating out of the drawer always dismisses it; the rail keeps its own
    // transient rule, which depends on the user's sidebar mode.
    closeDrawer();
    setIsSidebarOpen((currentOpen) =>
      sidebarOpenAfterTransientNavigation({
        currentOpen,
        mode: sidebarMode,
      }),
    );
  }, [closeDrawer, sidebarMode, setIsSidebarOpen]);
  const { bridge: shellBridge, profileSlot, setProfileSlot } = useChatShellBridge({ workspace, currentView, conversationId, isBelowTablet: mobileShell.isBelowTablet, sidebarCollapsed: !(mobileShell.isBelowTablet ? true : isSidebarOpen), resetToEmptyChatSurface, closeTransientSidebar });

  function rememberCurrentConversationScroll(): void {
    const currentConversationId = readyTranscriptConversationIdRef.current;
    const userId = account?.user.id;
    const container = scrollContainerRef.current;
    if (!currentConversationId || !userId || !container) return;
    transcriptSessionCache.rememberScroll({
      userId,
      conversationId: currentConversationId,
      scrollTop: container.scrollTop,
    });
  }

  function stageTranscriptSnapshot(
    targetConversationId: string,
    userId: string,
    snapshot: SavedConversationTranscript,
    scrollTopOverride?: number | null,
  ): void {
    clearColdTranscriptRetrieval();
    setFailedConversationId(null);
    setIsHydratingConversation(false);
    if (snapshot.messages.length === 0) {
      resetToEmptyChatSurface();
      return;
    }
    readyTranscriptConversationIdRef.current = targetConversationId;
    const scrollTop =
      scrollTopOverride === undefined
        ? transcriptSessionCache.readScroll({
            userId,
            conversationId: targetConversationId,
          })
        : scrollTopOverride;
    pendingScrollRestoreRef.current = {
      conversationId: targetConversationId,
      scrollTop,
    };
    shouldAutoScrollRef.current = scrollTop === null;
    recordLoadedTranscript(userId, targetConversationId, snapshot);
    setMessages(snapshot.messages);
  }

  function beginColdTranscriptRetrieval(targetConversationId: string): void {
    clearColdTranscriptRetrieval();
    clearConversationActivityTranscript(activityTranscriptReadiness, readyTranscriptConversationIdRef);
    pendingScrollRestoreRef.current = null;
    setFailedConversationId(null);
    setMessages([]);
    setIsHydratingConversation(true);
    coldRetrievalConversationIdRef.current = targetConversationId;
    coldRetrievalTimerRef.current = window.setTimeout(() => {
      if (
        coldRetrievalConversationIdRef.current === targetConversationId &&
        activeConversationIdRef.current === targetConversationId &&
        currentViewRef.current === "chat"
      ) {
        setShowConversationRetrievalState(true);
      }
    }, COLD_TRANSCRIPT_RETRIEVAL_DELAY_MS);
  }

  async function navigateConversationTranscript(
    targetConversationId: string,
    userId: string = account?.user.id ?? "",
    options: Readonly<{
      bootstrap?: boolean;
      messageId?: string;
      scrollToLatest?: boolean;
    }> = {},
  ): Promise<void> {
    if (!userId) return;
    rememberCurrentConversationScroll();
    retireActiveTranscriptPresentationForNavigation();
    rememberActiveConversationId(targetConversationId, options.messageId);
    activeConversationIdRef.current = targetConversationId;
    currentViewRef.current = "chat";
    setConversationId(targetConversationId);
    setCurrentView("chat");
    setStreamStatus(null);
    setShowChatOptions(false);

    if (options.messageId) {
      const requestedMessageId = options.messageId;
      transcriptSessionCache.cancelActiveNavigation();
      beginColdTranscriptRetrieval(targetConversationId);
      const isCurrentRequest = () =>
        isCurrentAnchoredConversationRequest({
          activeConversationId: activeConversationIdRef.current,
          targetConversationId,
          routeState: readActiveConversationRouteState(),
          requestedMessageId,
        });
      try {
        const snapshot = await loadSavedConversationTranscript(targetConversationId);
        if (!isCurrentRequest()) return;
        const anchorMessageId = projectedTranscriptAnchorId(snapshot.messages, requestedMessageId);
        if (!anchorMessageId) throw new Error("Transcript anchor was not returned.");
        clearColdTranscriptRetrieval();
        setIsHydratingConversation(false);
        readyTranscriptConversationIdRef.current = targetConversationId;
        activityTranscriptReadiness.stageCanonical(targetConversationId);
        pendingScrollRestoreRef.current = null;
        pendingMessageAnchorRef.current = {
          conversationId: targetConversationId,
          messageId: anchorMessageId,
        };
        shouldAutoScrollRef.current = false;
        recordLoadedTranscript(userId, targetConversationId, snapshot);
        setMessages(snapshot.messages);
      } catch (error) {
        if (!isCurrentRequest()) return;
        clearColdTranscriptRetrieval();
        setIsHydratingConversation(false);
        clearConversationActivityTranscript(activityTranscriptReadiness, readyTranscriptConversationIdRef);
        pendingMessageAnchorRef.current = null;
        setMessages([]);
        if (options.bootstrap && isMissingConversationLoadError(error)) {
          resetToEmptyChatSurface();
          return;
        }
        setFailedConversationId(targetConversationId);
      }
      return;
    }

    let renderedStaleSnapshot = false;
    const handle = transcriptSessionCache.navigate({
      userId,
      conversationId: targetConversationId,
      load: (signal) => loadSavedConversationTranscript(targetConversationId, signal),
      onState: (state: TranscriptNavigationState<SavedConversationTranscript>) => {
        if (state.phase === "loading") {
          beginColdTranscriptRetrieval(targetConversationId);
          return;
        }
        if (state.phase === "refreshing") {
          renderedStaleSnapshot = true;
          activityTranscriptReadiness.stageCached(targetConversationId);
          stageTranscriptSnapshot(
            targetConversationId,
            userId,
            state.snapshot,
            options.scrollToLatest ? null : undefined,
          );
          return;
        }
        if (state.phase === "ready") {
          const currentScrollTop = options.scrollToLatest
            ? null
            : renderedStaleSnapshot &&
                readyTranscriptConversationIdRef.current ===
                  targetConversationId
              ? (scrollContainerRef.current?.scrollTop ?? null)
              : undefined;
          activityTranscriptReadiness.stageCanonical(targetConversationId);
          stageTranscriptSnapshot(
            targetConversationId,
            userId,
            state.snapshot,
            currentScrollTop,
          );
          return;
        }

        clearColdTranscriptRetrieval();
        setIsHydratingConversation(false);
        if (state.snapshot !== null) {
          readyTranscriptConversationIdRef.current = targetConversationId;
          activityTranscriptReadiness.stageCached(targetConversationId);
          recordLoadedTranscript(userId, targetConversationId, state.snapshot);
          setMessages(state.snapshot.messages);
          return;
        }
        clearConversationActivityTranscript(activityTranscriptReadiness, readyTranscriptConversationIdRef);
        pendingScrollRestoreRef.current = null;
        setMessages([]);
        if (options.bootstrap && isMissingConversationLoadError(state.error)) {
          setHistoryItems((current) =>
            current.filter(
              (item) =>
                !historyItemBelongsToConversation(item, targetConversationId),
            ),
          );
          resetToEmptyChatSurface();
          return;
        }
        setFailedConversationId(targetConversationId);
      },
    });
    await handle.completion;
  }
  function beginConversationActivityTerminalReadiness(getRequest: () => ChatRequestSession) { const terminalReadiness = createConversationActivityTerminalReadinessSession({ getRequest: () => ({ conversationId: getRequest().identity.conversationId, kind: getRequest().kind }), activeConversationIdRef, currentViewRef, readyTranscriptConversationIdRef, transcriptReadiness: activityTranscriptReadiness, reconcileCanonical: (id) => void navigateConversationTranscript(id) }); terminalReadiness.stage(); return terminalReadiness; }
  // ── Init conversation ──────────────────────────────────────────────────────

  const initialRoutingSettled = useInitialChatSession({
    hasAcceptedUserInputRef,
    setAccount,
    setProfileState,
    setMessages,
    setIsHydratingConversation,
    resetToEmptyChatSurface: () => resetToEmptyChatSurface(null, workspace?.initialView),
    navigateConversationTranscript,
    cancelActiveNavigation: () => transcriptSessionCache.cancelActiveNavigation(),
  });

  const { scrollToLatest, updateScrollPositionState } = useChatScrollControls({
    accountUserId: account?.user.id,
    activeConversationIdRef,
    readyTranscriptConversationIdRef,
    bottomRef,
    scrollContainerRef,
    shouldAutoScrollRef,
    transcriptSessionCache,
    setShowJumpToLatest,
  });

  const { anchorToTurn } = useTranscriptTurnAnchor({
    conversationId,
    messages,
    jumpToLatestThresholdPx: JUMP_TO_LATEST_THRESHOLD_PX,
    activeConversationIdRef,
    pendingMessageAnchorRef,
    pendingScrollRestoreRef,
    messageElementRefs,
    scrollContainerRef,
    shouldAutoScrollRef,
    setShowJumpToLatest,
  });

  useConversationActivityViewport({
    activity: conversationActivity, accountScopeKey: account?.user.id ?? null,
    activeRouteConversationId: currentView === "chat" ? readActiveConversationRouteState().conversationId : null,
    activeConversationId: currentView === "chat" ? conversationId : null,
    activeConversationIdRef, readyTranscriptConversationIdRef,
    transcriptRootRef: scrollContainerRef, sentinelRef: latestActivitySentinelRef,
    transcriptReadiness: activityTranscriptReadiness,
    pendingScrollRestoreRef, pendingMessageAnchorRef,
    hydrationComplete: !isHydratingConversation,
  });

  useEffect(() => {
    executeChatTranscriptUpdateScroll({ shouldAutoScrollRef, scrollToLatest, updateScrollPositionState });
  }, [messages.length, scrollToLatest, streamStatus, updateScrollPositionState]);

  // ── Load existing conversation ─────────────────────────────────────────────

  const loadConversation = async (
    convId: string, messageId?: string, scrollToLatest = false,
  ) => {
    closeChatOptions();
    await navigateConversationTranscript(
      convId, undefined, { messageId, scrollToLatest },
    );
  };

  const loadConversationForRun = async (
    item: Pick<HistoryItem | SearchConversationItem, "id" | "conversation_id">,
  ) => {
    if (item.conversation_id) {
      void loadConversation(item.conversation_id);
      return;
    }
    try {
      const { run } = await getBacktestRun(item.id);
      if (run.conversation_id) {
        void loadConversation(run.conversation_id);
        return;
      }
    } catch {
      // Fall through to the chat surface if the run is unavailable.
    }
    setCurrentView("chat");
    closeTransientSidebar();
  };

  const openHistoryItem = (item: HistoryItem | SearchConversationItem) => {
    if (item.type === "chat") {
      void loadConversation(item.id);
      return;
    }
    if (item.type === "run") {
      void loadConversationForRun(item);
      return;
    }
    setCurrentView("chat");
    closeTransientSidebar();
  };

  // ── Start new chat ─────────────────────────────────────────────────────────

  const {
    startNewChat,
    adoptGuestConversation,
    handleConversationRemoved,
    handleAllConversationsDeleted,
  } = useChatSurfaceLifecycle({
    conversationId,
    setHistoryItems,
    resetToEmptyChatSurface,
    closeTransientSidebar,
    refreshHistory,
    onConversationRemoved: (removedConversationId) => {
      invalidateTranscriptForMutation(
        removedConversationId,
        "conversation_delete",
      );
    },
    onAllConversationsDeleted: () => {
      transcriptSessionCache.clearAuthenticatedState();
      clearConversationActivityTranscript(activityTranscriptReadiness, readyTranscriptConversationIdRef);
      pendingScrollRestoreRef.current = null;
    },
  });
  const archiveActiveConversation = useArchiveActiveConversation({
    conversationId, onArchived: handleConversationRemoved,
    onSuccess: () => showToast(t("common.archive", "Archive")), onError: () => showToast(t("common.error_occurred"), "error"),
  });
  const guestBootstrapRequired = profileState === "bootstrap_required";
  const guestExperience = useGuestExperience({
    account,
    guestBootstrapRequired,
    conversationId,
    messages,
    sendRef: guestSendRef,
    refreshAccount,
    refreshHistory,
    refreshHistoryForActivity,
    closeTransientSidebar,
    startNewChat,
    onOpenFeedback: () =>
      setFeedbackState({
        isOpen: true,
        type: "general",
        context: { surface: "guest_header", conversation_id: conversationId },
      }),
    // The one door into Omnisearch, so the drawer closes here rather than at
    // each caller. The palette paints below the drawer, and gating the shortcut
    // hook alone still left the guest shell's own key listener opening it into
    // a layer nobody can see.
    onOpenOmnisearch: () => {
      closeDrawer();
      setSearchOverlayOpen(true);
    },
    onRequestPendingGuestSignIn: () => router.push(currentAuthLoginPath()),
    onAdoptConversation: adoptGuestConversation,
    onGuestBootstrapExpired: (publicAccountAccessEnabled) => {
      guestEntry.resetGuestSubmissionError();
      setExpiredPublicAccountAccessEnabled(publicAccountAccessEnabled);
      setProfileState("expired");
    },
    onGuestBootstrapError: guestEntry.onGuestBootstrapError,
    onAuthenticationStart: accountBoundary.beginConversion,
    onAuthenticationComplete: accountBoundary.finishConversion,
    onGateError: () => showToast(t("chat.error_generic"), "error"),
    onStartOverError: () =>
      showToast(
        t(
          "guest.new_conversation.error",
          "The temporary chat was left unchanged.",
        ),
        "error",
      ),
    // The single owner of the Omnisearch shortcut; useChatKeyboardShortcuts
    // never claims it. Whether any surface is open is asked at press time
    // against the layer registry, rather than named here one surface at a
    // time: naming only the drawer left the same bug behind every other modal.
    // Withheld below the mobile threshold on the same rule as the rest of the
    // layer, so there is one answer to whether this width has shortcuts.
    omnisearchShortcutEnabled: omnisearchEnabled && !mobileShell.isBelowTablet && !workspace?.keyboardShortcuts,
  });
  const {
    isGuest,
    canManageConversation,
    canSaveDecision,
    canUseOmnisearch,
    canUseGroundedDiscovery,
    canSubmitFeedback,
    requestGuestDecision,
    requestGuestFeedback,
    requestGuestSearchUpgrade,
    requestGuestSignIn,
    requestNewChat,
    requestOmnisearch,
    recoverGuestSimulationRejection,
    resumeDecisionTarget,
    resumeDecisionArtifactId,
    resumeDecisionMessageId,
    clearResumeDecision,
  } = guestExperience;

  const memoryChrome = useMemoryChrome(isGuest, conversationId);

  const actionDisplayLabel = useCallback(
    (action: ChatActionOption) =>
      action.labelKey
        ? t(action.labelKey, {
            defaultValue: action.label,
            ...((action.payload ?? {}) as Record<string, unknown>),
          })
        : action.label,
    [t],
  );

  const handleMessageFeedback = useCallback(
    async (
      type: "bug" | "feature" | "general" | "rating",
      context: Record<string, unknown> | undefined,
      rating?: "positive" | "negative",
    ) => {
      if (type === "rating" && rating) {
        try {
          await postFeedback({
            type: "general",
            message: t("feedback.rating_message_fallback", { rating }),
            context: feedbackContextForSubmission(context, {
              includeConversationContext: true,
              rating,
              tags: [],
            }),
          });
        } catch {
          showToast(
            t(
              "feedback.error",
              "We could not submit that yet. Please try again.",
            ),
            "error",
          );
        }
        return;
      }

      setFeedbackState(
        openFeedbackDialogState(type, context, rating, conversationId),
      );
      setIsSidebarOpen(false);
    },
    [conversationId, showToast, t, setIsSidebarOpen],
  );

  // ── Send message ───────────────────────────────────────────────────────────
  const handleSend = async (
    text: string,
    mentionsOrAction?: SendSelection,
    actionArg?: ChatActionOption,
    options?: SendOptions,
  ) => {
    const trimmed = text.trim();
    let guestSubmissionHandedToStream = false;
    // Never decline a real message in silence; see lib/send-refusal.ts.
    const refuseSend = sendRefusal(showToast, t);
    if (!trimmed || !workspaceChatAvailable(workspace) || accountBoundary.invalidated.current || accountBoundary.conversionPending.current) return false;
    if (sendAdmissionInFlightRef.current || isStreamingResponse) {
      return false;
    }
    const mentions = Array.isArray(mentionsOrAction) ? mentionsOrAction : [];
    const starterSelection = isStarterSelectionMetadata(mentionsOrAction)
      ? mentionsOrAction
      : undefined;
    const action: ChatActionOption | undefined = Array.isArray(mentionsOrAction)
      ? actionArg
      : starterSelection
        ? undefined
        : (mentionsOrAction as ChatActionOption | undefined);
    const isDeferredGuestSubmission =
      guestBootstrapRequired && !options?.bypassGuestGate;
    sendAdmissionInFlightRef.current = true;
    if (isDeferredGuestSubmission) {
      guestSubmissionRetryRef.current = {
        text,
        mentionsOrAction,
        actionArg,
        options,
      };
      guestEntry.clearGuestSubmissionError();
      setGuestSubmissionPending(true);
      setStreamStatus(t("guest.entry.sending", "Sending..."));
    }

    try {
    if (
      !options?.bypassGuestGate &&
      !(await guestExperience.admitSend({
        text: trimmed,
        mentions,
        action,
        language: i18n.resolvedLanguage ?? i18n.language,
      }))
    ) {
      return false;
    }
    if (accountBoundary.invalidated.current || accountBoundary.conversionPending.current) return false;
    const expectedUserId = authenticatedUserIdRef.current;
    if (!expectedUserId) return false;
    try { await authenticatedRequestHeaders(expectedUserId); }
    catch (error) { if (error instanceof ChatAccountChangedError) accountBoundary.invalidate(); else showToast(t("chat.error_generic"), "error"); return false; }
    if (accountBoundary.invalidated.current || accountBoundary.conversionPending.current) return false;
    const ownedRequest = { expectedUserId, signal: accountBoundary.admission.current.signal };
    hasAcceptedUserInputRef.current = true;
    setIsHydratingConversation(false);
    const replacementAssistantId =
      options?.replacementAssistantId?.trim() || undefined;
    const routeState = readActiveConversationRouteState();
    let targetConversationId = targetConversationIdForSend({
      routeConversationId: routeState.conversationId,
      stateConversationId: conversationId,
      action,
    });
    const shouldCreateNewRouteConversation = Boolean(options?.startNewConversation) ||
      shouldStartConversationForVisibleEmptyChat({
        routeState,
        visibleMessageCount: messages.length,
        hasStructuredAction: Boolean(action?.type),
      });
    let shouldResetMessagesForNewConversation = false;

    if (shouldCreateNewRouteConversation || (!targetConversationId && !action?.type)) {
      try {
        const { conversation } = await createConversation(i18n.language, ownedRequest, workspace?.conversationSurface);
        if (accountBoundary.invalidated.current || accountBoundary.conversionPending.current) return false;
        targetConversationId = conversation.id;
        shouldResetMessagesForNewConversation = shouldCreateNewRouteConversation || messages.length === 0;
        rememberActiveConversationId(conversation.id);
        setConversationId(conversation.id);
        void refreshHistory();
      } catch (err) {
        if (err instanceof ChatAccountChangedError) { accountBoundary.invalidate(); return false; }
        console.error("Failed to start conversation before sending:", err);
        showToast(t("chat.error_generic"), "error");
        return false;
      }
    }

    if (!targetConversationId) {
      return refuseSend("chat.error_generic", SEND_GENERIC_FALLBACK);
    }
    if (conversationActivity.isConversationLocked(targetConversationId)) {
      return refuseSend("chat.send_busy", SEND_BUSY_FALLBACK);
    }
    const transcriptMutation: TranscriptMutation =
      action?.type === "retry_last_turn"
        ? "retry"
        : isFailedActionRetry(action)
          ? "recovery"
          : "message_send";
    if (!options?.keepLocalTranscript) {
      invalidateTranscriptForMutation(targetConversationId, transcriptMutation);
    }

    if (targetConversationId !== conversationId) {
      rememberActiveConversationId(targetConversationId);
      setConversationId(targetConversationId);
    }
    synchronizeConversationViewRefs(activeConversationIdRef, currentViewRef, targetConversationId, "chat");

    closeTransientSidebar();
    shouldAutoScrollRef.current = true;
    const renderUserMessage = options?.renderUserMessage ?? !isRetryAction(action);

    const userMsg: Message = {
      id: randomId(),
      role: "user",
      kind: action?.type ? "action" : "text",
      content: action?.type ? actionDisplayLabel(action) : trimmed,
      mentions,
      selectedAction: action,
      retestReceiptPending: action?.type === RETEST_ACTION_TYPE,
    };
    const assistantId = replacementAssistantId ?? randomId();
    const retryLastTurnAction = action?.type
      ? null
      : retryLastTurnActionFromMessage(trimmed, {
          assistantMessageId: assistantId,
        });

    setMessages((prev) => {
      const baseMessages = consumeConfirmationActionOnMessages(
        consumeResultActionOnMessages(
          markComposerActionsInactive(
            shouldResetMessagesForNewConversation ? [] : prev,
          ),
          action,
        ),
        action,
      );
      return appendOrReplacePendingAssistantMessage(baseMessages, {
        assistantId,
        pendingAssistant: {
          id: assistantId,
          role: "ai",
          kind: "text",
          content: "",
          contentPresentation:
            action?.type === "show_breakdown" ? "result_breakdown" : undefined,
        },
        userMessage: userMsg,
        renderUserMessage,
      });
    });
    if (!isDeferredGuestSubmission) setStreamStatus(null);

    const streamInput: string | ChatActionRequest = action?.type
      ? chatActionRequestFromAction(action)
      : trimmed;
    const requestKind =
      action?.type === "run_backtest" ? "backtest_job" : "chat_turn";
    const initialRequestSession = requestSessions.begin(
      targetConversationId,
      requestKind, options?.requestId,
    );
    if (!initialRequestSession) return refuseSend("chat.send_busy", SEND_BUSY_FALLBACK);
    guestSubmissionRetryRef.current = null;
    let requestSession: ChatRequestSession = initialRequestSession;
    const clearObservedDailyCap = dailyCap.captureSuccessClear();
    const terminalReadiness = beginConversationActivityTerminalReadiness(() => requestSession);
    const ordinaryTransportMessageIds =
      action?.type === "run_backtest"
        ? null
        : await snapshotOrdinaryTransportMessageIds(async () =>
            loadAllConversationMessagePages(targetConversationId),
          );

    const canApplyVisibleStreamUpdate = () =>
      requestSessions.canWriteVisible(requestSession);
    const clearNeutralGuestSubmission = () => { if (isDeferredGuestSubmission) setGuestSubmissionPending(false); };
    const recoverQuotaRejectedRun = (failureCode: unknown) => {
      if (!isGuestSimulationConversionRejection(failureCode, action) || !recoverGuestSimulationRejection(action)) return false;
      void loadConversation(requestSession.identity.conversationId);
      finishRequestTransport(requestSession);
      return true;
    };
    const handleStreamEvent = (event: ChatStreamEvent) => {
      if (event.event === "stage_start") {
        if (!requestSessions.authorize(requestSession, "stage")) return;
        conversationActivity.progressRequest(
          requestSession.identity.conversationId,
          requestSession.identity.requestId,
          "running",
        );
        clearNeutralGuestSubmission();
        if (!canApplyVisibleStreamUpdate()) return;
        setStreamStatus(toolProgressText(event.data.tool_progress ?? null, t));
      }
      if (event.event === "token") {
        if (!requestSessions.authorize(requestSession, "token")) return;
        setStreamStatus(null);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `${m.content ?? ""}${event.data.text}` }
              : m,
          ),
        );
      }
      if (event.event === "error") {
        if (!requestSessions.authorize(requestSession, "error")) return;
        clearNeutralGuestSubmission();
        const errorPayload = event.data as typeof event.data & Record<string, unknown>;
        if (recoverQuotaRejectedRun(errorPayload.code)) return;
        throwIfAmbiguousRunSseError(event, action?.type === "run_backtest");
        if (!canApplyVisibleStreamUpdate()) {
          finishRequestTransport(requestSession);
          return;
        }
        const persistedErrorMessageId = event.data.message_id?.trim();
        const errorRecoveryDisplay = recoveryDisplayFromMetadata(errorPayload);
        const errorStrategyPathContext = strategyPathContextFromMetadata(errorPayload);
        // Same gate the `final` frame applies: a retryable failure wears the
        const errorAssistantRecoveryCode = retryableAssistantRecoveryCode(
          errorPayload.recovery,
        );
        const durableRetry = durableRetryLastTurnFromStreamError(errorPayload);
        const durableRetryAction = durableRetry?.action ?? null;
        const visibleRetryAction = durableRetryAction
          ? (renderUserMessage ? null : durableRetryAction)
          : retryLastTurnActionFromMetadata(errorPayload, {
              assistantMessageId: persistedErrorMessageId,
              messageRole: "assistant",
            }) ??
          (retryLastTurnAction && persistedErrorMessageId
            ? retryLastTurnActionFromMessage(trimmed, {
                assistantMessageId: persistedErrorMessageId,
              })
            : retryLastTurnAction);
        setMessages((prev) =>
          normalizeDurableRetryActionHistory(
            settleOpenConfirmationsAfterStreamError(
              applyRetestReceipt(prev, userMsg.id, null).map((m) =>
                durableRetry && m.id === userMsg.id
                  ? {
                      ...m,
                      id: durableRetry.requestMessageId,
                      content: durableRetry.persistedMessage,
                      recoveryDisplay: errorRecoveryDisplay,
                      strategyPathContext: errorStrategyPathContext,
                      actions: [durableRetry.action],
                    }
                  : m.id === assistantId
                    ? {
                        ...m,
                        id: persistedErrorMessageId || m.id,
                        content: chatStreamErrorText(
                          event.data.detail,
                          t("chat.error_backtest"),
                        ),
                        recoveryDisplay: errorRecoveryDisplay,
                        strategyPathContext: errorStrategyPathContext,
                        assistantRecoveryCode: errorAssistantRecoveryCode,
                        actions:
                          visibleRetryAction
                            ? [visibleRetryAction]
                            : m.actions,
                      }
                    : m,
              ),
              action,
            ),
          ),
        );
        if (!terminalReadiness.accept({ message_id: event.data.message_id, recovery: event.data.recovery ?? null, retry_last_turn: event.data.retry_last_turn ?? null }, true)) terminalReadiness.finish(true);
        finishRequestTransport(requestSession);
      }
      if (event.event === "final") {
        // Ordinary sends passed compute admission; cancellation has its own handler.
        if (requestSession.kind === "chat_turn" && requestSessions.authorize(requestSession, "done")) clearObservedDailyCap();
        const identityAuthorized = requestSessions.authorize(requestSession, "final");
        if (!identityAuthorized) return;
        options?.onTerminal?.();
        clearNeutralGuestSubmission();
        setStreamStatus(null);
        if (recoverQuotaRejectedRun(event.data.final_response_payload?.code ?? event.data.code)) return;
        const finalPayload = event.data as typeof event.data & Record<string, unknown>;
        const finalText =
          event.data.assistant_response ?? event.data.assistant_prompt ?? "";
        const finalStageOutcome = event.data.stage_outcome;
        const finalMessageId =
          typeof finalPayload.message_id === "string"
            ? finalPayload.message_id
            : undefined;
        const finalAssistantId = finalMessageId ?? assistantId;
        setMessages((prev) =>
          applyRetestReceipt(retirePendingBreakdown(prev, requestSession.identity.requestId), userMsg.id, retestReceiptFromFinalPayload(finalPayload)),
        );
        const finalRecoveryDisplay = recoveryDisplayFromMetadata(finalPayload);
        const finalStrategyPathContext =
          strategyPathContextFromMetadata(finalPayload);
        const finalAssistantRecoveryCode = retryableAssistantRecoveryCode(
          finalPayload.recovery,
        );
        const finalDiscovery = discoverySidecarFromMetadata(finalPayload);
        const finalToolCards = toolCardsFromMetadata(finalPayload);
        const finalToolCardsUnavailable = hasUnavailableToolCards(finalPayload);
        const finalToolJobs = toolJobsFromMetadata(finalPayload);
        const finalMemoryRecalls = memoryRecallsFromFinalPayload(finalPayload);
        const finalNextExperiments =
          nextExperimentRowsFromMetadata(finalPayload) ?? undefined;
        const finalNextExperimentsSourceRunId =
          nextExperimentsSourceRunIdFromMetadata(finalPayload);
        const finalNextSteps = nextStepsFromMetadata(finalPayload, finalNextExperiments);
        const finalAnswerAssumptions = answerAssumptionsFromMetadata(finalPayload);
        const finalResponseActions = finalMessageId
          ? recoveryActionsFromMetadata(finalPayload, finalMessageId)
          : [];
        const finalRetryActions = [
          failedActionRetryActionFromMetadata(finalPayload),
          retryLastTurnActionFromMetadata(finalPayload, {
            assistantMessageId: finalMessageId,
          }),
        ].filter((retryAction): retryAction is ChatActionOption =>
          Boolean(retryAction),
        );
        const finalTextActions = [
          ...finalResponseActions,
          ...finalRetryActions,
        ];
        if (
          finalAssistantRecoveryCode &&
          !finalTextActions.some(isFailedActionRetry) &&
          text.trim()
        ) {
          const compositionRetry = retryLastTurnActionFromMessage(text, {
            assistantMessageId: finalMessageId ?? assistantId,
          });
          if (compositionRetry) finalTextActions.push(compositionRetry);
        }
        const finalHasFailedAction = hasFailedActionMetadata(finalPayload);
        const finalBacktestJob = backtestJobFromFinalPayload(finalPayload);
        const confirmation = pendingArtifactCardFromPayload(event.data.confirmation);
        if (confirmation) {
          // Researched peer adds ride the ordinary Try-next surface below
          // the card's turn (research rail, spec section 6).
          setMessages((prev) =>
            normalizeDurableRetryActionHistory(
              normalizeConfirmationHistory(
                replaceOrAppendFinalAssistantMessage(prev, assistantId, {
                  id: finalAssistantId,
                  role: "ai",
                  kind: "strategy_confirmation",
                  toolResultCards: finalToolCards, hasUnavailableToolResults: finalToolCardsUnavailable, toolJobs: finalToolJobs,
                  content: undefined,
                  confirmation,
                  strategyPathContext: finalStrategyPathContext,
                  actions: confirmation.actions ?? [],
                  nextExperiments: finalNextExperiments,
                }),
              ),
            ),
          );
        } else if (event.data.run) {
          const run = event.data.run as BacktestRun;
          const baseCard = resultCardFromRun(run);
          const resultActions = hydrateResultActionsForRun(
            baseCard.actions ?? [],
            run,
          );
          const card = {
            ...baseCard,
            readoutContent: resultReadoutContentFromMetadata(finalPayload, baseCard.readoutContent),
            savedStrategyId: run.strategy_id ?? null,
            actions: resultActions,
          };
          setMessages((prev) =>
            normalizeDurableRetryActionHistory(
              normalizeConfirmationHistory(
                replaceOrAppendFinalAssistantMessage(prev, assistantId, {
                  id: finalAssistantId,
                  role: "ai",
                  kind: "strategy_result",
                  toolResultCards: finalToolCards, hasUnavailableToolResults: finalToolCardsUnavailable, toolJobs: finalToolJobs,
                  content: finalText || undefined,
                  result: card,
                  actions: resultActions,
                  nextExperiments: finalNextExperiments,
                  savedStrategyId: card.savedStrategyId,
                  memoryRecalls: finalMemoryRecalls,
                }),
              ),
            ),
          );
        } else if (finalBacktestJob) {
          const finalBacktestJobMessage = { ...backtestJobMessage({
            id: finalAssistantId,
            content: finalText || undefined,
            job: finalBacktestJob,
            metadata: finalPayload,
          }), toolResultCards: finalToolCards, hasUnavailableToolResults: finalToolCardsUnavailable, toolJobs: finalToolJobs };
          setMessages((prev) =>
            normalizeDurableRetryActionHistory(
              normalizeConfirmationHistory(
                applyBacktestJobUpdate(
                  replaceOrAppendFinalAssistantMessage(
                    prev,
                    assistantId,
                    finalBacktestJobMessage,
                  ),
                  { job: finalBacktestJob, run: null },
                ),
              ),
            ),
          );
        } else if (finalText || finalToolCards.length || finalToolCardsUnavailable || finalToolJobs.length) {
          const finalResearchSources = researchSourcesForFinalPayload(finalPayload);
          const finalResearchDegradedCode =
            researchDegradedCodeFromMetadata(finalPayload);
          const finalTextPresentation =
            finalPayload.artifact_presentation_kind === "result" ? "result_readout"
              : finalRecoveryDisplay?.kind === "result_breakdown" || action?.type === "show_breakdown" ? "result_breakdown" : undefined;
          setMessages((prev) => {
            const nextMessages = replaceOrAppendFinalAssistantMessage(
              prev.map((m) =>
                mergeFinalTextMessage(m, {
                  assistantId,
                  finalText,
                  toolResultCards: finalToolCards,
                  finalActions: finalTextActions,
                  recoveryDisplay: finalRecoveryDisplay,
                  strategyPathContext: finalStrategyPathContext,
                  assistantRecoveryCode: finalAssistantRecoveryCode,
                  discovery: finalDiscovery,
                  memoryRecalls: finalMemoryRecalls,
                  researchSources: finalResearchSources,
                  researchDegradedCode: finalResearchDegradedCode,
                  nextExperiments: finalNextExperiments,
                  resultReadoutFacts: resultReadoutFacts(finalPayload.result_fact_bank),
                  resultReadoutContent: resultReadoutContentFromMetadata(finalPayload),
                  nextExperimentsSourceRunId: finalNextExperimentsSourceRunId,
                  nextSteps: finalNextSteps,
                  answerAssumptions: finalAnswerAssumptions,
                  contentPresentation: finalTextPresentation,
                }),
              ),
              assistantId,
              {
                id: finalAssistantId,
                role: "ai",
                kind: "text",
                content: finalText,
                toolResultCards: finalToolCards, hasUnavailableToolResults: finalToolCardsUnavailable, toolJobs: finalToolJobs,
                actions:
                  finalTextActions.length > 0 ? finalTextActions : undefined,
                recoveryDisplay: finalRecoveryDisplay,
                strategyPathContext: finalStrategyPathContext,
                assistantRecoveryCode: finalAssistantRecoveryCode,
                discovery: finalDiscovery,
                memoryRecalls: finalMemoryRecalls,
                researchSources: finalResearchSources,
                researchDegradedCode: finalResearchDegradedCode,
                nextExperiments: finalNextExperiments,
                resultReadoutFacts: resultReadoutFacts(finalPayload.result_fact_bank),
                resultReadoutContent: resultReadoutContentFromMetadata(finalPayload),
                nextExperimentsSourceRunId: finalNextExperimentsSourceRunId,
                nextSteps: finalNextSteps,
                answerAssumptions: finalAnswerAssumptions,
                contentPresentation: finalTextPresentation,
              },
            );
            if (
              isConfirmationAction(action) ||
              finalStageOutcome === "await_user_reply" ||
              finalStageOutcome === "needs_clarification"
            ) {
              return normalizeDurableRetryActionHistory(
                settleOpenConfirmationsFromFinalPayload(
                  nextMessages,
                  finalPayload,
                  {
                    action,
                    finalActions: finalTextActions,
                    hasFailedAction: finalHasFailedAction,
                  },
                ),
              );
            }
            return normalizeDurableRetryActionHistory(nextMessages);
          });
        } else if (!chatFinalPayloadOwnsVisibleTerminalArtifact(finalPayload)) {
          // A final that owns no visible artifact must still yield a visible
          // turn; card-state settles (a cancelled confirmation, a persisted
          // outcome) own theirs and never reach this fallback.
          setMessages((prev) =>
            applyEmptyFinalFallback(prev, {
              assistantId,
              finalMessageId,
              content: t("chat.error_backtest"),
              finalActions: finalTextActions,
              recoveryDisplay: finalRecoveryDisplay,
              strategyPathContext: finalStrategyPathContext,
              assistantRecoveryCode: finalAssistantRecoveryCode,
              discovery: finalDiscovery,
              memoryRecalls: finalMemoryRecalls,
              finalPayload,
              action,
              hasFailedAction: finalHasFailedAction,
            }),
          );
        }
        terminalReadiness.accept(event.data, identityAuthorized);
      }
      if (event.event === "title") {
        if (
          !requestSessions.authorize(
            requestSession,
            "title",
            event.data.conversation_id,
          )
        ) return;
        setHistoryItems((prev) =>
          prev.map((item) =>
            item.id === requestSession.identity.conversationId
              ? { ...item, title: event.data.title }
              : item,
          ),
        );
      }
      if (event.event === "done") {
        if (!requestSessions.authorize(requestSession, "done")) return;
        clearNeutralGuestSubmission();
        setMessages((prev) => applyRetestReceipt(prev, userMsg.id, null));
        terminalReadiness.finish(true); finishRequestTransport(requestSession);
      }
    };
    const moveRequestToConversation = (nextConversationId: string) => {
      const transferred = requestSessions.transfer(
        requestSession,
        nextConversationId,
      );
      if (!transferred) return false;
      requestSession = transferred;
      return true;
    };
    const streamToConversation = async (nextTargetConversationId: string) => {
      let runStreamFinalSeen = false;
      await streamChatMessage(
        nextTargetConversationId,
        streamInput,
        i18n.language,
        (event) => {
          runStreamFinalSeen ||= event.event === "final";
          handleStreamEvent(event);
        },
        // Discovery selections retain their resolver identity; other action
        // turns drop composer mentions.
        action?.type && action.type !== "select_discovery_candidate"
          ? []
          : mentions,
        {
          expectedUserId,
          requestId: requestSession.identity.requestId,
          signal: requestSession.controller.signal,
          failedAssistantId: replacementAssistantId,
        },
      );
      throwIfAmbiguousRunStreamTermination(
        action?.type === "run_backtest",
        runStreamFinalSeen,
      );
    };

    guestSubmissionHandedToStream = true;
    const transport = (async () => {
      try {
        await streamToConversation(targetConversationId);
      } catch (err: unknown) {
        if (err instanceof ChatAccountChangedError) { accountBoundary.invalidate(); return; }
        if (!requestSessions.authorize(requestSession, "catch")) return;
        if (
          err instanceof ChatStreamError &&
          err.status === 404 &&
          !action?.type && !options?.awaitCompletion
        ) {
          try {
            const retryWasVisible = canApplyVisibleStreamUpdate();
            if (retryWasVisible) clearActiveConversationPointer();
            const { conversation } = await createConversation(i18n.language, ownedRequest, workspace?.conversationSurface);
            if (accountBoundary.invalidated.current || accountBoundary.conversionPending.current) return;
            if (!moveRequestToConversation(conversation.id)) return;
            if (retryWasVisible) {
              rememberActiveConversationId(conversation.id);
              activeConversationIdRef.current = conversation.id;
              setConversationId(conversation.id);
            }
            await streamToConversation(conversation.id);
            return;
          } catch (retryErr) {
            err = retryErr;
          }
        }
        if (err instanceof ChatAccountChangedError) { accountBoundary.invalidate(); return; }
        clearNeutralGuestSubmission();
        const isOrdinaryTransportAmbiguity =
          action?.type !== "run_backtest" &&
          (!(err instanceof ChatStreamError) || err.status === 0);
        if (isOrdinaryTransportAmbiguity) {
          if (!requestSessions.authorize(requestSession, "ambiguity")) return;
          conversationActivity.progressRequest(
            requestSession.identity.conversationId,
            requestSession.identity.requestId,
            "checking",
          );
          if (canApplyVisibleStreamUpdate()) {
            setStreamStatus(t("chat.status.checking"));
          }
          const view = await resolveOrdinaryTransportAmbiguityView(
            async () =>
              loadAllConversationMessagePages(requestSession.identity.conversationId),
            hydrateMessagesFromApi,
            {
              assistantId,
              message: conversationLoadFailureMessage(
                requestSession.identity.conversationId,
                t("chat.error_load"),
              ),
            },
            ordinaryTransportMessageIds,
            err instanceof ChatStreamError ? err.requestId : null,
            { signal: requestSession.controller.signal },
          );
          if (requestSessions.authorize(requestSession, "ambiguity")) {
            if (canApplyVisibleStreamUpdate()) {
              setMessages((current) => settleRetestReceiptProjection(view.messages, current, userMsg.id));
            }
            terminalReadiness.finish(true);
            finishRequestTransport(requestSession);
          }
          return;
        }
        const confirmationId = ambiguousRunConfirmationId(action, err);
        if (confirmationId) {
          if (!requestSessions.authorize(requestSession, "run_replay")) return;
          conversationActivity.progressRequest(
            requestSession.identity.conversationId,
            requestSession.identity.requestId,
            "checking",
          );
          if (canApplyVisibleStreamUpdate()) {
            setStreamStatus(t("chat.status.checking"));
            setMessages((prev) =>
              settleConfirmationAfterActionTransportError(prev, action, {
                durableStateUnknown: true,
              }),
            );
          }
          const reconciliation = await reconcileAmbiguousRunResponse({
            lookup: () => getBacktestJobByAction(confirmationId),
            replay: () =>
              streamToConversation(requestSession.identity.conversationId),
          });
          if (!requestSessions.authorize(requestSession, "run_replay")) return;
          if (reconciliation.kind === "replayed") return;
          if (reconciliation.kind === "durable") {
            if (canApplyVisibleStreamUpdate()) {
              setMessages((prev) =>
                normalizeDurableRetryActionHistory(
                  normalizeConfirmationHistory(
                    applyReconciledBacktestJobResponse(
                      prev,
                      reconciliation.response,
                      assistantId,
                    ),
                  ),
                ),
              );
            }
            terminalReadiness.finish(true);
            finishRequestTransport(requestSession);
            return;
          }
          if (reconciliation.kind === "recoverable") {
            if (canApplyVisibleStreamUpdate()) {
              setMessages((prev) =>
                applyRecoverableRunReconciliation(
                  prev,
                  assistantId,
                  requestSession.identity.conversationId,
                  reconciliation.error,
                ),
              );
            }
            terminalReadiness.finish(true);
            finishRequestTransport(requestSession);
            return;
          }
        }
        if (!requestSessions.authorize(requestSession, "catch")) return;
        const canApplyVisibleUpdate = canApplyVisibleStreamUpdate();
        const status = (err as { status?: number }).status ?? 0;
        const rejectionCode = err instanceof ChatStreamError ? err.code : null;
        const fallbackMessage =
          err instanceof ChatStreamError && err.message
            ? err.message
            : t("chat.error_backtest");
        const httpErrorDisplay = chatHttpErrorDisplay(rejectionCode, fallbackMessage, {
          status, retryAfter: err instanceof ChatStreamError ? err.retryAfter : null,
        });
        dailyCap.record(httpErrorDisplay.recoveryDisplay);
        if (canApplyVisibleUpdate) {
          setMessages((prev) =>
            normalizeDurableRetryActionHistory(
              settleConfirmationAfterActionTransportError(
                applyChatHttpErrorToMessages(
                  applyRetestReceipt(prev, userMsg.id, null), httpErrorDisplay,
                  { code: rejectionCode, retryAfterHeader: err instanceof ChatStreamError ? err.retryAfter : null, retryAction: retryLastTurnAction, message: trimmed, assistantMessageId: assistantId },
                ),
                action,
                { rejectionCode },
              ),
            ),
          );
        }
        settleAdmissionTransportReadiness(terminalReadiness, httpErrorDisplay.recoveryDisplay, assistantId, requestSessions.authorize(requestSession, "catch"));
        finishRequestTransport(requestSession);
      }
    })();
    return options?.awaitCompletion ? transport.then(() => true) : true;
    } finally {
      sendAdmissionInFlightRef.current = false;
      if (isDeferredGuestSubmission && !guestSubmissionHandedToStream) {
        setGuestSubmissionPending(false);
        setStreamStatus(null);
      }
    }
  };

  const retryGuestSubmission = () => {
    const pending = guestSubmissionRetryRef.current;
    if (!pending) return;
    void handleSend(
      pending.text,
      pending.mentionsOrAction,
      pending.actionArg,
      pending.options,
    );
  };

  useGuestSendBridge(guestSendRef, handleSend);
  const receiptFollowup = useReceiptFollowup({ profileState, account, conversationId, hydrating: isHydratingConversation, guest: guestExperience, refreshAccount, navigate: navigateConversationTranscript, send: (text, options) => handleSend(text, undefined, undefined, options) });
  // ── Action routing ─────────────────────────────────────────────────────────

  const handleLogout = async (options: LogoutOptions = {}) => {
    if (options.afterAccountDeletion) return endSessionKeepingSurface(accountBoundary);
    await leaveSession({
      boundary: accountBoundary,
      currentUserId: account?.user.id ?? null,
      signOut: () => (options.sessionEnded ? Promise.resolve(null) : logoutFromApi()),
      clearLocalState: () => {
        requestSessions.synchronizeAccountScope(null);
        dailyCap.clear();
        setAccount(null);
        transcriptSessionCache.clearAuthenticatedState();
        resetToEmptyChatSurface();
        clearHistory();
      },
      navigate: (href) => { window.location.href = href; },
      onFailed: () => showToast(t("settings.logout_error", "We couldn’t sign out this browser. Try again."), "error"),
      businessBuild: businessPilotEnabled,
      accountDeleted: Boolean(options.sessionEnded),
    });
  };

  const handleCancelConfirmationAction = async (action: ChatActionOption) => {
    if (!account?.user.id || accountBoundary.invalidated.current || accountBoundary.conversionPending.current) return;
    const routeState = readActiveConversationRouteState();
    const targetConversationId = targetConversationIdForSend({
      routeConversationId: routeState.conversationId,
      stateConversationId: conversationId,
      action,
    });
    if (!targetConversationId) return;
    invalidateTranscriptForMutation(targetConversationId, "message_send");
    if (targetConversationId !== conversationId) {
      rememberActiveConversationId(targetConversationId);
      synchronizeConversationViewRefs(activeConversationIdRef, currentViewRef, targetConversationId, "chat");
      setConversationId(targetConversationId);
    }
    const effect = confirmationActionEffectFromAction(action);
    if (!effect) return;
    const streamInput: ChatActionRequest = {
      type: "cancel_confirmation",
      label: action.label,
      labelKey: action.labelKey,
      payload: action.payload,
      presentation: action.presentation,
    };
    const request = requestSessions.begin(targetConversationId, "chat_turn");
    if (!request) return;
    const terminalReadiness = beginConversationActivityTerminalReadiness(() => request);

    setStreamStatus(null);
    try {
      await streamChatMessage(
        targetConversationId,
        streamInput,
        i18n.language,
        (event) => {
          if (event.event === "stage_start") {
            if (!requestSessions.authorize(request, "stage")) return;
            conversationActivity.progressRequest(request.identity.conversationId, request.identity.requestId, "running");
          }
          if (event.event === "final") {
            const identityAuthorized = requestSessions.authorize(request, "cancel");
            if (!identityAuthorized) return;
            setMessages((prev) =>
              applyConfirmationActionEffects(
                markComposerActionsInactive(prev),
                [effect],
              ),
            );
            terminalReadiness.accept(event.data, identityAuthorized);
          }
          if (event.event === "error") {
            if (!requestSessions.authorize(request, "error")) return;
            if (requestSessions.canWriteVisible(request)) {
              showToast(
                chatStreamErrorText(event.data.detail, t("chat.error_generic")),
                "error",
              );
            }
            terminalReadiness.finish(true);
            finishRequestTransport(request);
          }
          if (event.event === "done") {
            if (!requestSessions.authorize(request, "done")) return;
            terminalReadiness.finish(true);
            finishRequestTransport(request);
          }
        },
        [],
        {
          expectedUserId: account.user.id,
          requestId: request.identity.requestId,
          signal: request.controller.signal,
        },
      );
    } catch (err: unknown) {
      if (err instanceof ChatAccountChangedError) { accountBoundary.invalidate(); return; }
      if (!requestSessions.authorize(request, "catch")) return;
      const message =
        err instanceof ChatStreamError && err.message
          ? err.message
          : t("chat.error_generic");
      if (requestSessions.canWriteVisible(request)) showToast(message, "error");
      terminalReadiness.finish(true);
      finishRequestTransport(request);
    }
  };

  const handleAction = (action: ChatActionOption) => {
    const value = action.value ?? "";
    if (action.type === "cancel_confirmation") {
      void handleCancelConfirmationAction(action);
      return;
    }
    if (action.type === "add_confirmation_peer") {
      // No turn is spent: the typed endpoint patches the pending card
      // deterministically and returns the superseding card message.
      void handleAddConfirmationPeer(action);
      return;
    }
    if (value === "/action:new-chat") {
      requestNewChat();
      return;
    }
    if (action.type === "retry_last_turn") {
      const retryText = retryLastTurnMessageFromAction(action);
      const retryChatAction = retryLastTurnChatActionFromAction(action);
      const failedAssistantId =
        retryLastTurnFailedAssistantIdFromAction(action);
      const requestMessageId = retryLastTurnRequestMessageIdFromAction(action);
      // A replayed discovery selection has to carry its identity too, or the
      // retry sends bare chip text and reintroduces the asset re-derivation
      // this lane fixes. The persisted chat_action still holds the payload.
      const retryMention = retryChatAction
        ? discoveryCandidateMention(retryChatAction)
        : null;
      if (retryText) {
        void handleSend(
          retryText,
          retryMention ? [retryMention] : (retryChatAction ?? []),
          retryMention ? (retryChatAction ?? undefined) : undefined,
          retryLastTurnSendOptions({ failedAssistantId, requestMessageId }),
        );
      }
      return;
    }
    if (action.type === "retry_load_conversation") {
      const retryConversationId = retryLoadConversationIdFromAction(action);
      if (retryConversationId) {
        void loadConversation(retryConversationId);
      }
      return;
    }
    if (isFailedActionRetry(action)) {
      void handleSend(action.label || value, action);
      return;
    }
    const discoveryMention = discoveryCandidateMention(action);
    if (discoveryMention) {
      void handleSend(action.label || value, [discoveryMention], action);
      return;
    }
    void handleSend(action.label || value, action.type ? action : undefined);
  };

  const {
    handleAddConfirmationPeer,
    handleDirectEditConfirmation,
  } = confirmationSupersedingHandlers(() => ({
    activeConversationId: () => activeConversationIdRef.current,
    // Through the ref: the undo toast outlives its render.
    activeConfirmationId: () => activeConfirmationIdFrom(latestMessagesRef.current),
    hydrate: (created) => hydrateMessagesFromApi(created),
    setMessages,
    showToast,
    hideToast,
    t,
  }));

  const handleToolRecompute = toolResultRecomputeHandler(() => ({
    source: () => ({ conversationId: activeConversationIdRef.current, latestMessageId: latestMessagesRef.current.at(-1)?.id, busy: sendAdmissionInFlightRef.current || conversationActivity.isConversationLocked(activeConversationIdRef.current) }),
    setMessages, invalidate: (id) => invalidateTranscriptForMutation(id, "durable_result_action"), reload: loadConversation,
  }));

  const omnisearch = omnisearchActionHandlers(() => ({
    closeOverlay: () => setSearchOverlayOpen(false),
    loadConversation, startNewChat, requestNewChat,
    guestGate: () => ({ accountKind: isGuest ? "guest" : "registered", hasAcceptedContent: messages.some((message) => message.role === "user") }),
    send: handleSend,
    isSourceConversationReady: (id) =>
      activeConversationIdRef.current === id &&
      readyTranscriptConversationIdRef.current === id,
  }));

  // ── Chat options helpers ───────────────────────────────────────────────────

  const closeChatOptions = useCallback(() => {
    setShowChatOptions(false);
    setIsRenamingHeaderChat(false);
  }, []);

  const activeHistoryChat = useMemo(
    () =>
      conversationId
        ? (historyItems.find(
            (item) =>
              item.type === "chat" &&
              historyItemBelongsToConversation(item, conversationId),
          ) ?? null)
        : null,
    [conversationId, historyItems],
  );

  const {
    activeTitleRecord,
    headerConversationTitle,
    headerConversationTitleSource,
  } = useActiveConversationTitle({
    conversationId,
    activeHistoryChat,
    messageCount: messages.length,
    isStreamingResponse,
    isChatViewActive: currentView === "chat",
    placeholder: t("chat.new_chat", "New chat"),
  });

  const handleStartHeaderRename = () => {
    if (!conversationId) return;
    setHeaderRenameValue(renamePrefillTitle(activeTitleRecord));
    setIsRenamingHeaderChat(true);
  };
  const handleSaveHeaderRename = async () => {
    if (!conversationId || isSavingHeaderRename) return;
    const nextTitle = headerRenameValue.trim();
    if (!nextTitle) {
      setIsRenamingHeaderChat(false);
      return;
    }
    setIsSavingHeaderRename(true);
    try {
      await patchConversation(conversationId, { title: nextTitle });
      invalidateTranscriptForMutation(conversationId, "conversation_rename");
      refreshHistory();
      showToast(t("common.save"));
      closeChatOptions();
    } catch {
      showToast(t("chat.rename_failed"), "error");
    } finally {
      setIsSavingHeaderRename(false);
    }
  };

  const handleToggleHeaderPin = async () => {
    if (!conversationId || isPinningHeaderChat) return;
    setIsPinningHeaderChat(true);
    try {
      await patchConversation(conversationId, {
        pinned: !Boolean(activeHistoryChat?.pinned),
      });
      refreshHistory();
      closeChatOptions();
    } catch {
      showToast(t("common.error_occurred"), "error");
    } finally {
      setIsPinningHeaderChat(false);
    }
  };

  const handleRequestHeaderDelete = (fromKeyboardShortcut = false) => {
    if (!conversationId) return;
    setPendingHeaderDelete({ conversationId, showKeyboardHints: fromKeyboardShortcut });
    closeChatOptions();
  };
  const handleConfirmHeaderDelete = async () => {
    if (!pendingHeaderDelete || isDeletingHeaderChat) return;
    setIsDeletingHeaderChat(true);
    try {
      await deleteConversation(pendingHeaderDelete.conversationId);
      showToast(t("common.delete"));
      handleConversationRemoved(pendingHeaderDelete.conversationId);
    } catch {
      showToast(t("common.error_occurred"), "error");
    } finally {
      setIsDeletingHeaderChat(false);
      setPendingHeaderDelete(null);
    }
  };
  // One in-flight lock for every way to start a turn. The composer already
  // disables itself while a turn runs; persistent discovery rows have to obey
  // the same lock or they become a way to spam turns around it.
  const turnInFlight =
    Boolean(visibleStreamStatus) ||
    isStreamingResponse ||
    isHydratingConversation ||
    guestSubmissionPending;
  // Next-move rows render under their owning message instead of a floating
  // strip above the composer, but they keep every gate the strip applied:
  // nothing offers a next move mid-turn, or while an active card already owns
  // the conversation's actions.
  const nextMovesEnabled =
    !turnInFlight && !hasActiveArtifactActionSet(messages);
  const showStreamStatus = standaloneStreamStatusVisible(messages, Boolean(visibleStreamStatus));
  const showConversationDisclaimer = shouldShowConversationDisclaimer(
    messages,
    isStreamingResponse,
  );
  // Spec 10b: both empty-state placeholders carry the same invitation once the
  // rail ships; the pre-rail strings stay behind the flag so flag-off behavior
  // is unchanged. The follow-up placeholder is deliberately untouched.
  const chatInputPlaceholder =
    messages.length === 0
      ? t(
          isGuest
            ? researchRailEnabled
              ? "guest.shell.input_placeholder"
              : "guest.shell.input_placeholder_prerail"
            : researchRailEnabled
              ? "chat.input_placeholder"
              : "chat.input_placeholder_prerail",
        )
      : t("chat.followup_placeholder", "Ask a follow-up...");
  const hasConversationLoadFailure =
    failedConversationId !== null && failedConversationId === conversationId;
  const showEmptyChatSurface = shouldShowEmptyChatSurface({
    messages,
    isHydratingConversation,
    hasConversationLoadFailure,
  });
  const conversationComposerUnavailable = Boolean(readReceiptFollowup()) ||
    isStreamingResponse ||
    isHydratingConversation ||
    guestSubmissionPending ||
    hasConversationLoadFailure;

  const keyboardShortcuts = useChatKeyboardShortcuts({
    enabled: !mobileShell.isBelowTablet,
    requestSearch: omnisearchEnabled ? () => setSearchOverlayOpen(true) : undefined,
    isChatView: currentView === "chat",
    canManageConversation,
    conversationId,
    isGuest,
    searchOverlayOpen,
    deleteConfirmationOpen: Boolean(pendingHeaderDelete),
    // The drawer is a modal too. Left out, its shortcuts still fired, and
    // Recents Quick Peek opened at z-65 behind a z-68 drawer: a real modal
    // nobody could see, reachable only by keyboard or switch control.
    modalOpen:
      isSidebarPreferenceModalOpen ||
      feedbackState.isOpen ||
      showChatOptions ||
      mobileShell.isDrawerOpen,
    sidebarOpen: isSidebarOpen,
    setSidebarOpen: setIsSidebarOpen,
    recentsExpanded: isRecentsExpanded,
    setRecentsExpanded: setIsRecentsExpanded,
    requestNewChat,
    closeTransientSidebar,
    requestDelete: () => handleRequestHeaderDelete(true),
    startRename: handleStartHeaderRename,
    archiveConversation: archiveActiveConversation,
    toggleRead: () => toggleConversationUnread(conversationActivity, conversationId),
    togglePin: handleToggleHeaderPin,
    showChatOptions: () => setShowChatOptions(true),
  });
  // ── Render ─────────────────────────────────────────────────────────────────

  if (accountBoundary.expired) {
    return <main className="flex h-[100dvh] flex-col items-center justify-center gap-4 bg-[#f9f9f9] p-6 text-center text-black dark:bg-[#141517] dark:text-white">
      <p role="alert" className="max-w-lg">{t("chat.account_changed")}</p>
      <button className="min-h-11 rounded-full bg-black px-6 py-3 text-base font-medium text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/25 dark:bg-white dark:text-black dark:focus-visible:ring-white/30" onClick={() => window.location.assign(signedInHomePath())}>{t("chat.account_changed_reload")}</button>
    </main>;
  }
  if (profileState === "probing" || profileState === "unavailable") {
    return (
      <div className="flex h-[100dvh] w-full items-center justify-center bg-background">
        <InitialConversationRetrievalState business={workspace?.id === "business"} />
      </div>
    );
  }

  if (profileState === "expired") {
    return (
      <ExpiredGuestSession
        publicAccountAccessEnabled={expiredPublicAccountAccessEnabled}
      />
    );
  }

  return (
    <ReceiptConversationProvider target={evidenceReceiptSharingEnabled ? guestExperience.receiptSharing.target : null} conversationId={conversationId} onClose={guestExperience.receiptSharing.close}>
    <ConversationActivityPresentationProvider
      selectPresentation={conversationActivity.selectPresentation}
      selectAggregatePresentation={conversationActivity.selectAggregatePresentation} selectOperationLabel={conversationActivity.selectOperationLabel}
    >
      <div className="relative flex h-[100dvh] w-full overflow-hidden bg-[#f9f9f9] text-black dark:bg-[#141517] dark:text-white tablet:flex-row">
      {/* ── Sidebar: rail on desktop, off-canvas drawer below the mobile threshold ── */}
      <SidebarShell
        isBelowTablet={mobileShell.isBelowTablet}
        isDrawerOpen={mobileShell.isDrawerOpen}
        onCloseDrawer={mobileShell.closeDrawer}
        label={t("common.navigation", "Navigation")}
      >
      <ChatSidebar
        variant={mobileShell.isBelowTablet ? "drawer" : "rail"}
        onRequestClose={mobileShell.closeDrawer}
        guestSettings={
          mobileShell.isBelowTablet && isGuest ? (
            <GuestSettingsMenu
              feedbackEnabled={canSubmitFeedback}
              onFeedback={requestGuestFeedback}
              placement="drawer"
            />
          ) : null
        }
        isOpen={mobileShell.isBelowTablet ? true : isSidebarOpen}
        onToggle={toggleSidebar}
        currentView={currentView}
        conversationId={conversationId}
        conversationActivity={conversationActivity}
        isRecentsExpanded={isRecentsExpanded}
        onToggleRecents={() => setIsRecentsExpanded((expanded) => !expanded)}
        historyItems={historyItems}
        historyNextCursor={historyNextCursor}
        isLoadingMoreHistory={isLoadingMoreHistory}
        hasRequestedOlderHistory={hasRequestedOlderHistory}
        historyLoadMoreError={historyLoadMoreError}
        onNewChat={() => {
          requestNewChat();
          closeTransientSidebar();
        }}
        onNavigate={(view) => {
          if (view !== "chat") {
            rememberCurrentConversationScroll();
            cancelTranscriptNavigation();
          }
          setCurrentView(view);
          closeTransientSidebar();
        }}
        onOpenItem={openHistoryItem}
        onLoadMoreHistory={loadMoreHistory}
        onOpenSearch={() => {
          closeDrawer();
          if (omnisearchEnabled) {
            requestOmnisearch();
          }
        }}
        onHistoryMutated={refreshHistory}
        onProfileUpdated={onProfileUpdated}
        onConversationRemoved={handleConversationRemoved}
        onAllConversationsDeleted={handleAllConversationsDeleted}
        onToast={showToast}
        onLogout={(options) => {
          void handleLogout(options);
        }}
        onFeedback={(type) => {
          setFeedbackState({
            isOpen: true,
            type,
            context: { surface: "sidebar", conversation_id: conversationId },
          });
        }}
        onOpenSidebarPreference={() => setIsSidebarPreferenceModalOpen(true)}
        onOpenKeyboardShortcuts={() =>
          keyboardShortcuts.setKeyboardShortcutsOpen(true)
        }
        settingsOpenRequest={keyboardShortcuts.settingsOpenRequest}
        mode={sidebarMode}
        omnisearchEnabled={
          omnisearchEnabled && (!isGuest || canUseOmnisearch)
        }
        shortcutHintsSuppressed={searchOverlayOpen}
        canManageConversation={canManageConversation}
        showProfileMenu={!isGuest}
        profileUser={account?.user}
        primaryNav={workspace?.sidebarNav(shellBridge)} headerSlot={workspace?.sidebarHeader?.(shellBridge)} footerActions={workspace?.sidebarFooter(shellBridge)} profileSlot={workspace?.profileInHeader && !mobileShell.isBelowTablet ? profileSlot : undefined}
        isGuest={guestExperience.isEstablishedGuest}
        guestExpiresAt={account?.guest?.expires_at}
      />
      </SidebarShell>

      <KeyboardShortcutSurfaces
        keyboardShortcutsOpen={keyboardShortcuts.keyboardShortcutsOpen}
        onCloseKeyboardShortcuts={() =>
          keyboardShortcuts.setKeyboardShortcutsOpen(false)
        }
        recentsQuickPeekOpen={keyboardShortcuts.isRecentsQuickPeekOpen}
        historyItems={historyItems}
        activeConversationId={conversationId}
        onOpenHistoryItem={openHistoryItem}
        onCloseRecentsQuickPeek={() =>
          keyboardShortcuts.setIsRecentsQuickPeekOpen(false)
        }
      />

      {omnisearchEnabled &&
        (!isGuest || canUseOmnisearch) &&
        searchOverlayOpen && (
          <ChatCommandPalette
            onClose={() => setSearchOverlayOpen(false)}
            onOpenConversation={(convId, messageId, openAtLeftOff) => {
              setSearchOverlayOpen(false);
              void loadConversation(convId, messageId, openAtLeftOff);
            }}
            onRetest={omnisearch.retest}
            onAsk={omnisearch.ask}
            turnInFlight={turnInFlight}
            activeConversationId={conversationId}
            isGuest={isGuest}
            groundedDiscoveryAvailable={canUseGroundedDiscovery}
            canManageConversation={canManageConversation}
            onDecisionUnavailable={requestGuestDecision}
            decisionResumeTarget={resumeDecisionTarget}
            onDecisionResumeHandled={clearResumeDecision}
            onMutated={refreshHistory}
            onConversationRemoved={handleConversationRemoved}
          />
        )}

      <ConversationDeleteDialog
        pending={pendingHeaderDelete}
        title={headerConversationTitle}
        isDeleting={isDeletingHeaderChat}
        onCancel={() => setPendingHeaderDelete(null)}
        onConfirm={() => void handleConfirmHeaderDelete()}
      />

      <section className="relative z-10 flex h-full flex-1 flex-col overflow-hidden bg-[#f9f9f9] dark:bg-[#141517]">
        {/* ── Unified View Header (SOTA: Absolute to content panel for perfect centering) ── */}
        {currentView !== "settings" && (
          <header className="absolute inset-x-0 top-0 z-[50] flex h-20 items-center justify-between gap-2 px-4 pointer-events-none tablet:gap-4 tablet:px-8">
            {mobileShell.isBelowTablet && (
              <div className="pointer-events-auto shrink-0">
                <ChatShellMenuTrigger
                  onOpen={mobileShell.openDrawer}
                  activityPresentation={
                    mobileShell.isDrawerOpen
                      ? null
                      : conversationActivity.selectAggregatePresentation(
                          historyItems.map((item) => item.conversation_id ?? item.id),
                        )
                  }
                />
              </div>
            )}
            {/* Title (left-aligned; truncates before the action cluster) */}
            <ChatHeaderHeading>
              {currentView === "chat" &&
                (conversationId !== null || messages.length > 0) &&
                !showEmptyChatSurface && (
                  <ChatHeaderTitle
                    conversationId={conversationId}
                    title={headerConversationTitle}
                    titleSource={headerConversationTitleSource}
                  />
                )}
            </ChatHeaderHeading>

            {/* Action cluster (guest settings or durable owner menu) */}
            <div className={`ml-auto flex shrink-0 justify-end pointer-events-auto${workspace ? " items-center gap-2" : ""}`}>
              {workspace?.headerActions(shellBridge)}
              {currentView === "chat" && isGuest ? (
                <GuestHeader
                  expiresAt={account?.guest?.expires_at ?? null}
                  feedbackEnabled={canSubmitFeedback}
                  onFeedback={requestGuestFeedback}
                  onSignIn={requestGuestSignIn}
                  showSettings={!mobileShell.isBelowTablet}
                />
              ) : currentView === "chat" &&
                conversationId &&
                canManageConversation ? (
                <ChatHeaderMenu
                  conversationId={conversationId}
                  onShare={guestExperience.receiptSharing.request}
                  isOpen={showChatOptions}
                  onToggleOpen={() => setShowChatOptions(!showChatOptions)}
                  onRequestClose={closeChatOptions}
                  isUnread={conversationActivity.hasEffectiveUnread(conversationId)}
                  isReadMutationPending={conversationActivity.hasEffectiveUnread(conversationId) ? conversationActivity.isMutationPending(conversationId, "mark_read") : conversationActivity.isMutationPending(conversationId, "mark_unread")}
                  onToggleUnread={() => void toggleConversationUnread(conversationActivity, conversationId)}
                  isRenaming={isRenamingHeaderChat}
                  renameValue={headerRenameValue}
                  onRenameValueChange={setHeaderRenameValue}
                  onStartRename={handleStartHeaderRename}
                  onSaveRename={() => void handleSaveHeaderRename()}
                  onCancelRename={() => setIsRenamingHeaderChat(false)}
                  isSavingRename={isSavingHeaderRename}
                  pinned={Boolean(activeHistoryChat?.pinned)}
                  isPinning={isPinningHeaderChat}
                  onTogglePin={() => void handleToggleHeaderPin()}
                  isDeleting={isDeletingHeaderChat}
                  onRequestDelete={() => handleRequestHeaderDelete()}
                  memoryChrome={memoryChrome}
                />
              ) : null}
              {workspace?.profileInHeader && !mobileShell.isBelowTablet ? <div ref={setProfileSlot} className="relative" /> : null}
            </div>
          </header>
        )}
        {currentView === "workspace" && workspace && (
          <WorkspaceMain workspace={workspace} bridge={shellBridge} composerNotice={dailyCap.notice} disabled={conversationComposerUnavailable} onToast={showToast} onSend={handleSend} setCurrentView={setCurrentView} />
        )}
        {currentView === "chat" && (
          <div className="relative mx-auto flex h-[100dvh] w-full max-w-5xl flex-col">
            <ConversationActivityAnnouncement activity={conversationActivity} conversationId={conversationId} title={activeTitleRecord ? headerConversationTitle : null} enabled={!isHydratingConversation} />
            {showEmptyChatSurface ? (
              <EmptyChatSurface
                isGuest={isGuest}
                expiresAt={account?.guest?.expires_at}
                guestSubmissionPending={guestSubmissionPending || Boolean(readReceiptFollowup())}
                guestSubmissionError={guestEntry.guestSubmissionError}
                isStreamingResponse={isStreamingResponse}
                isHydratingConversation={isHydratingConversation}
                canConsumeLandingStarter={initialRoutingSettled}
                preferredName={greetingName}
                placeholder={chatInputPlaceholder}
                composerNotice={dailyCap.notice}
                onSend={handleSend}
                onRetryGuestSubmission={retryGuestSubmission}
                onToast={showToast}
                workspace={workspace ? { lead: workspace.emptyChatLead(shellBridge), starterEntries: workspace.starterEntries(shellBridge), composer: workspace.composer(shellBridge) } : undefined}
              />
            ) : (
              <>
                <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-32 bg-[#f9f9f9]/80 backdrop-blur-[0.8px] [mask-image:linear-gradient(to_bottom,black_48%,transparent_100%)] dark:bg-[#141517]/80" />

                {showConversationRetrievalState && isHydratingConversation && (
                  <ConversationRetrievalAnnouncement business={workspace?.id === "business"} />
                )}

                {/* Messages */}
                <div
                  data-testid="conversation-transcript-region"
                  data-conversation-id={conversationId ?? undefined}
                  ref={scrollContainerRef}
                  onScroll={updateScrollPositionState}
                  role="region"
                  aria-label={t("common.conversation", "Conversation")}
                  aria-busy={isHydratingConversation || guestSubmissionPending}
                  className="argus-scrollbar flex-1 overflow-y-auto px-4 pt-[86px]"
                  style={{ paddingBottom: 190 + dailyCap.height }}
                >
                  <div className="space-y-8">
                    {showConversationRetrievalState &&
                      isHydratingConversation && (
                        <ConversationRetrievalState state="loading" business={workspace?.id === "business"} />
                      )}
                    {hasConversationLoadFailure && (
                      <ConversationRetrievalState
                        state="error"
                        onRetry={() => {
                          if (failedConversationId) void loadConversation(failedConversationId);
                        }}
                      />
                    )}
                    {messages.map((msg, index) => {
                      const { isLatestAi, isWorkingMessage } =
                        messageStreamPresentation(
                          messages,
                          msg,
                          index,
                          isStreamingResponse,
                          !!visibleStreamStatus,
                        );
                      return (
                        <div
                          key={msg.id}
                          ref={messageElementRegistrar(messageElementRefs, msg.id)}
                          data-message-id={msg.id}
                          tabIndex={-1}
                          className="scroll-m-24 outline-none"
                        >
                          <ReceiptConversationTurn messageId={msg.id}><ChatMessage
                            message={msg}
                            onAction={handleAction}
                            onDirectEdit={handleDirectEditConfirmation}
                            onToolRecompute={(card, changes) => handleToolRecompute(msg.id, card, changes)}
                            onOpenConversation={(id) => { void loadConversation(id); }}
                            onFeedback={(type, context, rating) => {
                              void handleMessageFeedback(type, context, rating);
                            }}
                            onToast={showToast}
                            isLatest={isLatestAi} latestMessageId={messages.at(-1)?.id}
                            isStreaming={isWorkingMessage}
                            conversationId={conversationId}
                            memoryProposalEnabled={memoryChrome.proposalEnabled}
                            nextMovesEnabled={nextMovesEnabled}
                            turnInFlight={turnInFlight}
                            isGuest={isGuest}
                            canSaveDecision={canSaveDecision}
                            onDecisionUnavailable={(artifactId) =>
                              requestGuestDecision({ surface: "result_card", artifactId })
                            }
                            onDecisionSaved={(decisionState) => {
                              setMessages((prev) =>
                                messagesWithSavedDecisionState(
                                  prev,
                                  msg.id,
                                  decisionState,
                                ),
                              );
                              if (conversationId) invalidateTranscriptForMutation(conversationId, "durable_result_action");
                            }}
                            onRequestSearchUpgrade={requestGuestSearchUpgrade}
                            resumeDecisionArtifactId={
                              msg.id === resumeDecisionMessageId ? resumeDecisionArtifactId : null
                            }
                            onDecisionResumeHandled={clearResumeDecision}
                          /></ReceiptConversationTurn>
                        </div>
                      );
                    })}
                    {showStreamStatus && (
                      <div className="ml-12">
                        <span className="animate-ethereal-shimmer text-[13px] text-black/45 dark:text-white/45">
                          {visibleStreamStatus}
                        </span>
                      </div>
                    )}
                    <FeedbackAsk conversationId={conversationId} messages={messages} answerArriving={isStreamingResponse} enabled={canSubmitFeedback} onToast={showToast} onTellUsMore={(context) => setFeedbackState(openFeedbackDialogState("general", context, undefined, conversationId))} />
                    <div ref={latestActivitySentinelRef} data-testid="latest-activity-sentinel" className="h-px" aria-hidden="true" />
                    <div ref={bottomRef} className="h-28" aria-hidden="true" />
                  </div>
                </div>

                <ConversationActivityRail
                  messages={messages}
                  onSelectTick={anchorToTurn}
                />

                {/* Input fade + bar */}
                <div className="pointer-events-none absolute bottom-0 inset-x-0 z-10 h-40 bg-[#f9f9f9]/80 backdrop-blur-[0.8px] [mask-image:linear-gradient(to_top,black_50%,transparent_100%)] dark:bg-[#141517]/80" />
                <div className="pointer-events-none absolute bottom-6 inset-x-0 z-20 px-4">
                  <div className="pointer-events-auto mx-auto max-w-3xl rounded-full">
                    {showJumpToLatest && (
                      <div className="mb-3 flex justify-center">
                        <ConversationActivityJumpButton
                          presentation={conversationActivity.selectPresentation(conversationId)}
                          onJump={() => scrollToLatest("smooth")}
                        />
                      </div>
                    )}
                    {dailyCap.notice}
                    <ReceiptSelectionComposer><ChatInput
                      key={conversationId ?? "unowned-transcript"}
                      onSend={handleSend}
                      disabled={conversationComposerUnavailable}
                      placeholder={chatInputPlaceholder}
                      onToast={showToast}
                      {...workspaceComposerProps(workspace, shellBridge)}
                    /></ReceiptSelectionComposer>
                    <ChatLegalNotice
                      expiresAt={account?.guest?.expires_at}
                      isGuest={isGuest}
                      showRegisteredDisclaimer={showConversationDisclaimer}
                      variant="after_message"
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        <ChatToast
          message={toast?.message ?? null}
          variant={toast?.variant}
          action={toast?.action}
        />
      </section>

      {/* ── Feedback Dialog ── */}
      <FeedbackDialog
        isOpen={feedbackState.isOpen}
        onClose={() => setFeedbackState((s) => ({ ...s, isOpen: false }))}
        type={feedbackState.type}
        rating={feedbackState.rating}
        context={feedbackState.context}
      />
      {workspace?.bottomNavigation?.(shellBridge)}
      {receiptFollowup}<GuestExperienceSurfaces experience={guestExperience} />
      {evidenceReceiptSharingEnabled && guestExperience.receiptSharing.target && <ShareReceiptPanel key={guestExperience.receiptSharing.target.conversationId} {...guestExperience.receiptSharing.target} onClose={guestExperience.receiptSharing.close} />}
      {isSidebarPreferenceModalOpen && (
        <SidebarPreferenceModal
          mode={sidebarMode}
          onSelect={handleSetSidebarMode}
          onClose={() => setIsSidebarPreferenceModalOpen(false)}
        />
      )}
      </div>
    </ConversationActivityPresentationProvider></ReceiptConversationProvider>
  );
}
