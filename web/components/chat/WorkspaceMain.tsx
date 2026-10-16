"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import ChatInput from "./ChatInput";
import type {
  ChatShellBridge,
  ChatShellView,
  ChatWorkspace,
} from "./ChatWorkspace";
import type { ChatMention } from "./types";

type ShellBridgeInput = {
  workspace: ChatWorkspace | null;
  currentView: ChatShellView;
  conversationId: string | null;
  isBelowTablet: boolean;
  sidebarCollapsed: boolean;
  resetToEmptyChatSurface: (conversationId?: string | null, view?: ChatShellView) => void;
  closeTransientSidebar: () => void;
};

export type ShellBridgeWithSlots = {
  bridge: ChatShellBridge;
  profileSlot: HTMLElement | null;
  setProfileSlot: (element: HTMLElement | null) => void;
};

export function useChatShellBridge({
  workspace,
  currentView,
  conversationId,
  isBelowTablet,
  sidebarCollapsed,
  resetToEmptyChatSurface,
  closeTransientSidebar,
}: ShellBridgeInput): ShellBridgeWithSlots {
  const [profileSlot, setProfileSlot] = useState<HTMLElement | null>(null);
  const [preparedQuestion, setPreparedQuestion] = useState<string | null>(null);
  const bridge = useMemo<ChatShellBridge>(
    () => ({
      currentView,
      conversationId,
      isBelowTablet,
      sidebarCollapsed,
      showWorkspace: () => {
        resetToEmptyChatSurface(null, "workspace");
        closeTransientSidebar();
      },
      newChat: () => {
        resetToEmptyChatSurface();
        closeTransientSidebar();
      },
      prepareQuestion: (text: string) => {
        resetToEmptyChatSurface();
        setPreparedQuestion(text);
        closeTransientSidebar();
      },
    }),
    [
      closeTransientSidebar,
      conversationId,
      currentView,
      isBelowTablet,
      resetToEmptyChatSurface,
      sidebarCollapsed,
    ],
  );
  useEffect(() => {
    workspace?.onShellChange(bridge);
  }, [bridge, workspace]);
  useEffect(() => {
    if (preparedQuestion === null || !workspace) return;
    workspace.composer(bridge).replaceDraft(preparedQuestion);
    setPreparedQuestion(null);
  }, [bridge, preparedQuestion, workspace]);
  return { bridge, profileSlot, setProfileSlot };
}

export function workspaceComposerProps(
  workspace: ChatWorkspace | null,
  bridge: ChatShellBridge,
) {
  if (!workspace) return {};
  const { leadingControl, draftText, onDraftChange, placeholder, onSent } = workspace.composer(bridge);
  return { leadingControl, draftText, onDraftChange, placeholder, onSent };
}

type WorkspaceMainProps = {
  workspace: ChatWorkspace;
  bridge: ChatShellBridge;
  composerNotice?: ReactNode;
  disabled: boolean;
  onToast: (message: string) => void;
  onSend: (
    text: string,
    mentions?: ChatMention[],
  ) => void | boolean | Promise<void | boolean>;
  setCurrentView: (view: ChatShellView) => void;
};

/** The main area while a workspace panel is showing, composer included. */
export function WorkspaceMain({
  workspace,
  bridge,
  composerNotice,
  disabled,
  onToast,
  onSend,
  setCurrentView,
}: WorkspaceMainProps) {
  const composer = workspace.composer(bridge);
  const hasComposer = workspace.chatAvailable && workspace.panelHasComposer;
  // The conversation opens while the send is admitted; a refused send comes
  // back to the panel with its text.
  const send = async (text: string, mentions?: ChatMention[]) => {
    composer.onDraftChange("");
    setCurrentView("chat");
    const accepted = await onSend(text, mentions);
    if (accepted === false) {
      setCurrentView("workspace");
      composer.replaceDraft(text);
    }
    return accepted;
  };
  return (
    <div className="relative mx-auto flex h-[100dvh] w-full max-w-5xl flex-col" style={workspace.bottomNavigation && bridge.isBelowTablet ? { height: "calc(100dvh - 64px - env(safe-area-inset-bottom))" } : undefined}>
      <div
        data-testid="workspace-panel-region"
        className="argus-scrollbar flex-1 overflow-y-auto px-4 pt-[86px] tablet:px-8"
        style={{ paddingBottom: hasComposer ? 190 : 48 }}
      >
        {workspace.panel(bridge)}
      </div>
      {hasComposer ? (
        <>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-40 bg-[#f9f9f9]/80 backdrop-blur-[0.8px] [mask-image:linear-gradient(to_top,black_50%,transparent_100%)] dark:bg-[#141517]/80" />
          <div className="pointer-events-none absolute inset-x-0 bottom-6 z-20 px-4">
            <div className="pointer-events-auto mx-auto max-w-3xl">
              {composerNotice}
              <ChatInput
                key={composer.draftKey}
                onSend={send}
                disabled={disabled}
                placeholder={composer.placeholder}
                onToast={onToast}
                leadingControl={composer.leadingControl}
                draftText={composer.draftText}
                onDraftChange={composer.onDraftChange}
                onSent={composer.onSent}
              />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
