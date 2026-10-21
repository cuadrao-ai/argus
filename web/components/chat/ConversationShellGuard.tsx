"use client";

import { useEffect } from "react";
import { conversationExitHref, registerConversationShell } from "@/lib/conversation-surface-guard";
import { useConversationSurface } from "./ChatWorkspace";

/** Sends a conversation opened in the wrong shell to its own, by its backend surface; on a Business build a Personal one goes nowhere but the notice. */
export default function ConversationShellGuard() {
  const surface = useConversationSurface();
  useEffect(
    () =>
      registerConversationShell({
        surface,
        open: (conversationId, target) => {
          window.location.replace(conversationExitHref(window.location.href, conversationId, target));
        },
      }),
    [surface],
  );
  return null;
}
