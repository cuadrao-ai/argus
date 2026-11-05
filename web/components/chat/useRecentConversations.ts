"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  listConversations,
  type HistoryItem,
} from "@/lib/argus-api";
import {
  mergeRecentChats,
  prepareFirstPageRecentChatsRefresh,
  projectConversationToRecentChat,
} from "@/lib/chat-recents";
import {
  createConversationActivityCausalClock,
  type ConversationActivityCausalClock,
  type ConversationActivityHistorySnapshot,
} from "@/lib/conversation-activity-state";
import { useConversationSurface } from "./ChatWorkspace";

type UseRecentConversationsOptions = Readonly<{
  enabled?: boolean;
  guestExpiresAt?: string | null;
  activityCausalClock?: ConversationActivityCausalClock;
}>;

type RecentConversationsState = {
  historyItems: HistoryItem[];
  historyActivityRevision: number;
  setHistoryItems: Dispatch<SetStateAction<HistoryItem[]>>;
  historyNextCursor: string | null;
  isLoadingMoreHistory: boolean;
  hasRequestedOlderHistory: boolean;
  historyLoadMoreError: boolean;
  loadHistoryPage: (
    nextCursor?: string | null,
    append?: boolean,
  ) => Promise<ConversationActivityHistorySnapshot>;
  clearHistory: () => void;
  loadMoreHistory: () => void;
  refreshHistory: () => void;
  refreshHistoryForActivity: () => Promise<ConversationActivityHistorySnapshot>;
};

export type RecentHistoryActivityState = Readonly<{
  historyItems: HistoryItem[];
  historyActivityRevision: number;
}>;

export const applyRecentHistoryActivityUpdate = (
  current: RecentHistoryActivityState,
  update: SetStateAction<HistoryItem[]>,
  revision: number,
): RecentHistoryActivityState => ({
  historyItems:
    typeof update === "function" ? update(current.historyItems) : update,
  historyActivityRevision: revision,
});

export const runHistoryRefreshSafely = (
  refresh: () => Promise<ConversationActivityHistorySnapshot>,
): void => {
  void refresh().catch(() => undefined);
};

export function useRecentConversations({
  enabled = true,
  guestExpiresAt,
  activityCausalClock,
}: UseRecentConversationsOptions): RecentConversationsState {
  const enabledRef = useRef(enabled);
  useLayoutEffect(() => { enabledRef.current = enabled; }, [enabled]);
  const scopeRevision = useRef(0);
  const [fallbackActivityCausalClock] = useState(
    createConversationActivityCausalClock,
  );
  const causalClock = activityCausalClock ?? fallbackActivityCausalClock;
  const surface = useConversationSurface();
  const [historyActivityState, setHistoryActivityState] =
    useState<RecentHistoryActivityState>({
      historyItems: [],
      historyActivityRevision: 0,
    });
  const { historyItems, historyActivityRevision } = historyActivityState;
  const setHistoryItems = useCallback<
    Dispatch<SetStateAction<HistoryItem[]>>
  >(
    (update) => {
      const revision = causalClock.nextRevision();
      setHistoryActivityState((current) =>
        applyRecentHistoryActivityUpdate(current, update, revision),
      );
    },
    [causalClock],
  );
  const [historyNextCursor, setHistoryNextCursor] = useState<string | null>(
    null,
  );
  const [isLoadingMoreHistory, setIsLoadingMoreHistory] = useState(false);
  const [hasRequestedOlderHistory, setHasRequestedOlderHistory] =
    useState(false);
  const [historyLoadMoreError, setHistoryLoadMoreError] = useState(false);
  const paginationInFlightRef = useRef(false);
  const pageRequestsRef = useRef(
    new Map<string, Promise<ConversationActivityHistorySnapshot>>(),
  );
  const firstPageConversationIdsRef = useRef<Set<string>>(new Set());
  const guestExpiresAtRef = useRef(guestExpiresAt);

  useEffect(() => {
    guestExpiresAtRef.current = guestExpiresAt;
  }, [guestExpiresAt]);

  const loadHistoryPage = useCallback(
    (nextCursor?: string | null, append = false) => {
      if (!enabledRef.current) return Promise.resolve({ items: [], revision: causalClock.nextRevision() });
      const requestScope = scopeRevision.current;
      const requestKey = nextCursor ?? "first-page";
      const existingRequest = pageRequestsRef.current.get(requestKey);
      if (existingRequest) return existingRequest;
      const activityRevision = causalClock.nextRevision();

      const request = listConversations({
        surface,
        limit: 30,
        cursor: nextCursor ?? undefined,
        archived: false,
        deleted: false,
      })
        .then(({ items, next_cursor }) => {
          if (!enabledRef.current || requestScope !== scopeRevision.current) return { items: [], revision: activityRevision };
          const projected = items
            .filter(
              (conversation) => conversation.preview?.kind !== "empty",
            )
            .map((conversation) =>
              projectConversationToRecentChat(conversation, {
                guestExpiresAt: guestExpiresAtRef.current,
              }),
            );
          if (append) {
            setHistoryActivityState((current) =>
              applyRecentHistoryActivityUpdate(
                current,
                (items) => mergeRecentChats(items, projected),
                activityRevision,
              ),
            );
          } else {
            const refresh = prepareFirstPageRecentChatsRefresh(
              firstPageConversationIdsRef.current,
              projected,
            );
            setHistoryActivityState((current) =>
              applyRecentHistoryActivityUpdate(
                current,
                refresh.apply,
                activityRevision,
              ),
            );
            firstPageConversationIdsRef.current = refresh.nextFirstPageConversationIds;
          }
          setHistoryNextCursor(next_cursor);
          return { items: projected, revision: activityRevision };
        })
        .finally(() => {
          if (pageRequestsRef.current.get(requestKey) === request) pageRequestsRef.current.delete(requestKey);
        });
      pageRequestsRef.current.set(requestKey, request);
      return request;
    },
    [causalClock, surface],
  );

  const refreshHistoryForActivity = useCallback(() => {
    const runRefresh = () => loadHistoryPage(null, false);
    const inFlightFirstPage =
      pageRequestsRef.current.get("first-page");
    const refreshRequest = inFlightFirstPage
      ? inFlightFirstPage.then(runRefresh, runRefresh)
      : runRefresh();
    return refreshRequest;
  }, [loadHistoryPage]);

  const refreshHistory = useCallback(() => {
    runHistoryRefreshSafely(refreshHistoryForActivity);
  }, [refreshHistoryForActivity]);

  const clearHistory = useCallback(() => {
    scopeRevision.current += 1;
    const revision = causalClock.nextRevision();
    setHistoryActivityState({
      historyItems: [],
      historyActivityRevision: revision,
    });
    setHistoryNextCursor(null);
    setHasRequestedOlderHistory(false);
    setHistoryLoadMoreError(false);
    pageRequestsRef.current.clear();
    firstPageConversationIdsRef.current.clear();
    paginationInFlightRef.current = false;
  }, [causalClock]);

  const loadMoreHistory = useCallback(() => {
    if (!historyNextCursor || paginationInFlightRef.current) return;
    paginationInFlightRef.current = true;
    setHasRequestedOlderHistory(true);
    setHistoryLoadMoreError(false);
    setIsLoadingMoreHistory(true);
    void loadHistoryPage(historyNextCursor, true)
      .catch(() => setHistoryLoadMoreError(true))
      .finally(() => {
        paginationInFlightRef.current = false;
        setIsLoadingMoreHistory(false);
      });
  }, [historyNextCursor, loadHistoryPage]);

  useEffect(() => {
    if (!enabled) { clearHistory(); return; }
    void loadHistoryPage(null, false).catch(() => undefined);
  }, [enabled, clearHistory, loadHistoryPage]);

  return {
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
  };
}
