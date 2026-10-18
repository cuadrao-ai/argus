"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { WorkspaceKeyboardShortcut } from "@/lib/keyboard-shortcuts";
import type { LucideIcon } from "lucide-react";
import type { ConversationSurface } from "@/lib/conversation-surface-api";
import type { WorkspaceStarterEntry } from "./StarterActions";

/**
 * A workspace adds its own surfaces to the shared chat shell without copying
 * it. The shell keeps one owner for conversations, Recents, search, profile and
 * the composer; the workspace contributes navigation, panels and actions.
 *
 * `currentView === "workspace"` means a workspace panel fills the main area.
 * Which panel is the workspace's own fact, never the shell's.
 */
export type ChatShellView = "chat" | "settings" | "workspace";

export type ChatShellBridge = Readonly<{
  currentView: ChatShellView;
  conversationId: string | null;
  isBelowTablet: boolean;
  sidebarCollapsed: boolean;
  /** Shows the workspace's main panel, leaving any open conversation. */
  showWorkspace: () => void;
  /** Opens an empty conversation, like New chat. */
  newChat: () => void;
  /** Opens an empty conversation with editable text; never sends. */
  prepareQuestion: (text: string) => void;
}>;

export type WorkspaceComposer = Readonly<{
  leadingControl: ReactNode;
  placeholder: string;
  draftText: string | null;
  /** Changes only when the draft is replaced from outside the composer. */
  draftKey: string;
  onDraftChange: (text: string) => void;
  replaceDraft: (text: string) => void;
  onSent: () => void;
}>;

export type WorkspaceSearchHit = Readonly<{
  id: string;
  icon: LucideIcon;
  title: string;
  detail: string;
  amount: string | null;
  open: () => void;
  /** The record behind the hit, shown beside the results before it opens. */
  preview?: ReactNode;
}>;

export type WorkspaceSearchGroup = Readonly<{
  id: string;
  label: string;
  hits: readonly WorkspaceSearchHit[];
  error?: string;
}>;

/**
 * The workspace's own records in the shared omnisearch, above conversations.
 * Each group is already authorized and matched by the workspace's backend.
 */
export type WorkspaceSearch = Readonly<{
  /** Hits carry previews, so the palette keeps its dossier pane and sheet. */
  previewAvailable?: boolean;
  find: (query: string) => Promise<readonly WorkspaceSearchGroup[]>;
  copy: Readonly<{
    placeholder: string;
    noResultsHint: string;
    region: string;
    loading: string;
    failed: string;
    retry: string;
  }>;
}>;

export type ChatWorkspace = Readonly<{
  id: string;
  /** Whose chats the shell lists, creates, searches and deletes. */
  conversationSurface: ConversationSurface;
  /**
   * Whether this workspace offers conversations now. False removes every way
   * into a chat: New chat, Recents, conversation search, Ask, the composers
   * and the chat shortcuts. The shell then stays on the workspace panel.
   */
  chatAvailable: boolean;
  initialView: ChatShellView;
  profileInHeader: boolean;
  keyboardShortcuts?: readonly WorkspaceKeyboardShortcut[];
  bottomNavigation?: (bridge: ChatShellBridge) => ReactNode;
  /** Whether the current panel keeps the composer at its bottom edge. */
  panelHasComposer: boolean;
  sidebarNav: (bridge: ChatShellBridge) => ReactNode;
  /** What sits directly under the lockup, above every nav entry: a workspace's own identity control, if any. */
  sidebarHeader?: (bridge: ChatShellBridge) => ReactNode;
  sidebarFooter: (bridge: ChatShellBridge) => ReactNode;
  headerActions: (bridge: ChatShellBridge) => ReactNode;
  panel: (bridge: ChatShellBridge) => ReactNode;
  starterEntries: (bridge: ChatShellBridge) => readonly WorkspaceStarterEntry[];
  composer: (bridge: ChatShellBridge) => WorkspaceComposer;
  emptyChatLead: (bridge: ChatShellBridge) => ReactNode;
  search: WorkspaceSearch;
  onShellChange: (bridge: ChatShellBridge) => void;
}>;

const ChatWorkspaceContext = createContext<ChatWorkspace | null>(null);

export const ChatWorkspaceProvider = ChatWorkspaceContext.Provider;

export function useChatWorkspace(): ChatWorkspace | null {
  return useContext(ChatWorkspaceContext);
}

/** Personal outside a workspace, and Personal always has chat. */
export function workspaceChatAvailable(workspace: ChatWorkspace | null): boolean {
  return workspace === null || workspace.chatAvailable;
}

export function useChatAvailable(): boolean {
  return workspaceChatAvailable(useContext(ChatWorkspaceContext));
}

/** The view the shell shows: a workspace without chat never shows a conversation. */
export function visibleShellView(workspace: ChatWorkspace | null, view: ChatShellView): ChatShellView {
  return view === "chat" && !workspaceChatAvailable(workspace) ? "workspace" : view;
}

/** Personal outside a workspace, so /chat keeps its own history. */
export function useConversationSurface(): ConversationSurface {
  return useContext(ChatWorkspaceContext)?.conversationSurface ?? "personal";
}
