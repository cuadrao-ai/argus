"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  canManageFocusedConversation,
  canOpenKeyboardShortcuts,
} from "./chatKeyboardShortcutPolicy";
import { hasOpenOverlay } from "@/components/layout/overlayStack";
import { useChatWorkspace, useChatAvailable } from "@/components/chat/ChatWorkspace";
import { KEYBOARD_SHORTCUTS, matchesKeyboardShortcut, matchesWorkspaceShortcut, workspaceKeyboardTargetBlocked } from "@/lib/keyboard-shortcuts";
import { nextSidebarRecentsState } from "@/lib/sidebar-shortcuts";

type UseChatKeyboardShortcutsOptions = {
  /**
   * Whether this width offers keyboard shortcuts at all.
   *
   * Below the mobile threshold the sidebar lives in a drawer that renders
   * nothing while closed, so `open_settings` incremented a request no mounted
   * component was listening for, and reopening the drawer could not replay it
   * because the sidebar starts by treating the current request as already
   * seen. `expand_sidebar_recents` toggled a rail that width does not have.
   * Both keys took the press and gave nothing back.
   *
   * The profile menu already withholds the shortcut sheet there, on the
   * grounds that a phone has no keyboard to shortcut. Registering the keys
   * anyway is the same decision made twice with different answers, so the gate
   * belongs to the whole layer rather than to the two dead entries.
   */
  enabled: boolean;
  requestSearch?: () => void;
  isChatView: boolean;
  canManageConversation: boolean;
  conversationId: string | null;
  isGuest: boolean;
  searchOverlayOpen: boolean;
  deleteConfirmationOpen: boolean;
  modalOpen: boolean;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  recentsExpanded: boolean;
  setRecentsExpanded: (expanded: boolean) => void;
  requestNewChat: () => void;
  closeTransientSidebar: () => void;
  requestDelete: () => void;
  startRename: () => void;
  archiveConversation: () => void | Promise<void>;
  toggleRead: () => void | Promise<void>;
  togglePin: () => void | Promise<void>;
  showChatOptions: () => void;
};

export function useChatKeyboardShortcuts(
  options: UseChatKeyboardShortcutsOptions,
) {
  const { enabled } = options;
  const chatAvailable = useChatAvailable();
  const workspace = useChatWorkspace();
  const workspaceRef = useRef(workspace);
  useLayoutEffect(() => { workspaceRef.current = workspace; }, [workspace]);
  const optionsRef = useRef(options);
  const [keyboardShortcutsOpen, setKeyboardShortcutsOpen] = useState(false);
  const [isRecentsQuickPeekOpen, setIsRecentsQuickPeekOpen] = useState(false);
  const [settingsOpenRequest, setSettingsOpenRequest] = useState(0);

  useEffect(() => {
    optionsRef.current = options;
  });

  // Crossing the threshold with either surface open leaves it on a width that
  // has no way to reopen it and no key to close it.
  useEffect(() => {
    if (enabled) return;
    setKeyboardShortcutsOpen(false);
    setIsRecentsQuickPeekOpen(false);
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const current = optionsRef.current;
      const shortcuts = workspaceRef.current?.keyboardShortcuts;
      if (shortcuts) {
        if (workspaceKeyboardTargetBlocked(event) || hasOpenOverlay() || current.modalOpen || current.searchOverlayOpen || current.deleteConfirmationOpen || keyboardShortcutsOpen) return;
        const command = /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
        const shortcut = shortcuts.find((item) => matchesWorkspaceShortcut(item, event, command));
        if (!shortcut) return;
        if (shortcut.id === "keyboard_shortcuts") setKeyboardShortcutsOpen(true);
        else if (shortcut.id === "sidebar") current.setSidebarOpen(!current.sidebarOpen);
        else if (shortcut.id === "settings" && !current.isGuest) setSettingsOpenRequest((value) => value + 1);
        else if (shortcut.id === "search" && current.requestSearch) current.requestSearch();
        else if (!shortcut.run?.()) return;
        event.preventDefault();
        return;
      }
      if (
        !matchesKeyboardShortcut("keyboard_shortcuts", event) ||
        !canOpenKeyboardShortcuts({
          searchOverlayOpen: current.searchOverlayOpen,
          recentsQuickPeekOpen: isRecentsQuickPeekOpen,
          deleteConfirmationOpen: current.deleteConfirmationOpen,
          modalOpen: current.modalOpen,
          anyOverlayOpen: hasOpenOverlay(),
          shortcutsOverlayOpen: keyboardShortcutsOpen,
        })
      ) {
        return;
      }
      event.preventDefault();
      setKeyboardShortcutsOpen((open) => !open);
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [enabled, isRecentsQuickPeekOpen, keyboardShortcutsOpen]);

  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const current = optionsRef.current;
      if (workspaceRef.current?.keyboardShortcuts) return;
      if (
        keyboardShortcutsOpen ||
        current.searchOverlayOpen ||
        isRecentsQuickPeekOpen ||
        current.deleteConfirmationOpen ||
        current.modalOpen ||
        // The registry, asked now, rather than the named list beside it. None
        // of these shortcuts acts on a surface that is open; they act on the
        // chat behind it, so anything open at all is a reason to stand down.
        // Quick Peek is still named because it does not register a layer.
        hasOpenOverlay() ||
        (!chatAvailable &&
          KEYBOARD_SHORTCUTS.some(
            (shortcut) => shortcut.needsChat && matchesKeyboardShortcut(shortcut.id, event),
          ))
      ) {
        return;
      }

      if (matchesKeyboardShortcut("new_chat", event)) {
        event.preventDefault();
        setIsRecentsQuickPeekOpen(false);
        current.requestNewChat();
        current.closeTransientSidebar();
        return;
      }
      if (matchesKeyboardShortcut("open_recents", event)) {
        event.preventDefault();
        current.setRecentsExpanded(false);
        setIsRecentsQuickPeekOpen(true);
        return;
      }
      if (matchesKeyboardShortcut("expand_sidebar_recents", event)) {
        event.preventDefault();
        setIsRecentsQuickPeekOpen(false);
        const nextState = nextSidebarRecentsState(
          current.sidebarOpen,
          current.recentsExpanded,
        );
        current.setSidebarOpen(nextState.sidebarOpen);
        current.setRecentsExpanded(nextState.recentsExpanded);
        return;
      }
      if (matchesKeyboardShortcut("open_settings", event) && !current.isGuest) {
        event.preventDefault();
        setIsRecentsQuickPeekOpen(false);
        setSettingsOpenRequest((request) => request + 1);
        return;
      }
      if (
        !canManageFocusedConversation({
          isChatView: current.isChatView,
          canManageConversation: current.canManageConversation,
          conversationId: current.conversationId,
        })
      ) {
        return;
      }

      if (matchesKeyboardShortcut("delete_focused_chat", event)) {
        event.preventDefault();
        current.requestDelete();
        return;
      }
      if (matchesKeyboardShortcut("rename_focused_chat", event)) {
        event.preventDefault();
        current.showChatOptions();
        current.startRename();
        return;
      }
      if (matchesKeyboardShortcut("archive_focused_chat", event)) {
        event.preventDefault();
        void current.archiveConversation();
        return;
      }
      if (matchesKeyboardShortcut("toggle_read_focused_chat", event)) {
        event.preventDefault();
        void current.toggleRead();
        return;
      }
      if (matchesKeyboardShortcut("toggle_pin_focused_chat", event)) {
        event.preventDefault();
        void current.togglePin();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [chatAvailable, enabled, isRecentsQuickPeekOpen, keyboardShortcutsOpen]);

  return {
    keyboardShortcutsOpen,
    setKeyboardShortcutsOpen,
    isRecentsQuickPeekOpen,
    setIsRecentsQuickPeekOpen,
    settingsOpenRequest,
  };
}
