import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import {
  ChatWorkspaceProvider,
  visibleShellView,
  workspaceChatAvailable,
  type ChatShellBridge,
  type ChatWorkspace,
} from "../components/chat/ChatWorkspace";
import { WorkspaceMain } from "../components/chat/WorkspaceMain";
import { KeyboardShortcutsOverlaySurface } from "../components/sidebar/KeyboardShortcutsOverlay";
import { businessChatAvailable, type BusinessWorkspaceInfo } from "../lib/business-api";

const payload: BusinessWorkspaceInfo = {
  accounts: [],
  currencies: ["DOP"],
  assistant_available: true,
  chat_available: true,
  receipt_limits: { max_bytes: 1, media_types: ["image/png"] },
};

const noop = () => undefined;
const bridge: ChatShellBridge = {
  currentView: "workspace",
  conversationId: null,
  isBelowTablet: false,
  sidebarCollapsed: false,
  showWorkspace: noop,
  newChat: noop,
  prepareQuestion: noop,
};

function workspace(chatAvailable: boolean): ChatWorkspace {
  return {
    id: "business",
    conversationSurface: "business",
    chatAvailable,
    initialView: "workspace",
    profileInHeader: true,
    panelHasComposer: true,
    sidebarNav: () => null,
    sidebarFooter: () => null,
    headerActions: () => null,
    panel: () => <h2>Your business</h2>,
    starterEntries: () => [],
    composer: () => ({
      leadingControl: null,
      placeholder: "Write a message",
      draftText: null,
      draftKey: "draft",
      onDraftChange: noop,
      replaceDraft: noop,
      onSent: noop,
    }),
    emptyChatLead: () => null,
    search: {
      find: async () => [],
      copy: { placeholder: "", noResultsHint: "", region: "", loading: "", failed: "", retry: "" },
    },
    onShellChange: noop,
  };
}

async function rendered(node: React.ReactNode) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: {} });
  return renderToStaticMarkup(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);
}

describe("Business chat is offered only when the backend says so", () => {
  test("a missing payload, a payload without the field, and false all keep chat closed", () => {
    const older: Partial<BusinessWorkspaceInfo> = { ...payload };
    delete older.chat_available;
    expect(businessChatAvailable(null)).toBe(false);
    expect(businessChatAvailable(older as BusinessWorkspaceInfo)).toBe(false);
    expect(businessChatAvailable({ ...payload, chat_available: false })).toBe(false);
    expect(businessChatAvailable(payload)).toBe(true);
  });
});

describe("the shell keeps a workspace without chat on its panel", () => {
  test("Personal, outside any workspace, always has chat", () => {
    expect(workspaceChatAvailable(null)).toBe(true);
    expect(visibleShellView(null, "chat")).toBe("chat");
  });

  test("a chat view becomes the workspace panel only while chat is off", () => {
    expect(visibleShellView(workspace(false), "chat")).toBe("workspace");
    expect(visibleShellView(workspace(false), "settings")).toBe("settings");
    expect(visibleShellView(workspace(true), "chat")).toBe("chat");
  });

  test("the panel's composer renders only while chat is on", async () => {
    const main = (chat: boolean) =>
      rendered(
        <WorkspaceMain
          workspace={workspace(chat)}
          bridge={bridge}
          disabled={false}
          onToast={noop}
          onSend={noop}
          setCurrentView={noop}
        />,
      );
    const off = await main(false);
    expect(off).toContain("Your business");
    expect(off).not.toContain('data-testid="chat-input"');
    expect(await main(true)).toContain('data-testid="chat-input"');
  });

  test("the shortcuts sheet lists no chat shortcut while chat is off", async () => {
    const sheet = (value: ChatWorkspace | null) =>
      rendered(
        <ChatWorkspaceProvider value={value}>
          <KeyboardShortcutsOverlaySurface onClose={noop} />
        </ChatWorkspaceProvider>,
      );
    const off = await sheet(workspace(false));
    expect(off).toContain("Open search");
    expect(off).toContain("Open Settings");
    for (const label of ["New chat", "Open Recents", "Toggle sidebar and Recents", "Delete current chat", "Quick-jump visible items"]) {
      expect(off).not.toContain(label);
    }
    expect(off).not.toContain('data-shortcut-group="chat"');
    expect(off).not.toContain('data-shortcut-group="quick_jump"');
    for (const value of [null, workspace(true)]) {
      const on = await sheet(value);
      expect(on).toContain("New chat");
      expect(on).toContain("Open Recents");
      expect(on).toContain('data-shortcut-group="quick_jump"');
    }
  });
});
