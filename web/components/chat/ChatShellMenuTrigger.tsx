"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { MenuGlyphIcon } from "@/components/chat/MenuGlyphIcon";
import { ConversationActivityIndicator } from "@/components/chat/ConversationActivityIndicator";
import { useChatAvailable } from "@/components/chat/ChatWorkspace";
import type { ConversationActivityPresentation } from "@/lib/conversation-activity-state";

/**
 * Drawer trigger for the mobile top bar (spec section 2).
 *
 * `=` rather than the Argus mark: a brand mark that is also a control is
 * ambiguous, and the mark still gets its reveal moment as the drawer's static
 * logo. Activity aggregates here while the drawer is closed, then propagates to
 * individual rows once it is open.
 */
export default function ChatShellMenuTrigger({
  onOpen,
  activityPresentation,
  leading = null,
}: {
  onOpen: () => void;
  activityPresentation?: ConversationActivityPresentation | null;
  leading?: ReactNode;
}) {
  const { t } = useTranslation();
  const chatAvailable = useChatAvailable();
  if (leading) return leading;

  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="chat-shell-menu-trigger"
      aria-label={t("sidebar.open", "Open sidebar")}
      aria-haspopup="dialog"
      className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 active:scale-95 dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
    >
      <MenuGlyphIcon className="h-5 w-5 text-black/70 dark:text-white/70" aria-hidden="true" />
      {chatAvailable && activityPresentation ? (
        <span className="pointer-events-none absolute right-1.5 top-1.5">
          <ConversationActivityIndicator presentation={activityPresentation} />
        </span>
      ) : null}
    </button>
  );
}
