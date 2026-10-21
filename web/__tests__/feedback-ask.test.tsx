import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import type { Message } from "../components/chat/types";
import FeedbackAsk from "../components/feedback/FeedbackAsk";
import { STORAGE_REGISTRY } from "../lib/browser-storage";
import {
  FEEDBACK_ASK_ANSWERS,
  feedbackAskContext,
  feedbackAskPointers,
  hasAskedForFeedback,
  landedResultThisTurn,
  markAskedForFeedback,
} from "../lib/feedback-ask";
import { feedbackContextForSubmission } from "../lib/feedback-context";
import type { ToolResultCard } from "../lib/tool-result-card";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

type AskProps = ComponentProps<typeof FeedbackAsk>;
type Language = "en" | "es-419";

const STORAGE_KEY = "argus:feedback-ask:v1";
const STRATEGY_NAME = "AAPL buy and hold";
const READOUT = "**Quick take** AAPL ended higher over the window.";

function userTurn(id: string): Message {
  return { id, role: "user", kind: "text", content: "Test buy and hold on AAPL" };
}

function reply(id: string, overrides: Partial<Message> = {}): Message {
  return { id, role: "ai", kind: "text", content: "Here is what I found.", ...overrides };
}

function backtestResult(id: string, overrides: Partial<Message> = {}): Message {
  return reply(id, {
    kind: "strategy_result",
    content: READOUT,
    result: {
      strategyName: STRATEGY_NAME,
      period: "June 1, 2025 to June 1, 2026",
      metrics: [],
      runId: `${id}-run`,
      evidenceArtifactId: `${id}-evidence`,
    },
    ...overrides,
  });
}

function calculation(id: string, status: ToolResultCard["outcome"]["status"]): Message {
  const card = { outcome: { status, result: null, failure: null } } as ToolResultCard;
  return reply(id, { content: "", toolResultCards: [card] });
}

async function renderAsk(language: Language, props: Partial<AskProps> = {}) {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: {
      en: { translation: en },
      "es-419": { translation: es419 },
    },
  });
  return renderToStaticMarkup(
    createElement(
      I18nextProvider,
      { i18n },
      createElement(FeedbackAsk, {
        conversationId: `render-${language}-${crypto.randomUUID()}`,
        messages: [userTurn("u1"), backtestResult("r1")],
        answerArriving: false,
        enabled: true,
        onTellUsMore: () => undefined,
        onToast: () => undefined,
        ...props,
      }),
    ),
  );
}

const TURNS: { label: string; messages: Message[]; follows: string | undefined }[] = [
  { label: "a result card", messages: [userTurn("u1"), backtestResult("r1")], follows: "r1" },
  {
    label: "a result after its job card",
    messages: [userTurn("u1"), reply("j1", { kind: "backtest_job", content: "" }), backtestResult("r1")],
    follows: "r1",
  },
  {
    label: "the later of two results in one turn",
    messages: [userTurn("u1"), backtestResult("r1"), calculation("c1", "succeeded")],
    follows: "c1",
  },
  { label: "a succeeded calculation", messages: [userTurn("u1"), calculation("c1", "succeeded")], follows: "c1" },
  { label: "a result the user moved past", messages: [userTurn("u1"), backtestResult("r1"), userTurn("u2")], follows: undefined },
  { label: "a result still loading", messages: [userTurn("u1"), backtestResult("r1", { isLoadingResult: true })], follows: undefined },
  { label: "a calculation that did not succeed", messages: [userTurn("u1"), calculation("c1", "invalid")], follows: undefined },
  { label: "a plain answer", messages: [userTurn("u1"), reply("a1")], follows: undefined },
  { label: "an empty conversation", messages: [], follows: undefined },
];

const LOCALES: { language: Language; question: string; answers: string[]; dismiss: string }[] = [
  { language: "en", question: "How is Cuadrao doing?", answers: ["Bad", "Okay", "Good"], dismiss: "Don&#x27;t ask again in this chat" },
  { language: "es-419", question: "¿Qué tal lo está haciendo Cuadrao?", answers: ["Mal", "Regular", "Bien"], dismiss: "No volver a preguntar en este chat" },
];

const HIDDEN: { label: string; props: Partial<AskProps> }[] = [
  { label: "while an answer is arriving", props: { answerArriving: true } },
  { label: "for an account that cannot send feedback", props: { enabled: false } },
  { label: "outside a conversation", props: { conversationId: null } },
  { label: "before a result lands", props: { messages: [userTurn("u1")] } },
];

describe("feedback ask", () => {
  for (const { label, messages, follows } of TURNS) {
    test(`${follows ? "asks" : "does not ask"} after ${label}`, () => {
      expect(landedResultThisTurn(messages)?.id).toBe(follows);
    });
  }

  test("a tap saves its rating with the result's pointers and none of the conversation's text", () => {
    const result = backtestResult("result-1");
    const pointers = feedbackAskPointers(result, "conversation-1");

    for (const rating of FEEDBACK_ASK_ANSWERS) {
      const context = feedbackAskContext(pointers, rating);

      expect(context).toEqual({
        source: "feedback_ask",
        surface: "chat",
        conversation_id: "conversation-1",
        message_id: "result-1",
        message_kind: "strategy_result",
        artifact_id: "result-1-run",
        result_run_id: "result-1-run",
        evidence_artifact_id: "result-1-evidence",
        rating,
        tags: [],
      });
      const serialized = JSON.stringify(context);
      expect(serialized).not.toContain(READOUT);
      expect(serialized).not.toContain(STRATEGY_NAME);
    }
    expect([...FEEDBACK_ASK_ANSWERS]).toEqual(["negative", "neutral", "positive"]);
  });

  test("the dialog attaches the result's pointers only when its checkbox is ticked", () => {
    // What "tell us more" hands the dialog, after the chat adds the conversation id.
    const handed = {
      ...feedbackAskPointers(backtestResult("result-2"), "conversation-2"),
      conversation_id: "conversation-2",
    };
    const detail = { tags: [] };

    expect(
      feedbackContextForSubmission(handed, { ...detail, includeConversationContext: false }),
    ).toEqual({
      source: "feedback_ask",
      surface: "chat",
      tags: [],
    });
    expect(
      feedbackContextForSubmission(handed, { ...detail, includeConversationContext: true }),
    ).toMatchObject({
      conversation_id: "conversation-2",
      message_id: "result-2",
      evidence_artifact_id: "result-2-evidence",
    });
  });

  test("a closed ask stays closed for its conversation when storage is blocked", () => {
    const closed = crypto.randomUUID();
    const other = crypto.randomUUID();
    expect(hasAskedForFeedback(closed)).toBe(false);
    markAskedForFeedback(closed);
    expect(hasAskedForFeedback(closed)).toBe(true);
    expect(hasAskedForFeedback(other)).toBe(false);
  });

  test("a closed ask is read back from browser storage, so a reload keeps it closed", () => {
    const stored = new Map<string, string>();
    const scope = globalThis as { window?: unknown };
    const previous = scope.window;
    scope.window = {
      localStorage: {
        getItem: (key: string) => stored.get(key) ?? null,
        setItem: (key: string, value: string) => void stored.set(key, value),
        removeItem: (key: string) => void stored.delete(key),
      },
    };
    try {
      const beforeReload = `closed-before-reload-${crypto.randomUUID()}`;
      stored.set(STORAGE_KEY, JSON.stringify([beforeReload]));
      expect(hasAskedForFeedback(beforeReload)).toBe(true);

      const now = `closed-now-${crypto.randomUUID()}`;
      markAskedForFeedback(now);
      expect(JSON.parse(stored.get(STORAGE_KEY) ?? "[]")).toEqual(
        [beforeReload, now].sort(),
      );
    } finally {
      if (previous === undefined) delete scope.window;
      else scope.window = previous;
    }
    expect(STORAGE_REGISTRY[STORAGE_KEY]).toBe("tips");
  });

  for (const { language, question, answers, dismiss } of LOCALES) {
    test(`asks in ${language} with three one-tap answers`, async () => {
      const markup = await renderAsk(language);

      expect(markup).toContain('data-testid="feedback-ask"');
      expect(markup).toContain(question);
      for (const answer of answers) expect(markup).toContain(`>${answer}</button>`);
      expect(markup).toContain(`aria-label="${dismiss}"`);
    });
  }

  for (const { label, props } of HIDDEN) {
    test(`stays hidden ${label}`, async () => {
      expect(await renderAsk("en", props)).toBe("");
    });
  }

  test("stays hidden in a conversation whose ask already closed", async () => {
    const conversationId = crypto.randomUUID();
    markAskedForFeedback(conversationId);
    expect(await renderAsk("en", { conversationId })).toBe("");
  });

  test("both locales carry every ask string, without em dashes", () => {
    for (const messages of [en, es419]) {
      const ask = messages.feedback.ask;
      const strings = [
        ask.question,
        ...FEEDBACK_ASK_ANSWERS.map((rating) => ask.answers[rating]),
        ask.thanks,
        ask.tell_more,
        ask.dismiss,
      ];
      for (const value of strings) {
        expect(value.length).toBeGreaterThan(0);
        expect(value).not.toContain("—");
      }
    }
  });
});
