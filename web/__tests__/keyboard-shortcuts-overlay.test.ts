import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

function source(relativePath: string): string {
  return readFileSync(join(root, relativePath), "utf-8");
}

describe("keyboard shortcuts overlay", () => {
  test("uses the central registry for the overlay, handler, and Help entry", () => {
    const overlayPath = join(
      root,
      "components/sidebar/KeyboardShortcutsOverlay.tsx",
    );

    expect(existsSync(overlayPath)).toBe(true);
    if (!existsSync(overlayPath)) return;

    const overlay = readFileSync(overlayPath, "utf-8");
    const chat = source("components/chat/ChatInterface.tsx");
    const keyboardShortcutHook = source(
      "components/keyboard/useChatKeyboardShortcuts.ts",
    );
    const guestShellActions = source("components/chat/useChatShellCapabilities.ts");
    const menu = source("components/sidebar/ProfileMenu.tsx");

    expect(overlay).toContain("KEYBOARD_SHORTCUTS.filter");
    expect(overlay).toContain("max-h-[calc(100dvh-2rem)]");
    expect(overlay).toContain("z-[130]");
    expect(chat).toContain("useChatKeyboardShortcuts");
    expect(keyboardShortcutHook).toContain(
      'matchesKeyboardShortcut("keyboard_shortcuts", event)',
    );
    expect(keyboardShortcutHook).toContain("canOpenKeyboardShortcuts");
    expect(keyboardShortcutHook).toContain("canManageFocusedConversation");
    expect(guestShellActions).toContain(
      'matchesKeyboardShortcut("omnisearch", event)',
    );
    expect(menu).toContain("onOpenKeyboardShortcuts");
  });

  test("localizes every overlay label in English and Spanish", () => {
    const en = JSON.parse(source("public/locales/en/common.json"));
    const es = JSON.parse(source("public/locales/es-419/common.json"));

    expect(en.keyboard_shortcuts.title).toBe("Keyboard shortcuts");
    expect(en.keyboard_shortcuts.shortcuts.omnisearch).toBe("Open search");
    expect(en.keyboard_shortcuts.shortcuts.keyboard_shortcuts).toBe(
      "Show keyboard shortcuts",
    );
    expect(es.keyboard_shortcuts.title).toBe("Atajos de teclado");
    expect(es.keyboard_shortcuts.shortcuts.omnisearch).toBe(
      "Abrir búsqueda",
    );
    expect(es.keyboard_shortcuts.shortcuts.keyboard_shortcuts).toBe(
      "Mostrar atajos de teclado",
    );
    expect(en.keyboard_shortcuts.shortcuts).toMatchObject({
      new_chat: "New chat",
      open_recents: "Open Recents",
      delete_focused_chat: "Delete current chat",
      rename_focused_chat: "Rename current chat",
      archive_focused_chat: "Archive current chat",
      toggle_read_focused_chat: "Mark current chat as read or unread",
      expand_sidebar_recents: "Toggle sidebar and Recents",
      open_settings: "Open Settings",
      toggle_pin_focused_chat: "Pin or unpin current chat",
      quick_jump: "Quick-jump visible items",
    });
    expect(es.keyboard_shortcuts.shortcuts.quick_jump).toBe(
      "Saltar a elementos visibles",
    );
    expect(es.keyboard_shortcuts.shortcuts.expand_sidebar_recents).toBe(
      "Alternar barra lateral y Recientes",
    );
    expect(en.recents_quick_peek.title).toBe("Recents");
    expect(es.recents_quick_peek.empty).toBe("Aún no hay chats recientes.");
  });

  test("shares numbered quick-jump behavior between Recents and Settings", () => {
    const sidebar = source("components/sidebar/ChatSidebar.tsx");
    const profileMenu = source("components/sidebar/ProfileMenu.tsx");
    const sidebarNavButton = source("components/sidebar/SidebarNavButton.tsx");
    const quickJumpBadge = source("components/keyboard/QuickJumpBadge.tsx");
    const keycap = source("components/keyboard/KeyboardShortcutKeycap.tsx");
    const recentChatActions = source(
      "components/sidebar/RecentChatActions.tsx",
    );
    const quickPeekPath = join(
      root,
      "components/sidebar/RecentsQuickPeek.tsx",
    );
    const quickPeek = source("components/sidebar/RecentsQuickPeek.tsx");

    expect(sidebar).toContain("useQuickJump");
    expect(sidebar).toContain("QuickJumpBadge");
    expect(profileMenu).toContain("useQuickJump");
    expect(profileMenu).toContain("QuickJumpBadge");
    expect(profileMenu).toContain('presentation="shortcut_hint"');
    expect(sidebar).toContain('presentation="shortcut_hint"');
    expect(sidebar).toContain("usesCommandKey={usesCommandKey}");
    expect(sidebar).toContain(
      "data-quick-jump-hint={quickJumpNumber}",
    );
    expect(quickPeek).toContain('presentation="shortcut_hint"');
    expect(quickPeek).toContain("usesCommandKey={usesCommandKey}");
    expect(quickPeek).toContain("data-quick-jump-hint={number}");
    expect(recentChatActions).toContain("quickJumpHint?: ReactNode");
    expect(recentChatActions).toContain(
      "isMenuOpen || isTriggerFocused || !quickJumpHint",
    );
    expect(profileMenu).toContain("!isQuickJumpActive && (");
    expect(profileMenu).toContain("min-w-[304px]");
    expect(profileMenu).toContain("h-[294px]");
    expect(profileMenu).toContain("min-h-[88px]");
    expect(profileMenu).toContain("h-[22px] w-full");
    expect(profileMenu.match(/min-w-\[248px\]/g)).toHaveLength(3);
    expect(profileMenu).toContain("min-h-[38px]");
    expect(profileMenu).toContain("keyboard_shortcuts.menu_item");
    expect(profileMenu).toContain('href="/terms"');
    expect(profileMenu).toContain('href="/privacy"');
    expect(profileMenu).not.toContain("settings.help.release_notes");
    expect(profileMenu).toContain('className="whitespace-nowrap"');
    expect(sidebarNavButton).toContain("KeyboardShortcutKeycap");
    expect(sidebarNavButton).toContain(
      "showShortcutHint && shortcutHint ? (",
    );
    expect(quickJumpBadge).toContain("KeyboardShortcutKeycap");
    expect(keycap).toContain("rounded-full");
    expect(keycap).toContain("font-sans");
    expect(keycap).toContain("gap-0.5");
    expect(keycap).toContain("h-[22px]");
    expect(keycap).toContain("text-[11px]");
    expect(existsSync(quickPeekPath)).toBe(true);
  });

  test("routes every real action through the central registry", () => {
    const chat = source("components/chat/ChatInterface.tsx");
    const keyboardShortcutHook = source(
      "components/keyboard/useChatKeyboardShortcuts.ts",
    );

    for (const id of [
      "new_chat",
      "open_recents",
      "delete_focused_chat",
      "rename_focused_chat",
      "archive_focused_chat",
      "toggle_read_focused_chat",
      "expand_sidebar_recents",
      "open_settings",
      "toggle_pin_focused_chat",
    ]) {
      expect(keyboardShortcutHook).toContain(
        `matchesKeyboardShortcut("${id}", event)`,
      );
    }
    expect(chat).toContain("useChatKeyboardShortcuts");
    expect(keyboardShortcutHook).toContain("current.showChatOptions();");
    expect(keyboardShortcutHook).toContain("setIsRecentsQuickPeekOpen(true);");
  });
});
