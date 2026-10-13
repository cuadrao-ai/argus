"use client";

import { useEffect, useState, type Dispatch, type RefObject, type SetStateAction } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import { getMe, listConversations } from "@/lib/argus-api";
import { guestProfileProbeOutcome } from "@/lib/guest-account";
import { readActiveConversationRouteState } from "@/lib/chat-conversation-routing";
import { currentAuthLoginPath } from "@/lib/landing-intent";
import { CONVERSATION_UNAVAILABLE } from "@/lib/conversation-surface-guard";
import { useConversationSurface } from "./ChatWorkspace";
import type { Message } from "./types";

export type ProfileState =
  | "probing"
  | "established"
  | "bootstrap_required"
  | "expired"
  | "unavailable";

type Account = Awaited<ReturnType<typeof getMe>>;

type InitialChatSessionOptions = {
  hasAcceptedUserInputRef: RefObject<boolean>;
  setAccount: Dispatch<SetStateAction<Account | null>>;
  setProfileState: Dispatch<SetStateAction<ProfileState>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setIsHydratingConversation: Dispatch<SetStateAction<boolean>>;
  resetToEmptyChatSurface: () => void;
  navigateConversationTranscript: (
    conversationId: string,
    userId: string,
    options: Readonly<{ bootstrap: boolean; messageId?: string }>,
  ) => Promise<void>;
  cancelActiveNavigation: () => void;
};

/**
 * A guest's latest Personal conversation is picked only on the Personal shell
 * and never on the notice address: on the Business shell that pick would send
 * the conversation to the notice and the next load would pick it again.
 */
export function guestAutoPickAllowed(surface: string, search: string = typeof window === "undefined" ? "" : window.location.search): boolean {
  if (surface === "business") return false;
  return new URLSearchParams(search.startsWith("?") ? search.slice(1) : search).get("notice") !== CONVERSATION_UNAVAILABLE;
}

export function useInitialChatSession({
  hasAcceptedUserInputRef,
  setAccount,
  setProfileState,
  setMessages,
  setIsHydratingConversation,
  resetToEmptyChatSurface,
  navigateConversationTranscript,
  cancelActiveNavigation,
}: InitialChatSessionOptions): boolean {
  const [initialRoutingSettled, setInitialRoutingSettled] = useState(false);
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const surface = useConversationSurface();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let meResponse: Awaited<ReturnType<typeof getMe>> | null = null;
        let probeOutcome: ReturnType<typeof guestProfileProbeOutcome> | null = null;
        try {
          meResponse = await getMe();
          if (meResponse === null) probeOutcome = "fail_closed";
          if (!cancelled) setAccount(meResponse);
        } catch (error) {
          probeOutcome = guestProfileProbeOutcome(error);
        }
        const resolvedLanguage = meResponse?.user?.language ?? i18n.language;
        if (resolvedLanguage && resolvedLanguage !== i18n.language) {
          await i18n.changeLanguage(resolvedLanguage);
        }
        if (cancelled) return;
        if (probeOutcome === null) {
          setProfileState("established");
        } else if (probeOutcome === "bootstrap_required") {
          setProfileState("bootstrap_required");
        } else if (probeOutcome === "fail_closed") {
          setProfileState("unavailable");
          router.replace(currentAuthLoginPath());
          return;
        }
        if (hasAcceptedUserInputRef.current) return;
        const activeRoute = readActiveConversationRouteState();
        let activeConversationId = activeRoute.conversationId;
        if (!activeConversationId && meResponse?.account_kind === "guest" && guestAutoPickAllowed(surface)) {
          // Guests have no Business space, so this is always the Personal list.
          const { items } = await listConversations({ limit: 2 });
          if (cancelled || hasAcceptedUserInputRef.current) return;
          activeConversationId = items[0]?.id ?? null;
        }
        if (activeConversationId) {
          const userId = meResponse?.user.id;
          if (!userId) {
            resetToEmptyChatSurface();
            setInitialRoutingSettled(true);
            return;
          }
          await navigateConversationTranscript(activeConversationId, userId, {
            bootstrap: true,
            messageId: activeRoute.messageId ?? undefined,
          });
          if (!cancelled) setInitialRoutingSettled(true);
          return;
        }

        if (cancelled || hasAcceptedUserInputRef.current) return;
        resetToEmptyChatSurface();
        setInitialRoutingSettled(true);
      } catch {
        if (cancelled) return;
        setProfileState("unavailable");
        router.replace(currentAuthLoginPath());
        setMessages([
          {
            id: "offline",
            role: "ai",
            kind: "text",
            content: t("chat.error_offline"),
          },
        ]);
        setIsHydratingConversation(false);
      }
    })();
    return () => {
      cancelled = true;
      cancelActiveNavigation();
    };
    // Bootstraps the active conversation once; re-running on callback or i18n updates would create noisy chat reloads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return initialRoutingSettled;
}
