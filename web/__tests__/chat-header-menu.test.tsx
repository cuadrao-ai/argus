import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import ChatHeaderMenu from "../components/chat/ChatHeaderMenu";
import { conversationActivityMutationNoticeDescriptor } from "../components/chat/useConversationActivity";

const source = readFileSync(
  join(import.meta.dir, "../components/chat/ChatHeaderMenu.tsx"),
  "utf-8",
);
const chatInterface = readFileSync(
  join(import.meta.dir, "../components/chat/ChatInterface.tsx"),
  "utf-8",
);
const toggleConversationUnread = readFileSync(
  join(import.meta.dir, "../components/chat/toggleConversationUnread.ts"),
  "utf-8",
);

async function renderMenu(
  overrides: Partial<React.ComponentProps<typeof ChatHeaderMenu>> = {},
): Promise<string> {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", fallbackLng: false });
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <ChatHeaderMenu
        isOpen
        onToggleOpen={() => undefined}
        onRequestClose={() => undefined}
        isUnread
        isReadMutationPending={false}
        onToggleUnread={() => undefined}
        isRenaming={false}
        renameValue=""
        onRenameValueChange={() => undefined}
        onStartRename={() => undefined}
        onSaveRename={() => undefined}
        onCancelRename={() => undefined}
        isSavingRename={false}
        pinned={false}
        isPinning={false}
        onTogglePin={() => undefined}
        isDeleting={false}
        onRequestDelete={() => undefined}
        {...overrides}
      />
    </I18nextProvider>,
  );
}

describe("ChatHeaderMenu unread control", () => {
  test("renders unread first, popover on desktop and the primitive below it", async () => {
    const html = await renderMenu();
    const unread = html.indexOf("Mark as read");
    const pin = html.indexOf("Pin chat");
    const rename = html.indexOf("Rename chat");
    const separator = html.indexOf('role="separator"');
    const remove = html.indexOf("Delete");

    expect(unread).toBeGreaterThan(-1);
    expect(unread).toBeLessThan(pin);
    expect(pin).toBeLessThan(rename);
    expect(rename).toBeLessThan(separator);
    expect(separator).toBeLessThan(remove);
    // Server render is the desktop band, so this is the popover. The mobile
    // form is no longer a second hand-rolled sheet here: it goes through the
    // BottomSheet primitive, which owns the scrim, focus trap, real drag, and
    // the history entry that makes system back close it. Enforced by
    // __tests__/bottom-sheet-ownership.test.ts.
    expect(html).toContain("absolute bottom-auto right-0 left-auto top-full");
    expect(html).toContain("w-[260px]");
    expect(html).not.toContain("fixed inset-x-0 bottom-0");
    expect(source).toContain("<BottomSheet");
    expect(source).toContain('snaps="fit"');
  });

  test("disables only the read mutation action", async () => {
    const html = await renderMenu({ isReadMutationPending: true });
    const unreadLabel = html.indexOf("Mark as read");
    const pinLabel = html.indexOf("Pin chat");
    const unread = html.slice(html.lastIndexOf("<button", unreadLabel), unreadLabel);
    const pin = html.slice(html.lastIndexOf("<button", pinLabel), pinLabel);

    expect(unread).toContain("disabled");
    expect(pin).not.toContain("disabled");
  });

  test("closes before mutating and restores trigger focus on Escape", () => {
    const toggleStart = source.indexOf("const handleToggleUnread");
    const toggleEnd = source.indexOf("};", toggleStart);
    const toggle = source.slice(toggleStart, toggleEnd);
    const escapeStart = source.indexOf('event.key === "Escape"');
    const escapeEnd = source.indexOf("}", escapeStart);
    const escape = source.slice(escapeStart, escapeEnd);

    expect(toggle.indexOf("onRequestClose()")).toBeLessThan(
      toggle.indexOf("onToggleUnread()"),
    );
    expect(escape).toContain("onRequestClose()");
    expect(escape).toContain("triggerRef.current?.focus()");
  });

  test("maps mutation notices to stable localized keys and rollback fallbacks", () => {
    expect(
      conversationActivityMutationNoticeDescriptor({
        conversationId: "conversation-a",
        action: "mark_unread",
        outcome: "success",
      }),
    ).toEqual({
      key: "chat.activity.mark_unread_success",
      defaultValue: "Marked as unread.",
      variant: "neutral",
    });
    expect(
      conversationActivityMutationNoticeDescriptor({
        conversationId: "conversation-a",
        action: "mark_read",
        outcome: "error",
      }),
    ).toEqual({
      key: "chat.activity.mark_read_error",
      defaultValue: "Couldn’t mark this conversation as read. Try again.",
      variant: "error",
    });
    expect(chatInterface).not.toContain("onMutationNotice: () => undefined");
    expect(chatInterface).toContain("conversationActivityMutationNoticeDescriptor");
  });

  test("uses the same owner, current cursor, and registered-only gate as Recents", () => {
    expect(chatInterface).toContain("conversationActivity.hasEffectiveUnread(conversationId)");
    expect(chatInterface).toContain('conversationActivity.isMutationPending(conversationId, "mark_read")');
    expect(chatInterface).toContain('conversationActivity.isMutationPending(conversationId, "mark_unread")');
    expect(chatInterface).toContain("toggleConversationUnread(conversationActivity, conversationId)");
    expect(toggleConversationUnread).toContain("activity.hasEffectiveUnread(conversationId)");
    expect(toggleConversationUnread).toContain("activity.selectAttentionCursor(conversationId)");
    expect(toggleConversationUnread).toContain("activity.markRead(");
    expect(toggleConversationUnread).toContain("activity.markUnread(conversationId)");
    expect(chatInterface).toMatch(
      /conversationId &&\s*canManageConversation \?[\s\S]{0,900}<ChatHeaderMenu/,
    );
  });
});
