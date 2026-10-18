"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import type {
  ChatActionOption,
  ChatMention,
  Message,
} from "@/components/chat/types";
import { useGuestConversion } from "@/components/guest/useGuestConversion";
import { useGuestShellActions } from "@/components/guest/useGuestShellActions";
import { getUsageAllowances } from "@/lib/argus-api";
import {
  decideGuestSimulationGate,
  guestSimulationPrecheckReset,
  isExactGuestRunReplay,
} from "@/lib/guest-capability-gates";
import { replaceGuestConversation } from "@/lib/guest-api";
import type { UserResponse } from "@/lib/guest-account";
import {
  cancelPendingGuestBootstrap,
  isGuestBootstrapAbortError,
  startGuestSession,
} from "@/lib/guest-session";
import {
  hasCampaignAttribution,
  prepareLandingStarterAuthHandoff,
} from "@/lib/landing-intent";
import {
  latestDecisionResumeMessageId,
  newConversationConversionMode,
  type GuestDecisionResumeTarget,
  type GuestPendingAction,
} from "@/lib/guest-conversion";
import { randomId } from "@/lib/random-id";
import type { ReceiptShareTarget } from "@/lib/receipt-selection";

export type GuestResumeSend = (
  text: string,
  mentionsOrAction?: ChatMention[] | ChatActionOption,
  action?: ChatActionOption,
  options?: { bypassGuestGate?: boolean },
) => Promise<boolean>;

export function useGuestSendBridge(
  sendRef: MutableRefObject<GuestResumeSend | null>,
  send: GuestResumeSend,
) {
  useEffect(() => {
    sendRef.current = send;
    return () => {
      sendRef.current = null;
    };
  }, [send, sendRef]);
}

type UseGuestExperienceInput = {
  account: UserResponse | null;
  guestBootstrapRequired: boolean;
  conversationId: string | null;
  messages: Message[];
  sendRef: MutableRefObject<GuestResumeSend | null>;
  refreshAccount: (expectedUserId?: string) => Promise<UserResponse | null>;
  refreshHistory: () => void;
  refreshHistoryForActivity: () => Promise<unknown>;
  closeTransientSidebar: () => void;
  startNewChat: () => Promise<unknown>;
  onOpenFeedback: () => void;
  onOpenOmnisearch: () => void;
  onRequestPendingGuestSignIn: () => void;
  onAdoptConversation: (conversationId: string) => void;
  onGuestBootstrapExpired: (publicAccountAccessEnabled: boolean) => void;
  onAuthenticationStart: () => void;
  onAuthenticationComplete: (userId: string | null) => void;
  onGuestBootstrapError: (error?: unknown) => void;
  onGateError: () => void;
  onStartOverError: () => void;
  omnisearchShortcutEnabled: boolean;
};

type GuestSendAdmissionInput = {
  text: string;
  mentions: ChatMention[];
  action?: ChatActionOption;
  language?: string | null;
};

export function useGuestExperience({
  account,
  guestBootstrapRequired,
  conversationId,
  messages,
  sendRef,
  refreshAccount,
  refreshHistory,
  refreshHistoryForActivity,
  closeTransientSidebar,
  startNewChat,
  onOpenFeedback,
  onOpenOmnisearch,
  onRequestPendingGuestSignIn,
  onAdoptConversation,
  onGuestBootstrapExpired,
  onGuestBootstrapError,
  onAuthenticationStart,
  onAuthenticationComplete,
  onGateError,
  onStartOverError,
  omnisearchShortcutEnabled,
}: UseGuestExperienceInput) {
  const [isNewConversationOpen, setIsNewConversationOpen] = useState(false);
  const [isReplacingConversation, setIsReplacingConversation] = useState(false);
  const [resumeDecisionTarget, setResumeDecisionTarget] =
    useState<GuestDecisionResumeTarget | null>(null);
  const [receiptShareTarget, setReceiptShareTarget] = useState<ReceiptShareTarget | null>(null);
  const pendingGuestAdmissionRef = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      pendingGuestAdmissionRef.current?.abort();
      pendingGuestAdmissionRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!guestBootstrapRequired || !hasCampaignAttribution()) return;
    void startGuestSession(account?.user.language ?? null).catch((error) => {
      if (isGuestBootstrapAbortError(error)) return;
    });
    return () => {
      cancelPendingGuestBootstrap();
    };
  }, [account?.user.language, guestBootstrapRequired]);

  const resumeGuestAction = useCallback(
    async (action: GuestPendingAction) => {
      if (action.reason === "simulation_limit") {
        await sendRef.current?.(
          action.action.label || action.action.value || "",
          action.action,
          undefined,
          { bypassGuestGate: true },
        );
      } else if (action.reason === "save_decision") {
        setResumeDecisionTarget(action.target);
      } else if (action.reason === "share_result") {
        setReceiptShareTarget({ conversationId: action.conversationId, messageId: action.messageId });
      } else if (action.reason === "new_conversation") {
        await startNewChat();
      }
      refreshHistory();
    },
    [refreshHistory, sendRef, startNewChat],
  );

  const conversion = useGuestConversion({
    account,
    conversationId,
    refreshAccount,
    refreshHistory: refreshHistoryForActivity,
    onResume: resumeGuestAction,
    onAuthenticationStart,
    onAuthenticationComplete,
  });

  const shell = useGuestShellActions({
    account,
    guestBootstrapRequired,
    hasAcceptedContent: messages.some((message) => message.role === "user"),
    closeTransientSidebar,
    onOpenFeedback,
    onNewChat: startNewChat,
    onRequestNonEmptyGuestChoice: () => setIsNewConversationOpen(true),
    onRequestGuestDecision: (target) => {
      if (!conversationId) return;
      conversion.requestConversion("save_decision", {
        reason: "save_decision",
        conversationId,
        actionId: randomId(),
        target,
      });
    },
    onOpenOmnisearch,
    onRequestSignIn: () => {
      if (guestBootstrapRequired) {
        prepareLandingStarterAuthHandoff();
        cancelPendingGuestBootstrap();
        pendingGuestAdmissionRef.current?.abort();
        pendingGuestAdmissionRef.current = null;
        onRequestPendingGuestSignIn();
        return;
      }
      conversion.requestConversion(
        "keep_history",
        conversationId
          ? {
              reason: "keep_history",
              conversationId,
              actionId: randomId(),
            }
          : null,
      );
    },
    omnisearchShortcutEnabled,
  });

  const admitSend = useCallback(
    async ({ action, language }: GuestSendAdmissionInput) => {
      const admissionController = guestBootstrapRequired
        ? new AbortController()
        : null;
      const admissionCancelled = () =>
        admissionController?.signal.aborted ?? false;
      if (admissionController) {
        pendingGuestAdmissionRef.current?.abort();
        pendingGuestAdmissionRef.current = admissionController;
      }

      try {
        let effectiveAccount = account;
        if (guestBootstrapRequired) {
          try {
            const bootstrap = await startGuestSession(language);
            if (admissionCancelled()) return false;
            if (bootstrap.renewed_after_expiry) {
              onGuestBootstrapExpired(
                bootstrap.public_account_access_enabled ?? false,
              );
              return false;
            }
            const refreshedAccount = await refreshAccount();
            if (admissionCancelled()) return false;
            if (refreshedAccount === null) {
              onGuestBootstrapError();
              return false;
            }
            effectiveAccount = refreshedAccount;
          } catch (error) {
            if (isGuestBootstrapAbortError(error) || admissionCancelled()) {
              return false;
            }
            onGuestBootstrapError(error);
            return false;
          }
        }
        if (admissionCancelled()) return false;
        if (effectiveAccount?.account_kind !== "guest") return true;

        // Conversation is compute and never gated; only a run reads the
        // execution allowance before it is sent.
        if (action?.type !== "run_backtest") return true;
        try {
          const usage = await getUsageAllowances();
          if (admissionCancelled()) return false;
          const decision = decideGuestSimulationGate({
            accountKind: "guest",
            availableNow: usage.allowances.execution.available_now,
            exactReplay: isExactGuestRunReplay(messages, action),
          });
          if (decision.kind === "convert") {
            // The prompt is the answer to a spent allowance, so it opens
            // whether or not there is a conversation to replay into. Only
            // the pending action needs one; gating the prompt on it left a
            // returning guest pressing send against silence.
            const reset = guestSimulationPrecheckReset(
              usage.allowances.execution,
            );
            conversion.requestConversion(
              decision.reason,
              conversationId
                ? {
                    reason: "simulation_limit",
                    conversationId,
                    actionId: randomId(),
                    action,
                  }
                : null,
              "signup",
              reset.resetAt,
              reset.resetKind,
            );
            return false;
          }
          return true;
        } catch {
          if (!admissionCancelled()) onGateError();
          return false;
        }
      } finally {
        if (pendingGuestAdmissionRef.current === admissionController) {
          pendingGuestAdmissionRef.current = null;
        }
      }
    },
    [
      conversationId,
      conversion,
      account,
      guestBootstrapRequired,
      messages,
      onGuestBootstrapError,
      onGuestBootstrapExpired,
      onGateError,
      refreshAccount,
    ],
  );

  const startOver = useCallback(async () => {
    if (isReplacingConversation) return;
    setIsReplacingConversation(true);
    try {
      const { conversation } = await replaceGuestConversation();
      onAdoptConversation(conversation.id);
      setIsNewConversationOpen(false);
      refreshHistory();
    } catch {
      onStartOverError();
    } finally {
      setIsReplacingConversation(false);
    }
  }, [
    isReplacingConversation,
    onAdoptConversation,
    onStartOverError,
    refreshHistory,
  ]);

  const closeNewConversation = useCallback(() => {
    if (!isReplacingConversation) setIsNewConversationOpen(false);
  }, [isReplacingConversation]);

  const convertForNewConversation = useCallback(() => {
    if (!conversationId) return;
    setIsNewConversationOpen(false);
    conversion.requestConversion(
      "new_conversation",
      {
        reason: "new_conversation",
        conversationId,
        actionId: randomId(),
      },
      newConversationConversionMode(
        conversion.publicAccountAccessEnabled,
      ),
    );
  }, [conversationId, conversion]);

  const recoverGuestSimulationRejection = useCallback(
    (action: ChatActionOption) => {
      if (
        account?.account_kind !== "guest" ||
        !conversationId ||
        action.type !== "run_backtest"
      ) {
        return false;
      }
      conversion.requestConversion(
        "simulation_limit",
        {
          reason: "simulation_limit",
          conversationId,
          actionId: randomId(),
          action,
        },
        "signup",
        account.guest?.expires_at ?? null,
        "workspace",
      );
      return true;
    },
    [account, conversationId, conversion],
  );

  const clearResumeDecision = useCallback(
    () => setResumeDecisionTarget(null),
    [],
  );
  const resumeDecisionArtifactId =
    resumeDecisionTarget?.surface === "result_card"
      ? resumeDecisionTarget.artifactId
      : null;
  const resumeDecisionMessageId = latestDecisionResumeMessageId(
    messages,
    resumeDecisionArtifactId,
  );

  const requestGuestSearchUpgrade = useCallback(
    () => conversion.requestConversion("discovery_searches", null),
    [conversion],
  )

  const requestReceiptShare = useCallback((sourceConversationId: string, messageId?: string) => {
    if (sourceConversationId !== conversationId) return;
    if (account?.account_kind === "guest") {
      if (messageId) conversion.requestConversion("share_result", {
        reason: "share_result", conversationId: sourceConversationId, messageId, actionId: randomId(),
      }, "signup");
      return;
    }
    setReceiptShareTarget({ conversationId: sourceConversationId, messageId });
  }, [account?.account_kind, conversationId, conversion]);

  return {
    ...shell,
    admitSend,
    recoverGuestSimulationRejection,
    requestGuestSearchUpgrade,
    receiptSharing: {
      target: receiptShareTarget?.conversationId === conversationId ? receiptShareTarget : null,
      request: requestReceiptShare,
      close: () => setReceiptShareTarget(null),
    },
    resumeDecisionTarget,
    resumeDecisionArtifactId,
    resumeDecisionMessageId,
    clearResumeDecision,
    conversion,
    newConversation: {
      isOpen: isNewConversationOpen,
      isReplacing: isReplacingConversation,
      close: closeNewConversation,
      startOver,
      convert: convertForNewConversation,
    },
  };
}

export type GuestExperience = ReturnType<typeof useGuestExperience>;
