"use client";

import { useEffect, useState } from "react";
import {
  Archive,
  Loader2,
  RotateCcw,
  } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { conversationPreviewText } from "@/lib/conversation-preview-display";
import { Tooltip } from "@/components/ui/Tooltip";
import { listConversations, patchConversation, type Conversation } from "@/lib/argus-api";

type ArchivedChatsViewProps = {
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
  onRestored?: () => void;
};

/**
 * Centered blur modal showing archived conversations with restore functionality.
 */
export default function ArchivedChatsView({ onClose, onBack, backLabel, onRestored }: ArchivedChatsViewProps) {
  const { t } = useTranslation();
  const [archivedChats, setArchivedChats] = useState<Conversation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const surface = useConversationSurface();

  useEffect(() => {
    listConversations({ archived: true, surface })
      .then(({ items }) => setArchivedChats(items))
      .finally(() => setIsLoading(false));
  }, [surface]);

  const handleUnarchive = async (id: string) => {
    try {
      await patchConversation(id, { archived: false });
      setArchivedChats((prev) => prev.filter((c) => c.id !== id));
      onRestored?.();
    } catch (err) {
      console.error("Failed to unarchive", err);
    }
  };

  return (
    <AdaptivePanel
      title={t("settings.data.archived_chats")}
      closeLabel={t("settings.data.close_archived", "Close archived chats")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
    >
        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-black/20 dark:text-white/20" />
            </div>
          ) : archivedChats.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
              <div className="w-16 h-16 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center">
                <Archive className="w-8 h-8 text-black/20 dark:text-white/20" />
              </div>
              <p className="text-[15px] text-black/40 dark:text-white/40">
                {t("common.no_items") || "No archived chats"}
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {archivedChats.map((chat) => (
                <div
                  key={chat.id}
                  className="group flex items-center justify-between p-4 bg-black/[0.02] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 rounded-[16px]"
                >
                  <div className="flex flex-col min-w-0 pr-4">
                    <span className="text-[15px] font-medium text-black dark:text-white truncate">
                      {chat.title || t("chat.new_chat")}
                    </span>
                    <span className="text-[13px] text-black/40 dark:text-white/40 truncate">
                      {conversationPreviewText(chat.preview, t)}
                    </span>
                  </div>
                  <Tooltip content={t("common.restore") || "Restore"} side="top">
                    <button
                      onClick={() => void handleUnarchive(chat.id)}
                      className="shrink-0 p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/5 text-black/50 dark:text-white/50 transition-colors"
                      aria-label="Restore"
                    >
                      <RotateCcw className="w-5 h-5" />
                    </button>
                  </Tooltip>
                </div>
              ))}
            </div>
          )}
        </div>
    </AdaptivePanel>
  );
}
