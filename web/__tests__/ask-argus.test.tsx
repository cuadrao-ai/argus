import { describe, expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { omnisearchActionHandlers } from "../components/chat/omnisearch-actions";
import { AskArgusRow } from "../components/sidebar/command-palette/AskArgusRow";
import { commandPaletteKeyboardAction } from "../lib/command-palette-items";
import { translate } from "./support/i18n-instance";

function enter(overrides: Partial<Parameters<typeof commandPaletteKeyboardAction>[0]> = {}) {
  return commandPaletteKeyboardAction({
    key: "Enter",
    itemCount: 0,
    hasSelection: false,
    targetIsEditable: true,
    targetIsSearchInput: true,
    isEditing: false,
    metaKey: false,
    ctrlKey: false,
    ...overrides,
  });
}

function harness(account: "registered" | "guest_with_content" | "guest_empty") {
  const events: string[] = [];
  const actions = omnisearchActionHandlers(() => ({
    closeOverlay: () => { events.push("close"); },
    loadConversation: () => { events.push("load"); },
    startNewChat: async () => { events.push("new_chat"); },
    requestNewChat: () => { events.push("request_new_chat"); },
    guestGate: () => ({
      accountKind: account === "registered" ? "registered" : "guest",
      hasAcceptedContent: account === "guest_with_content",
    }),
    send: (text, _action, _actionArg, options) => {
      events.push(`send:${text}:${JSON.stringify(options)}`);
      return true;
    },
    isSourceConversationReady: () => true,
  }));
  return { actions, events };
}

describe("Ask Argus when nothing matched", () => {
  test("Enter in the search box asks only when the row is offered and nothing is selected", () => {
    expect(enter({ canAsk: true })).toEqual({ type: "ask" });
    expect(enter()).toEqual({ type: "none" });
    expect(enter({ canAsk: true, hasSelection: true, itemCount: 1 })).toEqual({ type: "open", openAtLeftOff: false });
    expect(enter({ canAsk: true, targetIsSearchInput: false, targetIsEditable: false })).toEqual({ type: "none" });
    expect(enter({ canAsk: true, metaKey: true })).toEqual({ type: "none" });
  });

  test("the typed text starts a new chat through the ordinary send path", async () => {
    const { actions, events } = harness("registered");
    await actions.ask("  what does 500 a month at 6% become in 20 years?  ");
    expect(events).toEqual([
      "close",
      "new_chat",
      'send:what does 500 a month at 6% become in 20 years?:{"startNewConversation":true}',
    ]);
  });

  test("a guest whose chat has content keeps today's choice and nothing is sent", async () => {
    const { actions, events } = harness("guest_with_content");
    await actions.ask("hello");
    expect(events).toEqual(["close", "request_new_chat"]);
  });

  test("an empty guest chat starts like any other, and blank text does nothing", async () => {
    const guest = harness("guest_empty");
    await guest.actions.ask("hello");
    expect(guest.events.slice(0, 2)).toEqual(["close", "new_chat"]);
    const blank = harness("registered");
    await blank.actions.ask("   ");
    expect(blank.events).toEqual([]);
  });

  for (const language of ["en", "es-419"] as const) {
    test(`the row shows the typed text in ${language}`, async () => {
      const instance = await translate(language);
      const html = renderToStaticMarkup(
        <I18nextProvider i18n={instance}>
          <AskArgusRow text="Is a 7% loan cheaper than 6.5% with fees?" onAsk={() => undefined} />
        </I18nextProvider>,
      );
      expect(html).toContain("data-ask-argus-row");
      expect(html).toContain("Is a 7% loan cheaper than 6.5% with fees?");
      expect(html).toContain(language === "en" ? "Ask Cuadrao" : "Preguntarle a Cuadrao");
      expect(html).not.toContain("—");
    });
  }
});
