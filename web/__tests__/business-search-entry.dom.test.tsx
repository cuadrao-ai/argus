import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { useState, type ReactNode } from "react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import { useBusinessKeyboardShortcuts } from "@/components/business-app/business-keyboard-shortcuts";
import type { BusinessActions } from "@/components/business-app/business-actions";
import { useChatKeyboardShortcuts } from "@/components/keyboard/useChatKeyboardShortcuts";
import { useChatShellCapabilities } from "@/components/chat/useChatShellCapabilities";
import spanish from "@/public/locales/es-419/common.json";
import type { UserResponse } from "@/lib/guest-account";

const cleanups: (() => Promise<void>)[] = [];
const actions: BusinessActions = { create: [], composer: [], starterEntries: [] };
const activity = {
  hasEffectiveUnread: () => false,
  selectAttentionCursor: () => null,
  markRead: async () => {},
  markUnread: async () => {},
  isMutationPending: () => false,
};

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

function pressSearch() {
  document.body.dispatchEvent(new KeyboardEvent("keydown", {
    key: "k",
    code: "KeyK",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  }));
}

function SearchSurface({ business, children }: { business: boolean; children: ReactNode }) {
  const shortcuts = useBusinessKeyboardShortcuts({ openPanel: () => {}, actions, chosen: null });
  const workspace = business
    ? ({ id: "business", conversationSurface: "business", keyboardShortcuts: shortcuts } as ChatWorkspace)
    : null;
  return (
    <ChatWorkspaceProvider value={workspace}>
      <ul>
        {shortcuts.filter(() => business).map((shortcut) => (
          <li key={shortcut.id} data-shortcut={shortcut.id}>{shortcut.label}</li>
        ))}
      </ul>
      {children}
    </ChatWorkspaceProvider>
  );
}

function SearchKeys({ business }: { business: boolean }) {
  const [open, setOpen] = useState(false);
  useChatKeyboardShortcuts({
    enabled: true,
    requestSearch: business ? () => setOpen(true) : undefined,
    isChatView: true,
    canManageConversation: true,
    conversationId: "conversation-1",
    isGuest: false,
    searchOverlayOpen: open,
    deleteConfirmationOpen: false,
    modalOpen: false,
    sidebarOpen: true,
    setSidebarOpen: () => {},
    recentsExpanded: false,
    setRecentsExpanded: () => {},
    requestNewChat: () => {},
    closeTransientSidebar: () => {},
    requestDelete: () => {},
    startRename: () => {},
    archiveConversation: () => {},
    toggleRead: () => {},
    togglePin: () => {},
    showChatOptions: () => {},
  });
  useChatShellCapabilities({
    account: { account_kind: "registered" } as UserResponse,
    conversationId: "conversation-1",
    closeTransientSidebar: () => {},
    onNewChat: () => {},
    onOpenOmnisearch: () => setOpen(true),
    omnisearchShortcutEnabled: !business,
  });
  return open ? <div role="dialog" aria-label="Buscar" /> : null;
}

async function mount(business: boolean) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: ChatSidebar } = await import("@/components/sidebar/ChatSidebar");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <SearchSurface business={business}>
          <SearchKeys business={business} />
          <ChatSidebar
            isOpen
            onToggle={() => {}}
            currentView="chat"
            conversationId={null}
            conversationActivity={activity}
            isRecentsExpanded={false}
            onToggleRecents={() => {}}
            historyItems={[]}
            historyNextCursor={null}
            isLoadingMoreHistory={false}
            hasRequestedOlderHistory={false}
            historyLoadMoreError={false}
            onNewChat={() => {}}
            onNavigate={() => {}}
            onOpenItem={() => {}}
            onLoadMoreHistory={() => {}}
            onOpenSearch={() => {}}
            onLogout={() => {}}
            omnisearchEnabled
            showProfileMenu={false}
          />
        </SearchSurface>
      </I18nextProvider>,
    );
  });
  cleanups.push(() => act(async () => root.unmount()));
  return act;
}

const buscarButton = () => [...document.querySelectorAll("button")].find((button) => button.textContent?.includes("Buscar"));

async function shown(business: boolean) {
  const act = await mount(business);
  const before = document.querySelector("[role=dialog]");
  let thrown: unknown = null;
  await act(async () => {
    try {
      pressSearch();
    } catch (error) {
      thrown = error;
    }
  });
  return {
    button: buscarButton()?.textContent?.replace(/\s+/g, " ").trim() ?? null,
    shortcut: document.querySelector("[data-shortcut=search]")?.textContent ?? null,
    dialog: document.querySelector("[role=dialog]") !== null,
    dialogBefore: before !== null,
    thrown,
  };
}

test("Business shows Buscar and Ctrl+K opens search", async () => {
  const result = await shown(true);
  assert.equal(result.button?.includes("Buscar"), true);
  assert.equal(result.button?.includes("Ctrl+K"), true);
  assert.equal(result.shortcut, "Buscar");
  assert.equal(result.dialogBefore, false);
  assert.equal(result.dialog, true);
  assert.equal(result.thrown, null);
});

test("Personal keeps Buscar and Ctrl+K", async () => {
  const result = await shown(false);
  assert.equal(result.button?.startsWith("Buscar"), true);
  assert.equal(result.shortcut, null);
  assert.equal(result.dialog, true);
  assert.equal(result.thrown, null);
});
