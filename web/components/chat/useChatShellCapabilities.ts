"use client";

import { useCallback, useEffect, useState } from "react";
import { hasOpenOverlay } from "@/components/layout/overlayStack";
import type { UserResponse } from "@/lib/guest-account";
import { matchesKeyboardShortcut } from "@/lib/keyboard-shortcuts";
import type { ReceiptShareTarget } from "@/lib/receipt-selection";

type UseChatShellCapabilitiesInput = {
  account: UserResponse | null;
  conversationId: string | null;
  closeTransientSidebar: () => void;
  onNewChat: () => void | Promise<unknown>;
  onOpenOmnisearch: () => void;
  omnisearchShortcutEnabled: boolean;
};

export function useChatShellCapabilities({
  account,
  conversationId,
  closeTransientSidebar,
  onNewChat,
  onOpenOmnisearch,
  omnisearchShortcutEnabled,
}: UseChatShellCapabilitiesInput) {
  const capabilities = account?.capabilities;
  const registered = account?.account_kind === "registered";
  const canManageConversation =
    capabilities?.can_manage_conversation ?? registered;
  const canSaveDecision = capabilities?.can_save_decision ?? registered;
  const canUseOmnisearch = capabilities?.can_use_omnisearch ?? registered;
  const canUseGroundedDiscovery =
    capabilities?.can_use_grounded_discovery ?? registered;
  const canSubmitFeedback = capabilities?.can_submit_feedback ?? false;

  const requestOmnisearch = useCallback(() => {
    onOpenOmnisearch();
  }, [onOpenOmnisearch]);

  const requestNewChat = useCallback(() => {
    void onNewChat();
    closeTransientSidebar();
  }, [closeTransientSidebar, onNewChat]);

  useEffect(() => {
    if (!omnisearchShortcutEnabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesKeyboardShortcut("omnisearch", event)) return;
      if (hasOpenOverlay()) return;
      event.preventDefault();
      requestOmnisearch();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [omnisearchShortcutEnabled, requestOmnisearch]);

  const [receiptShareTarget, setReceiptShareTarget] =
    useState<ReceiptShareTarget | null>(null);
  const requestReceiptShare = useCallback(
    (sourceConversationId: string, messageId?: string) => {
      if (sourceConversationId !== conversationId) return;
      setReceiptShareTarget({
        conversationId: sourceConversationId,
        messageId,
      });
    },
    [conversationId],
  );
  const closeReceiptShare = useCallback(() => setReceiptShareTarget(null), []);

  return {
    isGuest: false,
    isEstablishedGuest: false,
    canManageConversation,
    canSaveDecision,
    canUseOmnisearch,
    canUseGroundedDiscovery,
    canSubmitFeedback,
    requestNewChat,
    requestOmnisearch,
    receiptSharing: {
      target:
        receiptShareTarget?.conversationId === conversationId
          ? receiptShareTarget
          : null,
      request: requestReceiptShare,
      close: closeReceiptShare,
    },
  };
}
