"use client";

import { useEffect, useRef, useState } from "react";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import {
  listConversations,
  type HistoryItem,
  type TitleSource,
} from "@/lib/argus-api";
import { conversationDisplayTitle, conversationTabTitle } from "@/lib/chat-title-display";

type FallbackTitleConversation = {
  id: string;
  title: string;
  title_source: TitleSource | null;
};

export type ActiveTitleRecord = {
  title: string;
  title_source?: TitleSource | null;
};

/**
 * Resolves the active conversation's display title from the same history
 * state Recents renders, with a one-shot listConversations fallback for
 * conversations outside the loaded history page. Mirrors the resolved name
 * into the browser tab title.
 */
export function useActiveConversationTitle({
  conversationId,
  activeHistoryChat,
  messageCount,
  isStreamingResponse,
  isChatViewActive,
  placeholder,
}: {
  conversationId: string | null;
  activeHistoryChat: HistoryItem | null;
  messageCount: number;
  isStreamingResponse: boolean;
  isChatViewActive: boolean;
  placeholder: string;
}): {
  activeTitleRecord: ActiveTitleRecord | null;
  headerConversationTitle: string;
  headerConversationTitleSource: TitleSource | null;
} {
  const [fallbackTitleConversation, setFallbackTitleConversation] =
    useState<FallbackTitleConversation | null>(null);
  const fallbackTitleFetchedForRef = useRef<string | null>(null);
  const surface = useConversationSurface();

  useEffect(() => {
    setFallbackTitleConversation((prev) =>
      prev && prev.id === conversationId ? prev : null,
    );
  }, [conversationId]);

  useEffect(() => {
    if (
      !conversationId ||
      activeHistoryChat ||
      messageCount === 0 ||
      isStreamingResponse
    ) {
      return;
    }
    if (fallbackTitleFetchedForRef.current === conversationId) return;
    fallbackTitleFetchedForRef.current = conversationId;
    let cancelled = false;
    listConversations({ limit: 50, surface })
      .then(({ items }) => {
        if (cancelled) return;
        const conversation = items.find((item) => item.id === conversationId);
        if (!conversation) return;
        setFallbackTitleConversation({
          id: conversation.id,
          title: conversation.title,
          title_source: conversation.title_source,
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [conversationId, activeHistoryChat, messageCount, isStreamingResponse, surface]);

  const activeTitleRecord =
    activeHistoryChat ??
    (fallbackTitleConversation && fallbackTitleConversation.id === conversationId
      ? fallbackTitleConversation
      : null);
  const headerConversationTitle = conversationDisplayTitle(
    activeTitleRecord,
    placeholder,
  );
  const headerConversationTitleSource = activeTitleRecord?.title_source ?? null;

  useEffect(() => {
    document.title = conversationTabTitle(activeTitleRecord, isChatViewActive, surface);
  }, [isChatViewActive, activeTitleRecord, surface]);

  return {
    activeTitleRecord,
    headerConversationTitle,
    headerConversationTitleSource,
  };
}
