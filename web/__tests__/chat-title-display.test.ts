import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  conversationDisplayTitle,
  renamePrefillTitle,
  shouldPlayTitleReveal,
  type HeaderTitleState,
} from "../lib/chat-title-display";
import {
  advanceRevealFrame,
  titleRevealFrame,
} from "../lib/chat-title-reveal";

const root = join(import.meta.dir, "..");

const PLACEHOLDER = "New chat";

function state(overrides: Partial<HeaderTitleState>): HeaderTitleState {
  return {
    conversationId: "conv-1",
    title: "NVDA Buy and Hold",
    titleSource: "ai_generated",
    ...overrides,
  };
}

describe("conversationDisplayTitle", () => {
  test("unnamed chats render the localized placeholder, never the backend default", () => {
    expect(conversationDisplayTitle(null, PLACEHOLDER)).toBe(PLACEHOLDER);
    expect(
      conversationDisplayTitle(
        { title: "New idea", title_source: "system_default" },
        PLACEHOLDER,
      ),
    ).toBe(PLACEHOLDER);
  });

  test("generated and user titles render as-is", () => {
    expect(
      conversationDisplayTitle(
        { title: "NVDA Buy and Hold", title_source: "ai_generated" },
        PLACEHOLDER,
      ),
    ).toBe("NVDA Buy and Hold");
    expect(
      conversationDisplayTitle(
        { title: "My thread", title_source: "user_renamed" },
        PLACEHOLDER,
      ),
    ).toBe("My thread");
  });

  test("records without a source keep their title unless it is blank", () => {
    expect(
      conversationDisplayTitle({ title: "Older payload" }, PLACEHOLDER),
    ).toBe("Older payload");
    expect(conversationDisplayTitle({ title: "  " }, PLACEHOLDER)).toBe(
      PLACEHOLDER,
    );
  });
});

describe("renamePrefillTitle", () => {
  test("stays empty until the chat carries a real name", () => {
    expect(renamePrefillTitle(null)).toBe("");
    expect(
      renamePrefillTitle({ title: "New idea", title_source: "system_default" }),
    ).toBe("");
    expect(renamePrefillTitle({ title: "New idea" })).toBe("");
  });

  test("prefills generated and user names", () => {
    expect(
      renamePrefillTitle({ title: "NVDA Buy and Hold", title_source: "ai_generated" }),
    ).toBe("NVDA Buy and Hold");
    expect(
      renamePrefillTitle({ title: "My thread", title_source: "user_renamed" }),
    ).toBe("My thread");
  });
});

describe("shouldPlayTitleReveal", () => {
  test("plays when the active conversation earns its generated name", () => {
    const previous = state({ title: PLACEHOLDER, titleSource: null });
    expect(shouldPlayTitleReveal(previous, state({}))).toBe(true);
    const fromDefault = state({ title: PLACEHOLDER, titleSource: "system_default" });
    expect(shouldPlayTitleReveal(fromDefault, state({}))).toBe(true);
  });

  test("never plays on navigation, first render, rename, or re-delivery", () => {
    expect(shouldPlayTitleReveal(null, state({}))).toBe(false);
    expect(
      shouldPlayTitleReveal(
        state({ conversationId: "conv-2", title: PLACEHOLDER, titleSource: null }),
        state({}),
      ),
    ).toBe(false);
    expect(
      shouldPlayTitleReveal(
        state({ title: PLACEHOLDER, titleSource: null }),
        state({ titleSource: "user_renamed", title: "My thread" }),
      ),
    ).toBe(false);
    expect(shouldPlayTitleReveal(state({}), state({}))).toBe(false);
    expect(
      shouldPlayTitleReveal(
        state({ titleSource: "user_renamed", title: "Old name" }),
        state({}),
      ),
    ).toBe(false);
  });
});

describe("titleRevealFrame", () => {
  const target = "NVDA Buy and Hold";
  const fixedChar = () => "x";

  test("starts fully scrambled with spaces preserved", () => {
    const frame = titleRevealFrame(target, 0, fixedChar);
    expect(frame.settled).toBe("");
    expect(frame.scrambled).toBe("xxxx xxx xxx xxxx");
    expect(frame.scrambled.length).toBe(target.length);
  });

  test("ends exactly on the target", () => {
    const frame = titleRevealFrame(target, 1, fixedChar);
    expect(frame.settled).toBe(target);
    expect(frame.scrambled).toBe("");
  });

  test("settles left to right monotonically", () => {
    let lastSettled = -1;
    for (const progress of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
      const frame = titleRevealFrame(target, progress, fixedChar);
      expect(frame.settled).toBe(target.slice(0, frame.settled.length));
      expect(frame.settled.length).toBeGreaterThanOrEqual(lastSettled);
      expect(frame.settled.length + frame.scrambled.length).toBe(target.length);
      lastSettled = frame.settled.length;
    }
  });

  test("advanceRevealFrame keeps prior glyphs while the boundary moves", () => {
    const first = titleRevealFrame(target, 0.2, () => "a");
    const advanced = advanceRevealFrame(first, target, 0.5);
    expect(advanced.settled).toBe(
      titleRevealFrame(target, 0.5, fixedChar).settled,
    );
    expect(advanced.scrambled).toBe(
      first.scrambled.slice(first.scrambled.length - advanced.scrambled.length),
    );
  });
});

describe("chat header wiring", () => {
  const chat = readFileSync(
    join(root, "components/chat/ChatInterface.tsx"),
    "utf-8",
  );
  const sidebar = readFileSync(
    join(root, "components/sidebar/ChatSidebar.tsx"),
    "utf-8",
  );

  test("header renders the synced conversation title instead of a static label", () => {
    const titleState = readFileSync(
      join(root, "lib/chat-header-title-state.ts"),
      "utf-8",
    );
    expect(chat).toContain("<ChatHeaderTitle");
    expect(chat).toContain("useActiveConversationTitle({");
    expect(titleState).toContain("conversationDisplayTitle(");
    expect(chat).not.toContain("t('common.conversation', 'Conversation')");
  });

  test("owner menu renders only for a manageable conversation", () => {
    expect(chat).toContain('currentView === "chat" &&');
    expect(chat).toContain("conversationId &&");
    expect(chat).toContain("canManageConversation ? (");
    expect(chat).toContain("<ChatHeaderMenu");
  });

  test("header delete dialog names the active chat", () => {
    const dialog = readFileSync(join(root, "components/chat/ConversationDeleteDialog.tsx"), "utf-8");
    expect(chat).toContain("title={headerConversationTitle}");
    expect(dialog).toContain("{ title },");
    expect(chat).not.toContain('{ title: t("common.conversation", "Conversation") }');
  });

  test("rename prefill trusts title_source, not string comparison", () => {
    expect(chat).toContain("renamePrefillTitle(activeTitleRecord)");
    expect(chat).not.toContain("activeHistoryChat.title !== t('chat.new_chat')");
    expect(sidebar).toContain("setRenameValue(renamePrefillTitle(item))");
  });

  test("sidebar rows render the placeholder-aware display title", () => {
    expect(sidebar).toContain("conversationDisplayTitle(");
    expect(sidebar).toContain("{displayTitle}");
  });

  test("reveal animation cannot strand scrambled glyphs", () => {
    const headerTitle = readFileSync(
      join(root, "components/chat/ChatHeaderTitle.tsx"),
      "utf-8",
    );
    expect(headerTitle).toContain("useLayoutEffect(");
    expect(headerTitle).toContain('document.visibilityState !== "visible"');
    expect(headerTitle).toContain("TITLE_REVEAL_DURATION_MS + 250");
    expect(headerTitle).toContain("prefers-reduced-motion");
    expect(headerTitle).toContain('aria-hidden="true"');
  });
});
