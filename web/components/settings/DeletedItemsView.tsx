"use client";

import { useEffect, useState } from "react";
import {
  History,
  Loader2,
  MessageSquare,
  RotateCcw,
  } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  listHistory,
  patchConversation,
  type HistoryItem,
} from "@/lib/argus-api";

type DeletedItemsViewProps = {
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
  onRestored?: () => void;
};

function isDeletedItemVisible(item: HistoryItem) {
  return item.type === "chat";
}

export default function DeletedItemsView({ onClose, onBack, backLabel, onRestored }: DeletedItemsViewProps) {
  const { t } = useTranslation();
  const [deletedItems, setDeletedItems] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const surface = useConversationSurface();

  useEffect(() => {
    listHistory({ deleted: true, surface })
      .then(({ items }) => setDeletedItems(items.filter(isDeletedItemVisible)))
      .finally(() => setIsLoading(false));
  }, [surface]);

  const handleRestore = async (item: HistoryItem) => {
    try {
      if (!isDeletedItemVisible(item)) return;
      await patchConversation(item.id, { deleted_at: null });
      setDeletedItems((prev) => prev.filter((i) => i.id !== item.id));
      onRestored?.();
    } catch (err) {
      console.error("Failed to restore", err);
    }
  };

  return (
    <AdaptivePanel
      title={t("settings.data.recently_deleted")}
      closeLabel={t("settings.data.close_deleted", "Close recently deleted")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
    >
      <p className="px-5 pt-3 text-[12px] text-black/40 dark:text-white/40">
        {t(
          "settings.data.deleted_retention_note",
          "Items in this list can currently be restored.",
        )}
      </p>
        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-black/20 dark:text-white/20" />
            </div>
          ) : deletedItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
              <div className="w-16 h-16 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center">
                <History className="w-8 h-8 text-black/20 dark:text-white/20" />
              </div>
              <p className="text-[15px] text-black/40 dark:text-white/40">
                {t("settings.data.no_deleted_items", "No recently deleted items")}
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {deletedItems.map((item) => (
                <div
                  key={item.id}
                  className="group flex items-center justify-between p-4 bg-black/[0.02] dark:bg-white/[0.03] border border-black/5 dark:border-white/5 rounded-[16px]"
                >
                  <div className="flex items-center gap-3 min-w-0 pr-4">
                    <div className="shrink-0 w-8 h-8 rounded-lg bg-black/5 dark:bg-white/5 flex items-center justify-center text-black/40 dark:text-white/40">
                      <MessageSquare className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="text-[15px] font-medium text-black dark:text-white truncate">
                        {item.title}
                      </span>
                      <span className="text-[12px] text-black/40 dark:text-white/40">
                        {t(
                          "settings.data.deleted_item_note",
                          "Currently restorable.",
                        )}
                      </span>
                    </div>
                  </div>
                  <Tooltip content={t("common.restore") || "Restore"} side="top">
                    <button
                      onClick={() => void handleRestore(item)}
                      className="shrink-0 p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/5 text-black/50 dark:text-white/50 transition-colors"
                      aria-label={t("common.restore", "Restore")}
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
