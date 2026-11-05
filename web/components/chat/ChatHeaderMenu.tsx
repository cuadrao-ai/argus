"use client";

import { useEffect, useRef } from "react";
import {
  Edit2,
  EyeOff,
  Mail,
  MailOpen,
  MoreVertical,
  Pin,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { BottomSheet } from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import type { MemoryChrome } from "./memory-chrome";
import ShareReceiptAction, { type ReceiptShareRequest } from "./ShareReceiptAction";
import { evidenceReceiptSharingEnabled } from "@/lib/private-alpha-flags";

type ChatHeaderMenuProps = {
  isOpen: boolean;
  onToggleOpen: () => void;
  onRequestClose: () => void;
  isUnread: boolean;
  isReadMutationPending: boolean;
  onToggleUnread: () => void;
  isRenaming: boolean;
  renameValue: string;
  onRenameValueChange: (value: string) => void;
  onStartRename: () => void;
  onSaveRename: () => void;
  onCancelRename: () => void;
  isSavingRename: boolean;
  pinned: boolean;
  isPinning: boolean;
  onTogglePin: () => void;
  isDeleting: boolean;
  onRequestDelete: () => void;
  /** Memory controls stay invisible unless the backend exposes them. */
  memoryChrome?: MemoryChrome;
  conversationId?: string;
  onShare?: ReceiptShareRequest;
};

/** Header owner menu for the active conversation. */
export default function ChatHeaderMenu({
  isOpen,
  onToggleOpen,
  onRequestClose,
  isUnread,
  isReadMutationPending,
  onToggleUnread,
  isRenaming,
  renameValue,
  onRenameValueChange,
  onStartRename,
  onSaveRename,
  onCancelRename,
  isSavingRename,
  pinned,
  isPinning,
  onTogglePin,
  isDeleting,
  onRequestDelete,
  memoryChrome,
  conversationId,
  onShare,
}: ChatHeaderMenuProps) {
  const { t } = useTranslation();
  // The panel line, not the sidebar's: at tablet width the dossier beside
  // this was already a sheet while this was not.
  const { isBelowDesktop } = useResponsiveLayout();
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        onRequestClose();
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onRequestClose();
        triggerRef.current?.focus();
      }
    }
    // Below the threshold the sheet owns Escape, the scrim, and focus restore.
    if (isOpen && !isBelowDesktop) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isBelowDesktop, isOpen, onRequestClose]);

  const handleToggleUnread = () => {
    onRequestClose();
    onToggleUnread();
  };

  const menuBody = !isRenaming ? (
        <div role="menu" className="py-1">
          <button
            type="button"
            role="menuitem"
            disabled={isReadMutationPending}
            onClick={handleToggleUnread}
            className="mx-2 my-0.5 flex min-h-11 w-[calc(100%-1rem)] items-center gap-4 rounded-[10px] px-6 py-4 text-left text-[16px] font-medium transition-colors hover:bg-black/5 disabled:cursor-wait disabled:opacity-50 dark:hover:bg-white/5 tablet:mx-1 tablet:w-[calc(100%-0.5rem)] tablet:px-3 tablet:py-2 tablet:text-[15px]"
          >
            {isUnread
              ? <MailOpen className="h-[18px] w-[18px] text-black/60 dark:text-white/60 tablet:h-4 tablet:w-4" />
              : <Mail className="h-[18px] w-[18px] text-black/60 dark:text-white/60 tablet:h-4 tablet:w-4" />}
            {isUnread
              ? t("chat.activity.mark_read", "Mark as read")
              : t("chat.activity.mark_unread", "Mark as unread")}
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={isPinning}
            onClick={onTogglePin}
            className="mx-2 my-0.5 flex min-h-11 w-[calc(100%-1rem)] items-center gap-4 rounded-[10px] px-6 py-4 text-left text-[16px] font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/5 tablet:mx-1 tablet:w-[calc(100%-0.5rem)] tablet:px-3 tablet:py-2 tablet:text-[15px]"
          >
            <Pin className="h-[18px] w-[18px] text-black/60 dark:text-white/60 tablet:h-4 tablet:w-4" />
            {pinned
              ? t('chat.unpin_chat', 'Unpin chat')
              : t('chat.pin_chat', 'Pin chat')}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={onStartRename}
            className="mx-2 my-0.5 flex min-h-11 w-[calc(100%-1rem)] items-center gap-4 rounded-[10px] px-6 py-4 text-left text-[16px] font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/5 tablet:mx-1 tablet:w-[calc(100%-0.5rem)] tablet:px-3 tablet:py-2 tablet:text-[15px]"
          >
            <Edit2 className="h-[18px] w-[18px] text-black/60 dark:text-white/60 tablet:h-4 tablet:w-4" />
            {t('chat.rename_chat', 'Rename chat')}
          </button>
          {memoryChrome?.controlsAvailable ? (
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={memoryChrome.optOut}
              onClick={memoryChrome.onToggleOptOut}
              className="mx-2 my-0.5 flex min-h-11 w-[calc(100%-1rem)] items-center gap-4 rounded-[10px] px-6 py-4 text-left text-[16px] font-medium transition-colors hover:bg-black/5 dark:hover:bg-white/5 tablet:mx-1 tablet:w-[calc(100%-0.5rem)] tablet:px-3 tablet:py-2 tablet:text-[15px]"
            >
              <EyeOff className="h-[18px] w-[18px] text-black/60 dark:text-white/60 tablet:h-4 tablet:w-4" />
              {memoryChrome.optOut
                ? t("chat.memory.private_on", "Private chat: on")
                : t("chat.memory.private_off", "Private chat")}
            </button>
          ) : null}
          <div role="separator" className="my-1 h-px bg-black/5 dark:bg-white/5" />
          <button
            type="button"
            role="menuitem"
            disabled={isDeleting}
            onClick={onRequestDelete}
            className="mx-2 my-0.5 flex min-h-11 w-[calc(100%-1rem)] items-center gap-4 rounded-[10px] px-6 py-4 text-left text-[16px] font-medium text-red-500 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-45 dark:hover:bg-red-500/10 tablet:mx-1 tablet:w-[calc(100%-0.5rem)] tablet:px-3 tablet:py-2 tablet:text-[15px]"
          >
            <Trash2 className="h-[18px] w-[18px] tablet:h-4 tablet:w-4" />
            {t('chat.delete_chat', 'Delete')}
          </button>
        </div>
      ) : (
        <form
          className="space-y-2 px-5 py-3"
          onSubmit={(event) => {
            event.preventDefault();
            onSaveRename();
          }}
        >
          <label className="block text-[12px] font-medium text-black/45 dark:text-white/45">
            {t('chat.rename_chat', 'Rename chat')}
          </label>
          <input
            autoFocus
            value={renameValue}
            onChange={(event) => onRenameValueChange(event.target.value.slice(0, 80))}
            className="w-full rounded-[12px] border border-black/10 bg-black/[0.02] px-3 py-2 text-[14px] font-medium text-black outline-none focus:border-black/25 dark:border-white/10 dark:bg-white/[0.04] dark:text-white dark:focus:border-white/25"
            maxLength={80}
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={isSavingRename}
              className="min-h-9 flex-1 rounded-full bg-black px-3 py-1.5 text-[13px] font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-50 dark:bg-white dark:text-black"
            >
              {t('common.save')}
            </button>
            <button
              type="button"
              disabled={isSavingRename}
              onClick={onCancelRename}
              className="min-h-9 flex-1 rounded-full border border-black/10 px-3 py-1.5 text-[13px] font-medium text-black/70 transition-colors hover:bg-black/5 disabled:opacity-50 dark:border-white/10 dark:text-white/70 dark:hover:bg-white/5"
            >
              {t('common.cancel')}
            </button>
          </div>
        </form>
  );

  return (
    <div className="relative flex items-center animate-in fade-in duration-300" ref={containerRef}>
      {evidenceReceiptSharingEnabled && conversationId && onShare && <ShareReceiptAction conversationId={conversationId} onShare={onShare} />}
      <button
        ref={triggerRef}
        type="button"
        onClick={onToggleOpen}
        className="flex h-11 w-11 items-center justify-center rounded-full transition-all duration-200 hover:bg-black/5 dark:hover:bg-white/5 active:scale-95"
        aria-label={t("chat.chat_options", "Chat options")}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <MoreVertical className="h-5 w-5" />
      </button>
      {isOpen && !isBelowDesktop && (
        <div className="absolute bottom-auto right-0 left-auto top-full mt-2 w-[260px] rounded-[20px] border border-black/5 bg-white pb-2 pt-2 dark:border-white/5 dark:bg-[#1f2225]">
          {menuBody}
        </div>
      )}
      {isOpen && isBelowDesktop && (
        <BottomSheet
          isOpen
          snaps="fit"
          titleHidden
          title={t("chat.chat_options", "Chat options")}
          closeLabel={t("common.close", "Close")}
          onClose={onRequestClose}
        >
          {menuBody}
        </BottomSheet>
      )}
    </div>
  );
}
