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
import { useGuestShellActions } from "@/components/guest/useGuestShellActions";
import { businessSearchEnabledFromEnv, businessSearchEntryEnabled } from "@/lib/private-alpha-flags";
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
  const entry = businessSearchEntryEnabled(business ? "business" : undefined);
  useChatKeyboardShortcuts({
    enabled: true,
    requestSearch: business && entry ? () => setOpen(true) : undefined,
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
  useGuestShellActions({
    account: { account_kind: "registered" } as UserResponse,
    guestBootstrapRequired: false,
    hasAcceptedContent: false,
    closeTransientSidebar: () => {},
    onOpenFeedback: () => {},
    onNewChat: () => {},
    onRequestNonEmptyGuestChoice: () => {},
    onRequestGuestDecision: () => {},
    onOpenOmnisearch: () => setOpen(true),
    onRequestSignIn: () => {},
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

async function shown(business: boolean, flag: string | undefined) {
  if (flag === undefined) delete process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
  else process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED = flag;
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

test("the Business search flag defaults off and Personal does not read it", () => {
  assert.equal(businessSearchEnabledFromEnv(undefined), false);
  assert.equal(businessSearchEnabledFromEnv(""), false);
  assert.equal(businessSearchEnabledFromEnv("true"), true);
  assert.equal(businessSearchEntryEnabled("business"), process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED === "true");
  assert.equal(businessSearchEntryEnabled(undefined), true);
  assert.equal(businessSearchEntryEnabled("personal"), true);
});

test("Business hides Buscar and Ctrl+K when its search flag is off", async () => {
  const previous = process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
  try {
    const result = await shown(true, undefined);
    assert.equal(result.button, null);
    assert.equal(result.shortcut, null);
    assert.equal(result.dialogBefore, false);
    assert.equal(result.dialog, false);
    assert.equal(result.thrown, null);
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
    else process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED = previous;
  }
});

test("Business shows Buscar and Ctrl+K opens search when its search flag is on", async () => {
  const previous = process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
  try {
    const result = await shown(true, "true");
    assert.equal(result.button?.includes("Buscar"), true);
    assert.equal(result.button?.includes("Ctrl+K"), true);
    assert.equal(result.shortcut, "Buscar");
    assert.equal(result.dialog, true);
    assert.equal(result.thrown, null);
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
    else process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED = previous;
  }
});

test("Personal keeps Buscar and Ctrl+K whether the Business search flag is on or off", async () => {
  const previous = process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
  try {
    for (const flag of [undefined, "true"] as const) {
      for (const cleanup of cleanups.splice(0)) await cleanup();
      document.body.innerHTML = "";
      const result = await shown(false, flag);
      assert.equal(result.button?.startsWith("Buscar"), true);
      assert.equal(result.shortcut, null);
      assert.equal(result.dialog, true);
      assert.equal(result.thrown, null);
    }
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED;
    else process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED = previous;
  }
});
