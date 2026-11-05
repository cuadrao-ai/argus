import { consumeOverlayEntriesForNavigation } from "./overlay-history";
import type { ChatActionOption } from "@/components/chat/types";

export type ActiveConversationRouteState = {
  conversationId: string | null;
  messageId: string | null;
  isChatRoute: boolean;
  isNewChatRoute: boolean;
};

const ACTIVE_CONVERSATION_QUERY_KEY = "conversation";
/** Every route that hosts the chat shell, Argus chat and workspaces alike. */
export const CHAT_SHELL_PATHS: ReadonlySet<string> = new Set(["/chat", "/biz", "/dev/business-preview"]);
const ACTIVE_MESSAGE_QUERY_KEY = "message";

export function activeConversationRouteStateFromUrl(
  href: string,
  queryKey = "conversation",
  messageQueryKey = "message",
): ActiveConversationRouteState {
  try {
    const url = new URL(href);
    const conversationId = url.searchParams.get(queryKey)?.trim() || null;
    const messageId = url.searchParams.get(messageQueryKey)?.trim() || null;
    const isChatRoute = CHAT_SHELL_PATHS.has(url.pathname);
    return {
      conversationId: isChatRoute ? conversationId : null,
      messageId: isChatRoute && conversationId ? messageId : null,
      isChatRoute,
      isNewChatRoute: isChatRoute && conversationId === null,
    };
  } catch {
    return {
      conversationId: null,
      messageId: null,
      isChatRoute: false,
      isNewChatRoute: false,
    };
  }
}

export function readActiveConversationRouteState(): ActiveConversationRouteState {
  if (typeof window === "undefined") {
    return activeConversationRouteStateFromUrl("");
  }
  return activeConversationRouteStateFromUrl(window.location.href);
}

export function rememberActiveConversationId(
  conversationId: string,
  messageId?: string,
): void {
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    if (!CHAT_SHELL_PATHS.has(url.pathname)) return;
    if (
      url.searchParams.get(ACTIVE_CONVERSATION_QUERY_KEY) === conversationId &&
      (url.searchParams.get(ACTIVE_MESSAGE_QUERY_KEY) ?? undefined) === messageId
    ) {
      return;
    }
    url.searchParams.set(ACTIVE_CONVERSATION_QUERY_KEY, conversationId);
    if (messageId) {
      url.searchParams.set(ACTIVE_MESSAGE_QUERY_KEY, messageId);
    } else {
      url.searchParams.delete(ACTIVE_MESSAGE_QUERY_KEY);
    }
    // Navigating rewrites the URL onto whatever entry is current, and with an
    // overlay open that is the entry the overlay pushed. Popping it on teardown
    // would put the previous conversation back in the address bar while the new
    // one is on screen. Spending them here rather than at each navigation site,
    // because every site is one somebody has to remember.
    consumeOverlayEntriesForNavigation();
    window.history.replaceState(
      window.history.state,
      "",
      `${url.pathname}${url.search}`,
    );
  } catch {
    // URL state is optional recovery metadata.
  }
}

export function clearActiveConversationPointer(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(window.location.href);
    if (!CHAT_SHELL_PATHS.has(url.pathname)) return null;
    if (!url.searchParams.has(ACTIVE_CONVERSATION_QUERY_KEY)) return null;
    url.searchParams.delete(ACTIVE_CONVERSATION_QUERY_KEY);
    url.searchParams.delete(ACTIVE_MESSAGE_QUERY_KEY);
    const query = url.searchParams.toString();
    const nextRoute = query ? `${url.pathname}?${query}` : url.pathname;
    consumeOverlayEntriesForNavigation();
    window.history.replaceState(window.history.state, "", nextRoute);
    return nextRoute;
  } catch {
    return null;
  }
}

export function isCurrentAnchoredConversationRequest({
  activeConversationId,
  targetConversationId,
  routeState,
  requestedMessageId,
}: {
  activeConversationId: string | null;
  targetConversationId: string;
  routeState: ActiveConversationRouteState;
  requestedMessageId: string;
}): boolean {
  return (
    activeConversationId === targetConversationId &&
    routeState.isChatRoute &&
    routeState.conversationId === targetConversationId &&
    routeState.messageId === requestedMessageId
  );
}

export function shouldStartConversationForVisibleEmptyChat({
  routeState,
  visibleMessageCount,
  hasStructuredAction,
}: {
  routeState: ActiveConversationRouteState;
  visibleMessageCount: number;
  hasStructuredAction: boolean;
}) {
  return (
    routeState.isNewChatRoute &&
    visibleMessageCount === 0 &&
    !hasStructuredAction
  );
}

export function shouldApplyConversationScopedUpdate({
  targetConversationId,
  activeConversationId,
  currentView,
  routeState,
}: {
  targetConversationId: string | null | undefined;
  activeConversationId: string | null | undefined;
  currentView: string;
  routeState: ActiveConversationRouteState;
}) {
  const target = targetConversationId?.trim();
  if (
    !shouldApplyConversationOwnedUpdate({
      targetConversationId: target,
      activeConversationId,
    })
  ) {
    return false;
  }
  return (
    currentView === "chat" &&
    routeState.isChatRoute &&
    routeState.conversationId?.trim() === target
  );
}

export function shouldApplyConversationOwnedUpdate({
  targetConversationId,
  activeConversationId,
}: {
  targetConversationId: string | null | undefined;
  activeConversationId: string | null | undefined;
}) {
  const target = targetConversationId?.trim();
  return Boolean(target && activeConversationId?.trim() === target);
}

export function shouldApplyConversationRequestUpdate({
  targetConversationId,
  requestId,
  currentRequestId,
  scope,
  activeConversationId,
  currentView,
  routeState,
}: {
  targetConversationId: string | null | undefined;
  requestId: string | null | undefined;
  currentRequestId: string | null | undefined;
  scope: "request" | "visible";
  activeConversationId: string | null | undefined;
  currentView: string;
  routeState: ActiveConversationRouteState;
}): boolean {
  const target = targetConversationId?.trim();
  const request = requestId?.trim();
  if (!target || !request || request !== currentRequestId?.trim()) {
    return false;
  }
  if (scope === "request") {
    return true;
  }
  return shouldApplyConversationScopedUpdate({
    targetConversationId: target,
    activeConversationId,
    currentView,
    routeState,
  });
}

export function actionConversationId(action: ChatActionOption | null | undefined) {
  const rawConversationId =
    action?.payload?.conversation_id ?? action?.payload?.conversationId;
  if (typeof rawConversationId !== "string") return null;
  return rawConversationId.trim() || null;
}

export function targetConversationIdForSend({
  routeConversationId,
  stateConversationId,
  action,
}: {
  routeConversationId: string | null | undefined;
  stateConversationId: string | null | undefined;
  action: ChatActionOption | null | undefined;
}) {
  return (
    actionConversationId(action) ??
    routeConversationId?.trim() ??
    stateConversationId?.trim() ??
    null
  );
}
