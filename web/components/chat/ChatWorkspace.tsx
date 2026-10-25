"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { WorkspaceKeyboardShortcut } from "@/lib/keyboard-shortcuts";
import type { LucideIcon } from "lucide-react";
import type { ConversationSurface } from "@/lib/conversation-surface-api";
import type { StorageKey } from "@/lib/browser-storage";
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
  /** The name the person asked to be greeted by; null when they set none. */
  greetingName: string | null;
  /** Signed-in member identity, from the shell account response. */
  memberEmail?: string | null;
  /** Opens the shared search. Absent when this shell has no search. */
  openSearch?: () => void;
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
  /** What the hit is, in a word on the row. */
  badge: string;
  /** More words a screen or action answers to, beyond its title. */
  keywords?: string;
  /** Absent when the record has no screen of its own: the row shows it and goes nowhere. */
  open?: () => void;
  /** The record behind the hit, shown beside the results before it opens. */
  preview?: ReactNode;
}>;

/** The next rows of a group. `restarted` rows replace the group's, as after a stale cursor. */
export type WorkspaceSearchPage = Readonly<{
  hits: readonly WorkspaceSearchHit[];
  loadMore?: () => Promise<WorkspaceSearchPage>;
  restarted?: boolean;
}>;

export type WorkspaceSearchGroup = Readonly<{
  id: string;
  label: string;
  hits: readonly WorkspaceSearchHit[];
  error?: string;
  /** Present while the backend holds more rows for this group; Cargar más calls it. */
  loadMore?: () => Promise<WorkspaceSearchPage>;
}>;

/** The server's memory of recent searches. A call may fail with a 404 on a backend without it. */
export type WorkspaceRecentSearchesServer = Readonly<{
  list: () => Promise<readonly { id: string; q: string }[]>;
  add: (query: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  clear: () => Promise<void>;
}>;

/**
 * The workspace's own records in the shared omnisearch, above conversations.
 * Each group is already authorized and matched by the workspace's backend.
 */
export type WorkspaceSearch = Readonly<{
  /** Hits carry previews, so the palette keeps its dossier pane and sheet. */
  previewAvailable?: boolean;
  find: (query: string) => Promise<readonly WorkspaceSearchGroup[]>;
  /**
   * Screens and actions, listed before a query and matched by it on the
   * device, so a short or mistyped query still has somewhere to go.
   */
  shortcuts: readonly WorkspaceSearchGroup[];
  /** Where this browser keeps the queries that led to a record, per scope. */
  recents: Readonly<{ key: StorageKey; scope: string; server?: WorkspaceRecentSearchesServer }>;
  copy: Readonly<{
    placeholder: string;
    noResultsHint: string;
    region: string;
    loading: string;
    failed: string;
    retry: string;
    recent: string;
    showMore: (count: number) => string;
    showLess: string;
    loadMore: string;
    loadMoreFailed: string;
    retryLoad: string;
    removeRecent: (query: string) => string;
    clearRecents: string;
    noMatch: (query: string) => string;
    keepTyping: string;
    readError: string;
    loadMoreError: string;
    ask: string;
    close: string;
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
  /** The workspace's mark; on a closed rail it is the expand button, and hovering it shows the expand icon. */
  sidebarMark?: (bridge: ChatShellBridge) => ReactNode;
  sidebarFooter: (bridge: ChatShellBridge) => ReactNode;
  /** Phone leading control, in place of the menu button. */
  headerLeading?: (bridge: ChatShellBridge) => ReactNode;
  headerActions: (bridge: ChatShellBridge) => ReactNode;
  /** A search field in the top bar from the tablet stop up; the sidebar then drops its own search row. */
  headerSearch?: (bridge: ChatShellBridge) => ReactNode;
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
