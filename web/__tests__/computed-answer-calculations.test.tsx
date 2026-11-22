import { afterEach, describe, expect, test } from "bun:test";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import ComputedAnswerActions from "../components/chat/ComputedAnswerActions";
import ComputedRerunPanel, { ComputedRerunPanels } from "../components/chat/ComputedRerunPanel";
import { RailCalculationPreview } from "../components/chat/ConversationActivityRail";
import { ComputedAnswerDecision } from "../components/chat/DecisionAffordance";
import { DecisionReruns } from "../components/chat/DecisionRerunView";
import { hydrateMessagesFromApi } from "../components/chat/chat-message-projection";
import { AnswerDossierView } from "../components/sidebar/command-palette/AnswerDossierView";
import type { AnswerDossier } from "../lib/answer-dossier-contract";
import type { ApiMessage } from "../lib/argus-api";
import { answerRerunPanels, panelsAfterEdit, panelsAfterRefresh, refreshedCards } from "../lib/computed-rerun";
import { computedAnswerCards, deriveConversationRailTicks } from "../lib/conversation-rail";
import {
  comparableComputationKind,
  computationCalculations,
  decisionComputationFromMetadata,
  type DecisionRerun,
} from "../lib/decision-contract";
import { rerunDecision, rerunMessageComputation } from "../lib/decisions-api";
import { localizedToolText, toolFactValue, type ToolResultCard } from "../lib/tool-result-card";
import { translate } from "./support/i18n-instance";

/** Cards and markers come from scripts/dump_calculation_fixtures.py. */
const fixture = JSON.parse(
  readFileSync(join(import.meta.dir, "fixtures/calculation-cards.json"), "utf-8"),
) as {
  cards: Record<string, { card: ToolResultCard; computation: { kind: string; inputs: Record<string, unknown>; symbols?: string[] } }>;
};
const loan = fixture.cards.time_value;
const growth = fixture.cards.growth_projection;
const multiple = fixture.cards.price_multiple;
const calculationOf = ({ computation }: { computation: { kind: string; inputs: Record<string, unknown> } }) => ({ kind: computation.kind, inputs: computation.inputs });
const severalMarker = { calculations: [calculationOf(loan), calculationOf(growth)] };

const escapeHtml = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");

function inOrder(markup: string, texts: string[]) {
  const positions = texts.map((text) => markup.indexOf(escapeHtml(text)));
  expect(positions.every((position) => position >= 0)).toBe(true);
  expect([...positions].sort((left, right) => left - right)).toEqual(positions);
}

function answer(id: string, cards: ToolResultCard[], computation: unknown, metadata: Record<string, unknown> = {}): ApiMessage {
  return {
    id,
    conversation_id: "c1",
    role: "assistant",
    content: "",
    created_at: "2026-09-11T12:00:00Z",
    metadata: { tool_result_cards: cards, computation, ...metadata },
  };
}

const computed = (card: ToolResultCard): DecisionRerun => ({ kind: card.tool_name, inputs: {}, status: "computed", result: card, retest: null, reason_code: null });
const unavailable = (kind: string): DecisionRerun => ({ kind, inputs: {}, status: "unavailable", result: null, retest: null, reason_code: "kernel_unavailable" });

describe("a computation marker in either shape", () => {
  test("one calculation and several calculations both parse, in marker order", () => {
    const single = decisionComputationFromMetadata({ computation: loan.computation });
    expect(single).toEqual(loan.computation);
    expect(computationCalculations(single!)).toEqual([calculationOf(loan)]);
    expect(comparableComputationKind(single!)).toBe("time_value");

    const several = decisionComputationFromMetadata({ computation: { ...severalMarker, symbols: ["AAPL", ""] } });
    expect(several).toEqual({ ...severalMarker, symbols: ["AAPL"] });
    expect(computationCalculations(several!).map((calculation) => calculation.kind)).toEqual(["time_value", "growth_projection"]);
    expect(comparableComputationKind(several!)).toBeNull();
    expect(decisionComputationFromMetadata({ computation: { calculations: [{ kind: "time_value" }, { kind: "time_value" }] } }))
      .toEqual({ calculations: [{ kind: "time_value", inputs: {} }, { kind: "time_value", inputs: {} }] });
    const listedOnce = decisionComputationFromMetadata({ computation: { calculations: [calculationOf(loan)] } });
    expect(computationCalculations(listedOnce!)).toEqual([calculationOf(loan)]);
    expect(comparableComputationKind(listedOnce!)).toBe("time_value");
  });

  test("a malformed several-calculation marker is refused", () => {
    const valid = calculationOf(loan);
    for (const computation of [
      { calculations: [] },
      { calculations: [valid, valid, valid, valid, valid] },
      { calculations: [valid, { kind: "Not A Slug", inputs: {} }] },
      { calculations: [valid, { kind: "growth_projection", inputs: [1, 2] }] },
      { calculations: [valid, null] },
      { calculations: "time_value" },
    ]) {
      expect(decisionComputationFromMetadata({ computation })).toBeNull();
    }
  });
});

describe("an answer weighing several calculations on the conversation rail", () => {
  test("is one tick whose preview lists every title and headline in order", async () => {
    const messages = hydrateMessagesFromApi([
      { id: "u1", conversation_id: "c1", role: "user", content: "Borrow now or save first?", created_at: "2026-09-11T11:59:00Z", metadata: {} },
      answer("a1", [loan.card, growth.card], severalMarker),
    ]).messages;
    const ticks = deriveConversationRailTicks(messages);
    expect(ticks.map((tick) => [tick.messageId, tick.kind])).toEqual([["a1", "result"]]);
    const calculations = ticks[0].calculations ?? [];
    expect(calculations.map((calculation) => calculation.headline?.name)).toEqual(["payment", "end_value"]);

    const instance = await translate("en");
    const t = instance.t.bind(instance);
    const preview = renderToStaticMarkup(<RailCalculationPreview calculations={calculations} t={t} locale="en" />);
    expect(preview.match(/data-testid="conversation-activity-rail-headline"/g)).toHaveLength(2);
    inOrder(preview, calculations.flatMap((calculation) => [
      localizedToolText(calculation.title, t),
      toolFactValue(calculation.headline!, t, "en"),
    ]));

    const single = renderToStaticMarkup(<RailCalculationPreview calculations={calculations.slice(0, 1)} t={t} locale="en" />);
    expect(single.match(/data-testid="conversation-activity-rail-headline"/g)).toHaveLength(1);
    expect(single).not.toContain(escapeHtml(localizedToolText(calculations[0].title, t)));
  });

  test("calculations sharing a kind take their cards in order, and a calculation without a card is no result", () => {
    const second = { ...growth.card, artifact_id: `${growth.card.artifact_id}-second`, call_id: `${growth.card.call_id}-second` };
    const marker = { calculations: [calculationOf(growth), calculationOf(growth)] };
    const [matched, reordered, missing] = hydrateMessagesFromApi([
      answer("a1", [growth.card, loan.card, second], marker),
      answer("a2", [second, growth.card], marker),
      answer("a3", [growth.card, loan.card], marker),
    ]).messages;
    expect(computedAnswerCards(matched)?.map((card) => card.artifact_id)).toEqual([growth.card.artifact_id, second.artifact_id]);
    expect(computedAnswerCards(reordered)?.map((card) => card.artifact_id)).toEqual([second.artifact_id, growth.card.artifact_id]);
    expect(computedAnswerCards(missing)).toBeNull();
    expect(deriveConversationRailTicks([missing])).toEqual([]);
  });

  test("one unsuccessful calculation makes the answer's single tick need attention", () => {
    const failed = fixture.cards.time_value_payment_below_interest;
    const failedCard = { ...failed.card, artifact_id: `${failed.card.artifact_id}-second`, call_id: `${failed.card.call_id}-second` };
    const messages = hydrateMessagesFromApi([
      answer("a1", [loan.card, failedCard], { calculations: [calculationOf(loan), calculationOf(failed)] }),
    ]).messages;
    const ticks = deriveConversationRailTicks(messages);
    expect(ticks).toHaveLength(1);
    expect(ticks[0].kind).toBe("error_recovery");
    expect(ticks[0].toolOutcome?.failure?.code).toBe("payment_below_interest");
    expect(ticks[0].calculations).toBeUndefined();
  });
});

function dossier(cards: ToolResultCard[], overrides: Partial<AnswerDossier> = {}): AnswerDossier {
  return {
    message_id: "m1",
    conversation_id: "c1",
    asked: "Borrow now or save first?",
    computed_at: "2026-09-11T12:00:00Z",
    symbols: [],
    cards,
    decision: null,
    decision_id: null,
    actions: [{ type: "answer_decision", availability: "available", message_id: "m1", decision_state: null, note: null }],
    ...overrides,
  };
}

type PanelElement = ReactElement<{ onRerun: (changes: Record<string, unknown>) => void }>;

/** Walks rendered elements, expanding the hook-free panel list, to reach each calculation's panel. */
function panelElements(node: ReactNode): PanelElement[] {
  if (Array.isArray(node)) return node.flatMap(panelElements);
  if (!isValidElement(node)) return [];
  const element = node as ReactElement<{ children?: ReactNode }>;
  if (element.type === ComputedRerunPanel) return [element as unknown as PanelElement];
  if (element.type === ComputedRerunPanels) {
    return panelElements(ComputedRerunPanels(element.props as unknown as Parameters<typeof ComputedRerunPanels>[0]));
  }
  return panelElements(element.props.children);
}

describe("one stored and latest panel per calculation", () => {
  test("the Search dossier renders a panel per card in order and offers continue without compare", async () => {
    const instance = await translate("en");
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={instance}>
        <AnswerDossierView dossier={dossier([loan.card, multiple.card])} onOpenConversationById={() => undefined} />
      </I18nextProvider>,
    );
    expect(html.match(/data-testid="computed-rerun-panel"/g)).toHaveLength(2);
    expect(html).toContain(`<input id="rerun-0-${loan.card.artifact_id}-present_value"`);
    expect(html).toContain(`<input id="rerun-1-${multiple.card.artifact_id}-`);
    expect(html.indexOf("rerun-0-")).toBeLessThan(html.indexOf("rerun-1-"));
    expect(html).toContain("data-answer-dossier-refresh");
    expect(html).not.toContain('data-compute-action="compare"');
    expect(html).toContain('data-compute-action="continue"');
    expect(html).not.toMatch(/(tools|command_palette)\.[a-z_]+\.[a-z_.]+/);
  });

  test("a reopened decision renders a panel per re-run and each edit names its calculation", async () => {
    const instance = await translate("en");
    const t = instance.t.bind(instance);
    // Every re-run card shares the backend's rerun identity, so input ids carry the calculation index.
    const reruns = [loan.card, growth.card].map((card) => computed({ ...card, artifact_id: "decision_rerun", call_id: "decision_rerun" }));
    const props = { decisionId: "d1", reruns, latest: [null, null], busy: false, transportError: null, t, locale: "en" };
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={instance}><DecisionReruns {...props} onRerun={() => undefined} /></I18nextProvider>,
    );
    expect(html.match(/data-testid="computed-rerun-panel"/g)).toHaveLength(2);
    expect(html).toContain('<input id="rerun-0-decision_rerun-present_value"');
    expect(html).toMatch(/<input id="rerun-1-decision_rerun-/);

    const edits: Array<[number, Record<string, unknown>]> = [];
    const panels = panelElements(DecisionReruns({ ...props, onRerun: (calculation, changes) => { edits.push([calculation, changes]); } }));
    expect(panels).toHaveLength(2);
    panels.forEach((panel, index) => panel.props.onRerun({ edited: index }));
    expect(edits).toEqual([[0, { edited: 0 }], [1, { edited: 1 }]]);
  });

  test("a calculation that cannot re-run on open keeps its place beside the ones that did", async () => {
    const instance = await translate("en");
    const t = instance.t.bind(instance);
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={instance}>
        <DecisionReruns decisionId="d1" reruns={[unavailable("time_value"), computed(growth.card)]} latest={[null, null]} busy={false} transportError={null}
          onRerun={() => undefined} t={t} locale="en" />
      </I18nextProvider>,
    );
    expect(html.match(/data-testid="computed-rerun-panel"/g)).toHaveLength(1);
    expect(html.indexOf('data-testid="computed-rerun-unavailable"')).toBeLessThan(html.indexOf('data-testid="computed-rerun-panel"'));
  });
});

describe("re-runs map to their calculations", () => {
  const originalFetch = globalThis.fetch;
  const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  afterEach(() => {
    globalThis.fetch = originalFetch;
    process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
  });

  test("decision and message re-runs post the calculation index, defaulting to the first", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls: Array<[string, string, unknown]> = [];
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([init?.method ?? "GET", String(input).replace(/^.*\/api\/v1/, ""), JSON.parse(String(init?.body))]);
      return Response.json({ reruns: [] });
    }) as typeof fetch;
    await rerunDecision("d1", { periods: 24 }, 1);
    await rerunMessageComputation("c1", "m1", { present_value: 150000 }, 2);
    await rerunMessageComputation("c1", "m1", {});
    expect(calls).toEqual([
      ["POST", "/decisions/d1/rerun", { inputs: { periods: 24 }, calculation: 1 }],
      ["POST", "/conversations/c1/messages/m1/computation/rerun", { inputs: { present_value: 150000 }, calculation: 2 }],
      ["POST", "/conversations/c1/messages/m1/computation/rerun", { inputs: {}, calculation: 0 }],
    ]);
  });

  test("each view hands its panel's calculation index to its client", () => {
    // No DOM harness exists in this suite, so the hand-off from panel to client is pinned at the source.
    const decisionView = readFileSync(join(import.meta.dir, "../components/chat/DecisionRerunView.tsx"), "utf-8");
    expect(decisionView).toContain("rerunDecision(decisionId, changes, calculation)");
    expect(decisionView).toContain("onRerun={(calculation, changes) => { void rerun(calculation, changes); }}");
    const dossierView = readFileSync(join(import.meta.dir, "../components/sidebar/command-palette/AnswerDossierView.tsx"), "utf-8");
    expect(dossierView).toContain("rerunMessageComputation(dossier.conversation_id, dossier.message_id, changes, calculation)");
    expect(dossierView).toContain("onRerun={(calculation, changes) => { void rerun(calculation, changes); }}");
  });

  test("an edit moves only its own panel, and a refresh lands each card beside its stored one", () => {
    const changedLoan = { ...loan.card, arguments: { ...loan.card.arguments, present_value: 150000 } };
    const edited = panelsAfterEdit(answerRerunPanels(2), 0, [computed(changedLoan), computed(growth.card)]);
    expect(edited).toEqual([{ latest: changedLoan, source: "changes", reasonCode: null }, ...answerRerunPanels(1)]);
    const locked = panelsAfterEdit(edited, 1, [computed(loan.card), unavailable("growth_projection")]);
    expect(locked).toEqual([edited[0], { latest: null, source: "changes", reasonCode: "kernel_unavailable" }]);

    const refreshedLoan = { ...loan.card, arguments: { ...loan.card.arguments, annual_rate_pct: 6.5 } };
    const refreshedGrowth = { ...growth.card, arguments: { ...growth.card.arguments, annual_rate_pct: 1.5 } };
    const cards = refreshedCards({ status: "refreshed", reruns: [computed(refreshedLoan), computed(refreshedGrowth)] }, 2);
    expect(cards).toEqual([refreshedLoan, refreshedGrowth]);
    expect(panelsAfterRefresh(locked, cards!)).toEqual([
      { latest: refreshedLoan, source: "refreshed", reasonCode: null },
      { latest: refreshedGrowth, source: "refreshed", reasonCode: null },
    ]);
    const partial = refreshedCards({ status: "refreshed", reruns: [unavailable("time_value"), computed(refreshedGrowth)] }, 2);
    expect(partial).toEqual([null, refreshedGrowth]);
    expect(panelsAfterRefresh(edited, partial!)[0]).toBe(edited[0]);
    expect(refreshedCards({ status: "inputs_not_found", reruns: [] }, 2)).toBeNull();
    expect(refreshedCards({ status: "refreshed", reruns: [unavailable("time_value"), unavailable("growth_projection")] }, 2)).toBeNull();
  });
});

describe("compare is offered only for a single calculation", () => {
  test("a several-calculation answer in chat offers continue and hides compare", async () => {
    const instance = await translate("en");
    const several = decisionComputationFromMetadata({ computation: severalMarker });
    const single = decisionComputationFromMetadata({ computation: loan.computation });
    const render = (computation: typeof several) => renderToStaticMarkup(
      <I18nextProvider i18n={instance}>
        <ComputedAnswerDecision message={{ id: "a1", computation, decisionState: null }} conversationId="c1" onOpenConversation={() => undefined} />
      </I18nextProvider>,
    );
    const severalMarkup = render(several);
    expect(severalMarkup.match(/data-testid="computed-answer-decision"/g)).toHaveLength(1);
    expect(severalMarkup).not.toContain('data-compute-action="compare"');
    expect(severalMarkup).toContain('data-compute-action="continue"');
    expect(render(single)).toContain('data-compute-action="compare"');
    expect(renderToStaticMarkup(
      <ComputedAnswerActions conversationId="c1" messageId="m1" kind={null} t={instance.t.bind(instance)} locale="en" />,
    )).toBe("");
  });
});
