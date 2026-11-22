import { describe, expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import ToolResultCard from "../components/chat/ToolResultCard";
import ChatMessage from "../components/chat/ChatMessage";
import {
  parseToolResultCard, toolCardsFromMetadata, toolInputChange,
  applyToolResultMessage, toolProgressText, toolInputChanges,
  toolFactValue,
} from "../lib/tool-result-card";
import { hydrateMessagesFromApi, messageStreamPresentation } from "../components/chat/chat-message-projection";
import { parseChatStreamFrame } from "../lib/argus-api";
import { toolCardFixture, toolMessageFixture } from "./fixtures/tool-result-card";
import { toolResultRecomputeHandler } from "../lib/tool-result-recompute";

async function translate(language: "en" | "es-419") {
  const instance = createInstance();
  await instance.init({ lng: language, fallbackLng: false, resources: {
    en: { translation: en }, "es-419": { translation: es },
  }, interpolation: { escapeValue: false } });
  return instance;
}

describe("declaration-owned result cards", () => {
  test("a queued handler checks current source identity and submission state before dispatch", async () => {
    let latestMessageId = "later-user";
    let busy = false;
    const unexpected = () => { throw new Error("An ineligible edit dispatched"); };
    const recompute = toolResultRecomputeHandler(() => ({
      source: () => ({ conversationId: "conversation-alpha", latestMessageId, busy }),
      setMessages: unexpected, invalidate: unexpected, reload: async () => unexpected(),
    }));
    await recompute("tool-message", toolCardFixture(), { known: 42 });
    latestMessageId = "tool-message";
    busy = true;
    await recompute("tool-message", toolCardFixture(), { known: 42 });
  });

  test.each([
    { latestMessageId: "tool-message", turnInFlight: false, isStreaming: false, editable: true },
    { latestMessageId: "newer-user", turnInFlight: false, isStreaming: false, editable: false },
    { latestMessageId: "newer-answer", turnInFlight: false, isStreaming: false, editable: false },
    { latestMessageId: "tool-message", turnInFlight: true, isStreaming: false, editable: false },
    { latestMessageId: "tool-message", turnInFlight: false, isStreaming: true, editable: false },
  ])("only the idle latest persisted message offers an editor: %j", async (state) => {
    const instance = await translate("en");
    const message = hydrateMessagesFromApi([toolMessageFixture([toolCardFixture()])]).messages[0];
    const html = renderToStaticMarkup(<I18nextProvider i18n={instance}><ChatMessage
      message={message} onToolRecompute={async () => undefined} isLatest
      latestMessageId={state.latestMessageId} turnInFlight={state.turnInFlight} isStreaming={state.isStreaming}
    /></I18nextProvider>);
    expect(html.includes('<input id="artifact-1-known"')).toBe(state.editable);
    expect(html).toContain("data-tool-answer");
  });

  test("one parser retains plural calls, blank and zero through hydration", () => {
    const cards = [toolCardFixture(), toolCardFixture({ call_id: "call-2", artifact_id: "artifact-2" })];
    expect(toolCardsFromMetadata({ tool_result_cards: cards })).toEqual(cards);
    expect(toolCardsFromMetadata({ final_response_payload: { tool_result_cards: cards } })).toEqual(cards);
    const messages = hydrateMessagesFromApi([toolMessageFixture(cards)]).messages;
    expect(messages[0].toolResultCards).toEqual(cards);
    expect(messageStreamPresentation(messages, messages[0], 0, false, false).isWorkingMessage).toBe(false);
    expect(cards[0].arguments.known).toBe(0);
    expect(cards[0].arguments.unknown).toBeNull();
  });

  test("unknown versions and failures carrying an answer fail closed", () => {
    const card = toolCardFixture();
    expect(parseToolResultCard({ ...card, schema_version: 2 })).toBeNull();
    expect(parseToolResultCard({ ...card, card_version: 2 })).toBeNull();
    expect(parseToolResultCard({ ...card, outcome: { status: "ambiguous", result: { value: 2 }, failure: { code: "multiple_answers" } } })).toBeNull();
  });

  test("edits retain the blank and submit numeric zero, never a fallback", () => {
    const card = toolCardFixture();
    expect(toolInputChange(card, "known", "0")).toEqual({ known: 0 });
    expect(toolInputChange(card, "known", "")).toBeNull();
    expect(toolInputChange(card, "unknown", "2")).toBeNull();
    expect(toolInputChange(card, "undeclared", "2")).toBeNull();
    const withSecond = { ...card, arguments: { ...card.arguments, other: 1 }, presentation: { ...card.presentation,
      inputs: [...card.presentation.inputs, { ...card.presentation.inputs[0], name: "other", value: 1 }],
    } };
    expect(toolInputChanges(withSecond, { known: "2", other: "0" })).toEqual({ known: 2, other: 0 });
    expect(toolInputChanges(withSecond, { known: "2", other: "" })).toBeNull();
  });

  test("a stale response cannot replace a newer input revision", () => {
    const original = toolCardFixture();
    const newer = toolCardFixture({ input_revision: 2, arguments: { known: 8, unknown: null } });
    const messages = hydrateMessagesFromApi([toolMessageFixture([newer])]).messages;
    expect(applyToolResultMessage(messages, toolMessageFixture([original]))[0].toolResultCards?.[0]).toEqual(newer);
    const latest = toolCardFixture({ input_revision: 3 });
    expect(applyToolResultMessage(messages, toolMessageFixture([latest]))[0].toolResultCards?.[0]).toEqual(latest);
  });

  for (const language of ["en", "es-419"] as const) {
    test(`typed values retain their declaration-owned display in ${language}`, async () => {
      const instance = await translate(language);
      const card = toolCardFixture();
      const fact = { ...card.presentation.inputs[0], value: "monthly", value_text: { locale_key: "command_palette.dossier_values.cadences.monthly", interpolation_args: {} } };
      expect(toolFactValue(fact, instance.t.bind(instance), language)).toBe((language === "en" ? en : es).command_palette.dossier_values.cadences.monthly);
      expect(fact.value).toBe("monthly");
    });
    test(`boolean facts and controls localize in ${language}`, async () => {
      const instance = await translate(language);
      const card = toolCardFixture();
      const input = { ...card.presentation.inputs[0], value: false };
      const booleanCard = { ...card, arguments: { ...card.arguments, known: false }, presentation: { ...card.presentation, inputs: [input] } };
      const html = renderToStaticMarkup(<I18nextProvider i18n={instance}><ToolResultCard card={booleanCard} onRecompute={async () => undefined} /></I18nextProvider>);
      expect(toolFactValue(input, instance.t.bind(instance), language)).toBe("No");
      expect(html).toContain(language === "en" ? ">Yes</option>" : ">Sí</option>");
      expect(toolInputChange(booleanCard, "known", "false")).toEqual({ known: false });
    });
    test(`answer-first inputs and retained unknown render in ${language}`, async () => {
      const instance = await translate(language);
      const html = renderToStaticMarkup(<I18nextProvider i18n={instance}><ToolResultCard card={toolCardFixture()} onRecompute={async () => undefined} /></I18nextProvider>);
      expect(html.indexOf('data-tool-answer')).toBeLessThan(html.indexOf('data-tool-inputs'));
      expect(html).toContain('value="0"');
      expect(html).toContain(language === "en" ? "Solved value" : "Valor calculado");
      expect(html).not.toContain("Benchmark");
      expect(html).not.toContain("Run test");
    });
  }

  test("each result keeps its narrative and canonical citations inside its card", async () => {
    const instance = await translate("en");
    const card = toolCardFixture();
    const withSources = { ...card, presentation: { ...card.presentation,
      narrative: "The **published figure** was checked.", sources: [{ url: "https://example.com/report", title: "Source report", source_date: "2026-09-08" }],
    } };
    const html = renderToStaticMarkup(<I18nextProvider i18n={instance}><ToolResultCard card={withSources} /></I18nextProvider>);
    expect(html).toContain("<strong>published figure</strong>");
    expect(html).toContain('href="https://example.com/report"');
    expect(html).toContain("example.com");
    expect(parseToolResultCard({ ...withSources, presentation: { ...withSources.presentation, sources: [{ url: "javascript:alert(1)", title: "Invalid" }] } })).toBeNull();
    expect(parseToolResultCard({ ...withSources, outcome: { status: "unavailable", result: null, failure: { code: "unavailable", fields: [] } }, presentation: { ...withSources.presentation, answer: null } })).toBeNull();
  });

  test("declared visuals reuse the receipt chart and reject malformed points", async () => {
    const instance = await translate("en");
    const card = toolCardFixture();
    const withVisual = { ...card, presentation: { ...card.presentation,
      visual: { kind: "portfolio_equity" as const, currency: "USD", base_value: 0, series: [{ time: "2026-09-08", value: 0 }, { time: "2026-09-09", value: 12 }] },
    } };
    const html = renderToStaticMarkup(<I18nextProvider i18n={instance}><ToolResultCard card={withVisual} /></I18nextProvider>);
    expect(parseToolResultCard(withVisual)?.presentation).toEqual(withVisual.presentation);
    expect(html).toContain("data-tool-visual");
    expect(html).toContain("h-[220px]");
    const invalid = { ...withVisual, presentation: { ...withVisual.presentation, visual: { ...withVisual.presentation.visual, series: [{ time: "2026-09-08", value: Number.NaN }] } } };
    expect(parseToolResultCard(invalid)).toBeNull();
  });

  test("progress is an actual call fact; graph stages cannot invent copy", async () => {
    const instance = await translate("en");
    const progress = { locale_key: "tools.progress.call", interpolation_args: { tool_name: "echo" }, call_id: "call-1", tool_name: "echo" };
    expect(parseChatStreamFrame(`data: ${JSON.stringify({ type: "stage_start", stage: "execute", tool_progress: progress })}`)).toEqual({ event: "stage_start", data: { stage: "execute", tool_progress: progress } });
    expect(toolProgressText(progress, instance.t.bind(instance))).toBe("Running echo");
    expect(toolProgressText(null, instance.t.bind(instance))).toBe("Working...");
    expect(toolProgressText({ ...progress, locale_key: "missing" }, instance.t.bind(instance))).toBe("Working...");
  });
});
