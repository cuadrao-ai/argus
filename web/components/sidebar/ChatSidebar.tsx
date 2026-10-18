"use client";

import type { LogoutOptions } from "@/lib/account-deletion-api";
import { conversationPreviewText } from "@/lib/conversation-preview-display";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useChatWorkspace, useChatAvailable, useConversationSurface, type ChatShellView } from "@/components/chat/ChatWorkspace";
import {
  ChevronDown,
  History,
  MessageCirclePlus,
  Pin,
  Search,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  ConversationActivityIndicator,
  conversationActivityLabelDescriptor,
  useConversationActivityPresentation,
} from "@/components/chat/ConversationActivityIndicator";
import { QuickJumpBadge } from "@/components/keyboard/QuickJumpBadge";
import { useQuickJump } from "@/components/keyboard/useQuickJump";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import SidebarNavButton from "./SidebarNavButton";
import SidebarHeader, { type SidebarVariant } from "./SidebarHeader";
import ProfileMenu from "./ProfileMenu";
import RecentChatActions from "./RecentChatActions";
import {
  deleteAllConversations,
  patchConversation,
  deleteConversation as apiDeleteConversation,
} from "@/lib/argus-api";
import {
  conversationDisplayTitle,
  renamePrefillTitle,
} from "@/lib/chat-title-display";
import {
  isKeyboardShortcutHintModifierActive,
  keyboardShortcutHintDisplay,
} from "@/lib/keyboard-shortcuts";
import {
  RECENTS_INITIAL_GROUP_LIMIT,
  getVisibleRecentChats,
  groupRecentChats,
  type RecentChatGroupKey,
} from "@/lib/chat-recents";

import type { ApiUser, HistoryItem, SearchConversationItem } from "@/lib/argus-api";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { sidebarShortcutHintsVisible } from "@/lib/sidebar-shortcuts";

// ─── Types ────────────────────────────────────────────────────────────────────

export type SidebarMode = "expanded" | "collapsed" | "hover";

type View = ChatShellView;

type ConversationActivityReadOwner = Readonly<{
  hasEffectiveUnread: (conversationId: string) => boolean;
  selectAttentionCursor: (conversationId: string) => string | null;
  markRead: (conversationId: string, cursor: string | null) => Promise<void>;
  markUnread: (conversationId: string) => Promise<void>;
  isMutationPending: (
    conversationId: string,
    action: "mark_read" | "mark_unread",
  ) => boolean;
}>;

export type ChatSidebarProps = {
  /** Whether the sidebar is expanded or collapsed */
  isOpen: boolean;
  onToggle: () => void;

  /** Sidebar behavior mode */
  mode?: SidebarMode;

  /** Currently active view */
  currentView: View;

  /** Currently active conversation id (used for highlighting) */
  conversationId: string | null;
  conversationActivity: ConversationActivityReadOwner;

  // ── Recents ──────────────────────────────────────────────────────────────
  /** Whether the Recents accordion is expanded */
  isRecentsExpanded: boolean;
  onToggleRecents: () => void;
  /** History items for the Recents list */
  historyItems: HistoryItem[];
  /** Whether more history pages are available */
  historyNextCursor: string | null;
  /** Whether a history page load is in progress */
  isLoadingMoreHistory: boolean;
  /** Whether the user has explicitly requested at least one older page */
  hasRequestedOlderHistory: boolean;
  /** Whether the latest explicit history-page request failed */
  historyLoadMoreError: boolean;

  // ── Callbacks ────────────────────────────────────────────────────────────
  onNewChat: () => void;
  onNavigate: (view: View) => void;
  onOpenItem: (item: HistoryItem | SearchConversationItem) => void;
  onLoadMoreHistory: () => void;
  onOpenSearch: () => void;
  /** Callback when a chat is mutated (pin/archive/delete/rename) so parent can refresh */
  onHistoryMutated?: () => void;
  /** Callback when a profile setting is saved, so the shell's account copy follows */
  onProfileUpdated?: (user: ApiUser) => void;
  /** Callback when archive/delete removes a chat from the active recents surface */
  onConversationRemoved?: (conversationId: string) => void;
  /** Callback when every non-deleted conversation is moved to Recently Deleted */
  onAllConversationsDeleted?: () => void;
  /** User-facing toast presenter owned by the chat shell */
  onToast?: (message: string) => void;
  /** Logout handler */
  onLogout: (options?: LogoutOptions) => void;
  /** Feedback handler */
  onFeedback?: (type: "bug" | "feature" | "general") => void;
  /** Sidebar preference handler */
  onOpenSidebarPreference?: () => void;
  onOpenKeyboardShortcuts?: () => void;
  settingsOpenRequest?: number;
  omnisearchEnabled?: boolean;
  /** Keep background shortcut hints visually quiet while a foreground surface owns focus. */
  shortcutHintsSuppressed?: boolean;
  canManageConversation?: boolean;
  showProfileMenu?: boolean;
  isGuest?: boolean;
  guestExpiresAt?: string | null;
  /** Rail on desktop, off-canvas drawer below the mobile threshold. */
  variant?: SidebarVariant;
  /** Drawer only: the X in the sidebar header dismisses the panel. */
  onRequestClose?: () => void;
  /** Guest settings entry point, which lives at the drawer bottom. */
  guestSettings?: ReactNode;
  /** A workspace's own destinations, between Search and Recents. */
  primaryNav?: ReactNode;
  /** Rendered directly under the lockup, before any nav entry. */
  headerSlot?: ReactNode;
  /** A workspace's actions, pinned above the profile footer. */
  footerActions?: ReactNode;
  /**
   * When set, the profile trigger and menu render into this header element
   * instead of the footer. The sidebar stays the one owner of profile state.
   */
  profileSlot?: HTMLElement | null;
};

function historyConversationId(item: HistoryItem): string {
  return item.conversation_id ?? item.id;
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ChatSidebar({
  isOpen,
  onToggle,
  mode = "expanded",
  currentView,
  conversationId,
  conversationActivity,
  isRecentsExpanded,
  onToggleRecents,
  historyItems,
  historyNextCursor,
  isLoadingMoreHistory,
  hasRequestedOlderHistory,
  historyLoadMoreError,
  onNewChat,
  onNavigate,
  onOpenItem,
  onLoadMoreHistory,
  onOpenSearch,
  onHistoryMutated,
  onProfileUpdated,
  onConversationRemoved,
  onAllConversationsDeleted,
  onToast,
  onLogout,
  onFeedback,
  onOpenSidebarPreference,
  onOpenKeyboardShortcuts,
  settingsOpenRequest = 0,
  omnisearchEnabled = false,
  shortcutHintsSuppressed = false,
  canManageConversation = true,
  showProfileMenu = true,
  isGuest = false,
  guestExpiresAt = null,
  variant = "rail",
  onRequestClose,
  guestSettings = null,
  primaryNav = null,
  headerSlot = null,
  footerActions = null,
  profileSlot = null,
}: ChatSidebarProps) {
  const { t, i18n } = useTranslation();
  const surface = useConversationSurface();
  const chatAvailable = useChatAvailable();
  const workspaceShortcuts = useChatWorkspace()?.keyboardShortcuts;
  const { selectPresentation, selectAggregatePresentation, selectOperationLabel } =
    useConversationActivityPresentation();
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDeleteAllDialogOpen, setIsDeleteAllDialogOpen] = useState(false);
  const [isDeletingAllConversations, setIsDeletingAllConversations] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [expandedRecentGroups, setExpandedRecentGroups] = useState<
    Set<RecentChatGroupKey>
  >(() => new Set());
  const [usesCommandKey, setUsesCommandKey] = useState(false);
  const [showShortcutHints, setShowShortcutHints] = useState(false);
  const shortcutHintsVisible = sidebarShortcutHintsVisible({
    modifierHeld: showShortcutHints,
    suppressed: shortcutHintsSuppressed,
    variant,
  });
  const profileButtonRef = useRef<HTMLElement | null>(null);
  const previousSettingsOpenRequestRef = useRef(settingsOpenRequest);
  const hoverTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isPointerInsideSidebarRef = useRef(false);

  // ─── Hover Logic ────────────────────────────────────────────────────────────

  const handleMouseEnter = () => {
    isPointerInsideSidebarRef.current = true;
    if (mode !== "hover") return;
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    
    hoverTimeoutRef.current = setTimeout(() => {
      if (!isOpen) {
        onToggle();
      }
    }, 300);
  };

  const handleMouseLeave = () => {
    isPointerInsideSidebarRef.current = false;
    if (mode !== "hover") return;
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    if (isProfileMenuOpen) return;
    
    hoverTimeoutRef.current = setTimeout(() => {
      if (isOpen) {
        onToggle();
      }
    }, 300);
  };

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    };
  }, []);

  useEffect(() => {
    if (
      mode === "hover" &&
      isOpen &&
      !isProfileMenuOpen &&
      !isPointerInsideSidebarRef.current
    ) {
      hoverTimeoutRef.current = setTimeout(() => {
        onToggle();
      }, 300);
    }
    return () => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    };
  }, [isProfileMenuOpen, isOpen, mode, onToggle]);

  useEffect(() => {
    setUsesCommandKey(
      /Mac|iPhone|iPad|iPod/.test(navigator.userAgent),
    );
  }, []);

  useEffect(() => {
    if (!isOpen) {
      setShowShortcutHints(false);
      return;
    }

    const updateShortcutHints = (event: KeyboardEvent) => {
      setShowShortcutHints(
        isKeyboardShortcutHintModifierActive(event, usesCommandKey),
      );
    };
    const hideShortcutHints = () => setShowShortcutHints(false);

    document.addEventListener("keydown", updateShortcutHints);
    document.addEventListener("keyup", updateShortcutHints);
    window.addEventListener("blur", hideShortcutHints);
    return () => {
      document.removeEventListener("keydown", updateShortcutHints);
      document.removeEventListener("keyup", updateShortcutHints);
      window.removeEventListener("blur", hideShortcutHints);
    };
  }, [isOpen, usesCommandKey]);

  useEffect(() => {
    if (settingsOpenRequest === previousSettingsOpenRequestRef.current) return;
    previousSettingsOpenRequestRef.current = settingsOpenRequest;
    setIsProfileMenuOpen(true);
  }, [settingsOpenRequest]);

  // ── Filter to chats only ────────────────────────────────────────────────
  const chatItems = useMemo(
    () => historyItems.filter((item) => item.type === "chat"),
    [historyItems],
  );
  const loadedConversationIds = useMemo(
    () => chatItems.map(historyConversationId),
    [chatItems],
  );
  const aggregateActivityPresentation = selectAggregatePresentation(loadedConversationIds);

  // ── Date-grouped history ────────────────────────────────────────────────
  const groupedHistory = useMemo(
    () => groupRecentChats(chatItems),
    [chatItems],
  );

  const toggleRecentGroup = useCallback((groupKey: RecentChatGroupKey) => {
    setExpandedRecentGroups((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) {
        next.delete(groupKey);
      } else {
        next.add(groupKey);
      }
      return next;
    });
  }, []);

  const visibleRecentItems = useMemo(
    () =>
      groupedHistory.flatMap((group) =>
        getVisibleRecentChats(group, {
          expanded: expandedRecentGroups.has(group.key),
          selectedConversationId: conversationId,
        }),
      ),
    [conversationId, expandedRecentGroups, groupedHistory],
  );
  const quickJumpRecentItems = useMemo(
    () =>
      visibleRecentItems.map((item) => ({
        id: historyConversationId(item),
        pinned: item.pinned,
      })),
    [visibleRecentItems],
  );
  const handleQuickJumpRecent = useCallback(
    (id: string) => {
      const item = visibleRecentItems.find(
        (candidate) => historyConversationId(candidate) === id,
      );
      if (item) onOpenItem(item);
    },
    [onOpenItem, visibleRecentItems],
  );
  const { isQuickJumpActive, numberFor } = useQuickJump({
    enabled:
      chatAvailable && !workspaceShortcuts &&
      isOpen &&
      isRecentsExpanded &&
      renamingId === null &&
      !isProfileMenuOpen,
    items: quickJumpRecentItems,
    onSelect: handleQuickJumpRecent,
    usesCommandKey,
  });

  // ── Chat actions ────────────────────────────────────────────────────────
  const handlePin = useCallback(async (id: string, pinned: boolean) => {
    try {
      await patchConversation(id, { pinned });
      onHistoryMutated?.();
    } catch (err) {
      console.error("Failed to pin/unpin conversation", err);
    }
  }, [onHistoryMutated]);

  const handleArchive = useCallback(async (id: string) => {
    onConversationRemoved?.(id);
    try {
      await patchConversation(id, { archived: true });
      onHistoryMutated?.();
    } catch (err) {
      console.error("Failed to archive conversation", err);
      onHistoryMutated?.();
    }
  }, [onConversationRemoved, onHistoryMutated]);

  const handleRequestDelete = useCallback((id: string) => {
    setPendingDeleteId(id);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDeleteId || isDeleting) return;
    setIsDeleting(true);
    onConversationRemoved?.(pendingDeleteId);
    try {
      await apiDeleteConversation(pendingDeleteId);
      onHistoryMutated?.();
    } catch (err) {
      console.error("Failed to delete conversation", err);
      onHistoryMutated?.();
    } finally {
      setIsDeleting(false);
      setPendingDeleteId(null);
    }
  }, [isDeleting, onConversationRemoved, onHistoryMutated, pendingDeleteId]);

  const handleRequestDeleteAllConversations = useCallback(() => {
    setIsProfileMenuOpen(false);
    setIsDeleteAllDialogOpen(true);
  }, []);

  const handleConfirmDeleteAllConversations = useCallback(async () => {
    if (isDeletingAllConversations) return;
    setIsDeletingAllConversations(true);
    try {
      const response = await deleteAllConversations(surface);
      setIsDeleteAllDialogOpen(false);
      if (response.deleted_count > 0) {
        onAllConversationsDeleted?.();
        onToast?.(t("settings.data.delete_all_success", {
          count: response.deleted_count,
          defaultValue_one: "Moved {{count}} conversation to Recently Deleted.",
          defaultValue_other: "Moved {{count}} conversations to Recently Deleted.",
        }));
      } else {
        onHistoryMutated?.();
        onToast?.(t(
          "settings.data.delete_all_empty",
          "No conversations to delete.",
        ));
      }
    } catch {
      onToast?.(t(
        "settings.data.delete_all_error",
        "Couldn’t delete conversations. Try again.",
      ));
    } finally {
      setIsDeletingAllConversations(false);
    }
  }, [
    isDeletingAllConversations,
    onAllConversationsDeleted,
    onHistoryMutated,
    onToast,
    surface,
    t,
  ]);

  const handleStartRename = useCallback((id: string) => {
    const item = chatItems.find((i) => i.id === id);
    setRenamingId(id);
    setRenameValue(renamePrefillTitle(item));
    setRenameError(null);
  }, [chatItems]);

  const handleSaveRename = useCallback(async () => {
    if (!renamingId) return;
    const trimmed = renameValue.trim();
    setRenameError(null);
    if (!trimmed) {
      setRenamingId(null);
      return;
    }
    try {
      await patchConversation(renamingId, { title: trimmed });
      onHistoryMutated?.();
    } catch (err) {
      console.error("Failed to rename conversation", err);
      setRenameError(t("chat.rename_failed", "Could not rename this chat. Try again."));
      return;
    }
    setRenamingId(null);
  }, [renamingId, renameValue, onHistoryMutated, t]);

  const handleCancelRename = useCallback(() => {
    setRenamingId(null);
    setRenameError(null);
  }, []);

  const pendingDeleteItem = useMemo(
    () => chatItems.find((item) => item.id === pendingDeleteId) ?? null,
    [chatItems, pendingDeleteId],
  );

  const isDrawer = variant === "drawer";
  // No rail exists in drawer mode, so its preference entry is absent, not greyed.
  const sidebarPreferenceHandler = isDrawer ? undefined : onOpenSidebarPreference;

  return (
    <aside
      onMouseEnter={isDrawer ? undefined : handleMouseEnter}
      onMouseLeave={isDrawer ? undefined : handleMouseLeave}
      className={
        isDrawer
          ? "flex h-full w-full flex-col border-r border-black/5 bg-white dark:border-white/5 dark:bg-[#141517]"
          : `flex shrink-0 flex-col border-r border-black/5 bg-white transition-[width] duration-300 ease-in-out overflow-hidden will-change-[width] dark:border-white/5 dark:bg-[#141517] ${
              isOpen ? "w-72" : "w-14"
            }`
      }
    >
      <SidebarHeader
        variant={variant}
        isOpen={isOpen}
        onToggle={onToggle}
        onRequestClose={onRequestClose}
      />

      {headerSlot}

      <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden px-[6px] pb-4 pt-2">
        {/* Main Navigation */}
        {chatAvailable && !workspaceShortcuts && (
          <SidebarNavButton
            icon={MessageCirclePlus}
            label={t("chat.new_chat")}
            collapsed={!isOpen}
            shortcutHint={keyboardShortcutHintDisplay("new_chat", usesCommandKey)}
            showShortcutHint={shortcutHintsVisible}
            onClick={() => {
              onNewChat();
            }}
            iconSize={20}
          />
        )}

        {omnisearchEnabled && (
          <SidebarNavButton
            icon={Search}
            label={t("common.search", "Search")}
            collapsed={!isOpen}
            shortcutHint={keyboardShortcutHintDisplay("omnisearch", usesCommandKey)}
            showShortcutHint={Boolean(workspaceShortcuts) || shortcutHintsVisible}
            onClick={onOpenSearch}
            iconSize={20}
          />
        )}

        {primaryNav}

        {/* Recents Accordion */}
        {chatAvailable && !workspaceShortcuts && (
          <div className="mb-2 mt-2">
            <SidebarNavButton
              icon={History}
              label={t("common.recents")}
              collapsed={!isOpen}
              activityPresentation={aggregateActivityPresentation}
              shortcutHint={keyboardShortcutHintDisplay(
                "expand_sidebar_recents",
                usesCommandKey,
              )}
              showShortcutHint={shortcutHintsVisible}
              onClick={() => {
                if (!isOpen) {
                  // When collapsed: expand sidebar + open recents
                  onToggle();
                  if (!isRecentsExpanded) onToggleRecents();
                } else {
                  onToggleRecents();
                }
              }}
              trailing={
                <ChevronDown
                  className={`h-4 w-4 text-black/40 transition-transform duration-200 dark:text-white/40 ${
                    isRecentsExpanded ? "rotate-180" : ""
                  }`}
                />
              }
            />

            {isRecentsExpanded && isOpen && (
              <div className="max-h-[50vh] overflow-y-auto pb-2">
                <div className="flex flex-col gap-4 pb-2">
                {chatItems.length === 0 ? (
                  <div className="px-11 py-6">
                    <p className="text-[13px] leading-relaxed text-black/30 dark:text-white/30">
                      {t("chat.no_recent_activity")}
                    </p>
                  </div>
                ) : (
                  <>
                    {groupedHistory.map((group) => {
                      const groupLabel = t(`chat.history.${group.key}`);
                      const groupHeadingId = `recents-${group.key}-heading`;
                      const groupItemsId = `recents-${group.key}-items`;
                      const isGroupExpanded = expandedRecentGroups.has(group.key);
                      const canToggleGroup =
                        !group.isPinned &&
                        group.items.length > RECENTS_INITIAL_GROUP_LIMIT;
                      const visibleItems = getVisibleRecentChats(group, {
                        expanded: isGroupExpanded,
                        selectedConversationId: conversationId,
                      });

                      return (
                        <section
                          key={group.key}
                          aria-labelledby={groupHeadingId}
                          className="flex flex-col"
                        >
                          <div className="px-11 py-2">
                            <h3
                              id={groupHeadingId}
                              className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-black/40 dark:text-white/40"
                            >
                              {group.isPinned && (
                                <Pin className="h-3 w-3" />
                              )}
                              {groupLabel}
                            </h3>
                          </div>
                          <div id={groupItemsId}>
                          {visibleItems.map((item) => {
                          const itemConversationId = historyConversationId(item);
                          const isActiveConversation = conversationId === itemConversationId;
                          const isUnread = conversationActivity.hasEffectiveUnread(itemConversationId);
                          const isReadMutationPending = isUnread
                            ? conversationActivity.isMutationPending(itemConversationId, "mark_read")
                            : conversationActivity.isMutationPending(itemConversationId, "mark_unread");
                          const itemActivityPresentation = selectPresentation(itemConversationId);
                          const itemOperationLabel = selectOperationLabel(itemConversationId);
                          const displayTitle = conversationDisplayTitle(
                            item,
                            t("chat.new_chat", "New chat"),
                          );
                          const activityLabel = conversationActivityLabelDescriptor(
                            itemActivityPresentation,
                            itemOperationLabel,
                          );
                          const rowAriaLabel = activityLabel
                            ? `${displayTitle}. ${t(activityLabel.key, activityLabel.defaultValue)}.`
                            : displayTitle;
                          const conversationActionItem =
                            item.id === itemConversationId ? item : { ...item, id: itemConversationId };
                          const expiresAt = item.expires_at ?? guestExpiresAt;
                          const quickJumpNumber = numberFor(itemConversationId);
                          const quickJumpHint =
                            isQuickJumpActive && quickJumpNumber !== null ? (
                              <span
                                data-quick-jump-hint={quickJumpNumber}
                                className="pointer-events-none flex h-[22px] items-center justify-end"
                              >
                                <QuickJumpBadge
                                  number={quickJumpNumber}
                                  presentation="shortcut_hint"
                                  usesCommandKey={usesCommandKey}
                                />
                              </span>
                            ) : null;

                          return (
                            <div
                              key={`chat:${item.id}`}
                              role="button"
                              tabIndex={0}
                              aria-label={rowAriaLabel}
                              aria-current={isActiveConversation ? "page" : undefined}
                              data-active-conversation={isActiveConversation ? "true" : undefined}
                              data-conversation-id={itemConversationId}
                              onClick={(e) => {
                                // Only navigate if click was on this element or its text children,
                                // not on nested interactive elements (three-dot menu)
                                const target = e.target as HTMLElement;
                                if (target.closest('[data-actions]')) return;
                                if (renamingId !== item.id) {
                                  onOpenItem(item);
                                }
                              }}
                              onKeyDown={(e) => {
                                if (
                                  (e.key === "Enter" || e.key === " ") &&
                                  e.target === e.currentTarget &&
                                  renamingId !== item.id
                                ) {
                                  e.preventDefault();
                                  onOpenItem(item);
                                }
                              }}
                              className={`group relative flex w-full cursor-pointer items-center gap-3 rounded-[14px] px-0 py-2 transition-all duration-200 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/30 focus-visible:ring-offset-1 dark:hover:bg-white/5 dark:focus-visible:ring-white/40 dark:focus-visible:ring-offset-[#141517] ${
                                isActiveConversation ? "bg-black/5 dark:bg-white/5" : ""
                              }`}
                            >
                            <div className="flex h-6 w-11 flex-shrink-0 items-center justify-center">
                              <ConversationActivityIndicator
                                presentation={itemActivityPresentation}
                              />
                            </div>
                            <div
                              className={`min-w-0 flex-1 pl-3 ${
                                quickJumpHint ? "pr-[104px]" : "pr-10"
                              }`}
                            >
                              {renamingId === item.id ? (
                                <>
                                  <input
                                    autoFocus
                                    type="text"
                                    value={renameValue}
                                    onChange={(e) => setRenameValue(e.target.value.slice(0, 80))}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        void handleSaveRename();
                                      } else if (e.key === "Escape") {
                                        handleCancelRename();
                                      }
                                    }}
                                    onBlur={() => void handleSaveRename()}
                                    onClick={(e) => e.stopPropagation()}
                                    aria-invalid={Boolean(renameError)}
                                    className="w-full rounded-md border border-black/20 bg-transparent px-1.5 py-0.5 text-[14px] font-medium outline-none focus:border-black/40 dark:border-white/20 dark:focus:border-white/40"
                                    maxLength={80}
                                  />
                                  {renameError && (
                                    <p className={`mt-1 text-[11px] font-medium ${inlineFailureTextClass}`} role="alert">
                                      {renameError}
                                    </p>
                                  )}
                                </>
                              ) : (
                                <>
                                  <span
                                    key={displayTitle}
                                    className="font-display block truncate text-[14px] font-medium tracking-tight text-black dark:text-white animate-in fade-in duration-300"
                                  >
                                    {displayTitle}
                                  </span>
                                  <span className="mt-0.5 block truncate text-[12px] text-black/40 dark:text-white/40">
                                    {conversationPreviewText(item.preview, t)}
                                  </span>
                                  {isGuest && expiresAt ? (
                                    <time
                                      dateTime={expiresAt}
                                      title={expiresAt}
                                      className="mt-0.5 block truncate text-[11px] text-black/35 dark:text-white/35"
                                    >
                                      {t("guest.history.expires_at", {
                                        defaultValue: "Available until {{date}}",
                                        date: new Intl.DateTimeFormat(
                                          i18n.resolvedLanguage ?? i18n.language,
                                          {
                                            dateStyle: "medium",
                                            timeStyle: "short",
                                          },
                                        ).format(new Date(expiresAt)),
                                      })}
                                    </time>
                                  ) : null}
                                </>
                              )}
                            </div>
                            {renamingId !== item.id &&
                              (canManageConversation || quickJumpHint) && (
                                <div className="absolute right-2 top-1/2 flex h-11 w-[88px] -translate-y-1/2 items-center justify-end">
                                  {canManageConversation ? (
                                    <RecentChatActions
                                      item={conversationActionItem}
                                      onPin={handlePin}
                                      onRename={handleStartRename}
                                      onArchive={handleArchive}
                                      onDelete={handleRequestDelete}
                                      isUnread={isUnread}
                                      isReadMutationPending={isReadMutationPending}
                                      onToggleUnread={() =>
                                        isUnread
                                          ? conversationActivity.markRead(itemConversationId, conversationActivity.selectAttentionCursor(itemConversationId))
                                          : conversationActivity.markUnread(itemConversationId)
                                      }
                                      quickJumpHint={quickJumpHint}
                                    />
                                  ) : (
                                    quickJumpHint
                                  )}
                                </div>
                              )}
                            </div>
                          );
                          })}
                          </div>
                          {canToggleGroup && (
                            <button
                              type="button"
                              aria-controls={groupItemsId}
                              aria-expanded={isGroupExpanded}
                              aria-label={t(
                                isGroupExpanded
                                  ? "chat.history.show_less_in"
                                  : "chat.history.show_more_in",
                                { group: groupLabel },
                              )}
                              onClick={() => toggleRecentGroup(group.key)}
                              className="mx-11 flex min-h-11 items-center rounded-lg text-left text-[12px] font-medium text-black/55 transition-colors hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/30 motion-reduce:transition-none dark:text-white/55 dark:hover:text-white dark:focus-visible:ring-white/40"
                            >
                              {t(
                                isGroupExpanded
                                  ? "chat.history.show_less"
                                  : "chat.history.show_more",
                              )}
                            </button>
                          )}
                        </section>
                      );
                    })}
                  </>
                )}
                    {historyNextCursor && (
                      <div className="px-11">
                        <button
                          type="button"
                          disabled={isLoadingMoreHistory}
                          aria-busy={isLoadingMoreHistory}
                          onClick={onLoadMoreHistory}
                          className="flex min-h-11 w-full items-center rounded-lg text-left text-[12px] font-medium text-black/55 transition-colors hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/30 disabled:cursor-wait disabled:text-black/30 motion-reduce:transition-none dark:text-white/55 dark:hover:text-white dark:focus-visible:ring-white/40 dark:disabled:text-white/30"
                        >
                          {t(
                            isLoadingMoreHistory
                              ? "chat.history.loading_older"
                              : "chat.history.load_older",
                          )}
                        </button>
                      </div>
                    )}
                    {!historyNextCursor &&
                      hasRequestedOlderHistory &&
                      !historyLoadMoreError && (
                        <div className="px-11">
                          <button
                            type="button"
                            disabled
                            className="flex min-h-11 w-full items-center rounded-lg text-left text-[12px] font-medium text-black/30 dark:text-white/30"
                          >
                            {t("chat.history.no_older")}
                          </button>
                        </div>
                      )}
                    {historyLoadMoreError && (
                      <p
                        role="alert"
                        className={`px-11 text-[12px] leading-relaxed ${inlineFailureTextClass}`}
                      >
                        {t("chat.history.load_older_error")}
                      </p>
                    )}
                    {isGuest ? (
                      <p className="px-11 pb-2 text-[12px] leading-relaxed text-black/45 dark:text-white/45">
                        {t(
                          "guest.history.keep_history",
                          "Sign in to keep your history",
                        )}
                      </p>
                    ) : null}
                  </div>
              </div>
            )}
          </div>
        )}
      </div>
      {canManageConversation && (
        <>
          <ConfirmDialog
            isOpen={Boolean(pendingDeleteItem)}
            title={t("sidebar.delete_confirm.title", "Delete this conversation?")}
            description={t(
              "sidebar.delete_confirm.description",
              "This moves “{{title}}” to Recently Deleted. You can restore it before permanent removal.",
              {
                title: pendingDeleteItem
                  ? conversationDisplayTitle(
                      pendingDeleteItem,
                      t("chat.new_chat", "New chat"),
                    )
                  : t("common.conversation", "Conversation"),
              },
            )}
            confirmLabel={t("sidebar.delete_confirm.confirm", "Delete conversation")}
            cancelLabel={t("common.cancel", "Cancel")}
            isBusy={isDeleting}
            onCancel={() => {
              if (!isDeleting) setPendingDeleteId(null);
            }}
            onConfirm={() => void handleConfirmDelete()}
          />
          <ConfirmDialog
            isOpen={isDeleteAllDialogOpen}
            title={t(
              "settings.data.delete_all_confirm.title",
              "Delete all conversations?",
            )}
            description={t(
              "settings.data.delete_all_confirm.description",
              "This moves all active and archived conversations to Recently Deleted. You can restore them before permanent removal.",
            )}
            confirmLabel={t(
              "settings.data.delete_all_confirm.confirm",
              "Delete all conversations",
            )}
            cancelLabel={t("common.cancel", "Cancel")}
            isBusy={isDeletingAllConversations}
            onCancel={() => {
              if (!isDeletingAllConversations) setIsDeleteAllDialogOpen(false);
            }}
            onConfirm={() => void handleConfirmDeleteAllConversations()}
          />
        </>
      )}

      {/* Footer: guest settings live here, since the top bar is already full. */}
      {guestSettings ? (
        <div
          data-testid="sidebar-guest-settings"
          className="border-t border-black/5 p-[6px] dark:border-white/5"
        >
          {guestSettings}
        </div>
      ) : null}

      {footerActions ? (
        <div
          data-testid="sidebar-workspace-actions"
          className="border-t border-black/5 p-[6px] dark:border-white/5"
        >
          {footerActions}
        </div>
      ) : null}

      {showProfileMenu && profileSlot
        ? createPortal(
            <>
              <ProfileMenu
                isOpen={isProfileMenuOpen}
                onClose={() => setIsProfileMenuOpen(false)}
                onLogout={onLogout}
                onFeedback={onFeedback}
                onDeleteAllConversations={handleRequestDeleteAllConversations}
                onHistoryMutated={onHistoryMutated}
                onProfileUpdated={onProfileUpdated}
                onOpenSidebarPreference={sidebarPreferenceHandler}
                onOpenKeyboardShortcuts={onOpenKeyboardShortcuts}
                anchorRef={profileButtonRef}
                sidebarCollapsed={!isOpen}
                placement="header"
              />
              <button
                ref={profileButtonRef as React.RefObject<HTMLButtonElement>}
                type="button"
                data-testid="header-profile-trigger"
                aria-label={t("common.settings")}
                aria-haspopup="menu"
                aria-expanded={isProfileMenuOpen}
                onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
                className="flex h-10 w-10 items-center justify-center rounded-full border border-black/10 bg-white text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:border-white/10 dark:bg-[#1f2225] dark:text-white/70 dark:hover:bg-white/5"
              >
                <User className="h-[18px] w-[18px]" />
              </button>
            </>,
            profileSlot,
          )
        : null}

      {/* Footer: Profile menu trigger */}
      {showProfileMenu && !profileSlot ? (
        <div className="relative border-t border-black/5 p-[6px] dark:border-white/5">
          <ProfileMenu
            isOpen={isProfileMenuOpen}
            onClose={() => setIsProfileMenuOpen(false)}
            onLogout={onLogout}
            onFeedback={onFeedback}
            onDeleteAllConversations={handleRequestDeleteAllConversations}
            onHistoryMutated={onHistoryMutated}
            onProfileUpdated={onProfileUpdated}
            onOpenSidebarPreference={sidebarPreferenceHandler}
            onOpenKeyboardShortcuts={onOpenKeyboardShortcuts}
            anchorRef={profileButtonRef}
            sidebarCollapsed={!isOpen}
            placement={variant}
          />
          <div ref={profileButtonRef as React.RefObject<HTMLDivElement>}>
            <SidebarNavButton
              icon={User}
              label={t("common.settings")}
              collapsed={!isOpen}
              shortcutHint={keyboardShortcutHintDisplay(
                "open_settings",
                usesCommandKey,
              )}
              showShortcutHint={shortcutHintsVisible}
              onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
              iconSize={20}
            />
          </div>
        </div>
      ) : null}
    </aside>
  );
}
