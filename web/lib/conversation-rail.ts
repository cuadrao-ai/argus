import type { Message } from "@/components/chat/types";
import type { DecisionState } from "@/lib/argus-api";
import type { RecoveryDisplay } from "@/lib/chat-recovery-display";
import { isSettledStrategyResult } from "@/lib/chat-result-message";
import { computationCalculations } from "@/lib/decision-contract";
import type {
  LocalizedToolText,
  ToolFact,
  ToolOutcome,
  ToolResultCard,
} from "@/lib/tool-result-card";

/**
 * Conversation activity rail ("turn map") derivation and interaction gating.
 *
 * Ticks are derived at render time from the transcript's existing message
 * payloads — no durable model, no LLM/provider calls.
 */

/**
 * Founder decision 2026-09-11: "Backtest finished" widened to "result". A
 * result is a settled backtest, or a message with a backend-declared
 * computation and a succeeded card; never a guess from prose.
 */
export type ConversationRailTickKind =
  | "result"
  | "decision_saved"
  | "error_recovery";

/** One calculation's preview on a computed answer's tick: its card title and headline figure. */
export type ConversationRailCalculation = {
  kind: string;
  title: LocalizedToolText;
  headline: ToolFact | null;
};

export type ConversationRailMetric = { label: string; value: string };

export type ConversationRailTick = {
  messageId: string;
  /** Position of the source message in the transcript array. */
  messageIndex: number;
  kind: ConversationRailTickKind;
  strategyTitle: string | null;
  /** Run symbols, capped at 5 by product constraint; identity during a glide. */
  symbols: string[];
  periodDisplay: string | null;
  /** Display-ready metric rows copied from the result card payload. */
  metrics: ConversationRailMetric[];
  decisionState: DecisionState | null;
  recovery: RecoveryDisplay | null;
  failedJobStatus: "failed" | "canceled" | "expired" | null;
  /** Present on a computed answer's tick, one per calculation in marker order; the rail reads them, never prose. */
  calculations?: ConversationRailCalculation[] | null;
  /** The first unsuccessful outcome among a computed answer's cards, for the treatment owner. */
  toolOutcome?: ToolOutcome | null;
};

/** The rail only earns space on longer conversations. */
export const RAIL_MIN_TRANSCRIPT_MESSAGES = 12;
export const RAIL_MIN_TICKS = 1;

const RAIL_PREVIEW_METRIC_LIMIT = 3;

const FAILED_JOB_STATUSES = new Set(["failed", "canceled", "expired"]);

const STRATEGY_PATH_FIELDS = [
  "strategy_type",
  "asset_universe",
  "asset_class",
  "date_range",
  "capital_amount",
  "sizing_mode",
  "timeframe",
  "cadence",
  "comparison_baseline",
  "indicators",
  "constraints",
  "fee_bps",
  "slippage_bps",
] as const;

const STRONG_STRATEGY_PATH_FIELDS = new Set<string>([
  "asset_universe",
  "date_range",
  "capital_amount",
  "timeframe",
  "cadence",
  "comparison_baseline",
  "indicators",
  "constraints",
  "fee_bps",
  "slippage_bps",
]);

const USER_OWNED_STRATEGY_PROVENANCE = new Set([
  "explicit_user",
  "recurring_contribution",
  "starting_capital",
]);

function meaningfulPathValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function samePathValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => samePathValue(value, right[index]))
    );
  }
  if (
    typeof left !== "object" ||
    left === null ||
    typeof right !== "object" ||
    right === null
  ) {
    return false;
  }
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const leftKeys = Object.keys(leftRecord).sort();
  const rightKeys = Object.keys(rightRecord).sort();
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key, index) =>
        key === rightKeys[index] &&
        samePathValue(leftRecord[key], rightRecord[key]),
    )
  );
}

function canonicalDateRange(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const dateRange = value as Record<string, unknown>;
  return typeof dateRange.start === "string" &&
    dateRange.start.trim() &&
    typeof dateRange.end === "string" &&
    dateRange.end.trim()
    ? dateRange
    : null;
}

function strategyExtraParameters(
  strategy: Record<string, unknown>,
): Record<string, unknown> | null {
  const value = strategy.extra_parameters;
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function normalizedDateRangeText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
  return normalized || null;
}

function sameCanonicalizedDateRange(
  pendingValue: unknown,
  pendingStrategy: Record<string, unknown>,
  confirmedStrategy: Record<string, unknown>,
): boolean {
  const pendingText = normalizedDateRangeText(pendingValue);
  const pendingExtra = strategyExtraParameters(pendingStrategy);
  const confirmedExtra = strategyExtraParameters(confirmedStrategy);
  if (!pendingText || !pendingExtra || !confirmedExtra) return false;

  const pendingRequested = canonicalDateRange(
    pendingExtra.requested_date_range,
  );
  const confirmedRequested = canonicalDateRange(
    confirmedExtra.requested_date_range,
  );
  const effective = canonicalDateRange(confirmedExtra.effective_date_range);
  const confirmed = canonicalDateRange(confirmedStrategy.date_range);
  if (
    !pendingRequested ||
    !confirmedRequested ||
    !effective ||
    !confirmed ||
    !samePathValue(pendingRequested, confirmedRequested) ||
    !samePathValue(confirmed, effective)
  ) {
    return false;
  }

  const pendingRawText = normalizedDateRangeText(
    pendingExtra.date_range_raw_text,
  );
  return (
    pendingRawText === pendingText &&
    normalizedDateRangeText(confirmedExtra.date_range_raw_text) ===
      pendingRawText
  );
}

function sameStrategyPathFact(
  field: (typeof STRATEGY_PATH_FIELDS)[number],
  pendingValue: unknown,
  pendingStrategy: Record<string, unknown>,
  confirmedStrategy: Record<string, unknown>,
): boolean {
  const confirmedValue = confirmedStrategy[field];
  return (
    samePathValue(pendingValue, confirmedValue) ||
    (field === "date_range" &&
      sameCanonicalizedDateRange(
        pendingValue,
        pendingStrategy,
        confirmedStrategy,
      ))
  );
}

function confirmedRequestedFieldValue(
  context: NonNullable<Message["strategyPathContext"]>,
  requestedField: string,
): unknown {
  if (requestedField === "assumption") {
    for (const value of Object.values(context.optionalParameters ?? {})) {
      const parameter = recordValue(value);
      if (
        parameter?.source === "user" &&
        meaningfulPathValue(parameter.value)
      ) {
        return parameter.value;
      }
    }

    const extraParameters = strategyExtraParameters(context.strategy);
    const fieldProvenance = recordValue(extraParameters?.field_provenance);
    for (const [field, provenance] of Object.entries(fieldProvenance ?? {})) {
      if (
        typeof provenance !== "string" ||
        !USER_OWNED_STRATEGY_PROVENANCE.has(provenance)
      ) {
        continue;
      }
      const strategyValue = context.strategy[field];
      if (meaningfulPathValue(strategyValue)) return strategyValue;
      const extraValue = extraParameters?.[field];
      if (meaningfulPathValue(extraValue)) return extraValue;
    }
    return undefined;
  }

  const strategyValue = context.strategy[requestedField];
  if (meaningfulPathValue(strategyValue)) return strategyValue;
  const optionalParameter = context.optionalParameters?.[requestedField];
  if (
    typeof optionalParameter !== "object" ||
    optionalParameter === null ||
    Array.isArray(optionalParameter)
  ) {
    return undefined;
  }
  return (optionalParameter as Record<string, unknown>).value;
}

function confirmationContinuesClarification(
  clarification: Message,
  confirmation: Message,
): boolean {
  const pending = clarification.strategyPathContext;
  const confirmed = confirmation.strategyPathContext;
  if (
    pending?.kind !== "clarification" ||
    confirmed?.kind !== "confirmation" ||
    !pending.requestedField
  ) {
    return false;
  }
  const hasSourceResultIdentity = Boolean(
    pending.sourceResultRunId || confirmed.sourceResultRunId,
  );
  const hasMatchingSourceResultId = Boolean(
    pending.sourceResultRunId &&
      pending.sourceResultRunId === confirmed.sourceResultRunId,
  );
  const hasMatchingStrategyPathId = Boolean(
    pending.strategyPathId &&
      pending.strategyPathId === confirmed.strategyPathId,
  );
  if (pending.requestedField === "assumption") {
    return (
      (!hasSourceResultIdentity || hasMatchingSourceResultId) &&
      hasMatchingStrategyPathId &&
      meaningfulPathValue(
        confirmedRequestedFieldValue(confirmed, pending.requestedField),
      )
    );
  }
  if (hasSourceResultIdentity) return hasMatchingSourceResultId;
  if (
    (pending.strategyPathId || confirmed.strategyPathId) &&
    !hasMatchingStrategyPathId
  ) {
    return false;
  }
  if (
    !meaningfulPathValue(
      confirmedRequestedFieldValue(confirmed, pending.requestedField),
    )
  ) {
    return false;
  }
  if (hasMatchingStrategyPathId) return true;

  let strongMatches = 0;
  for (const field of STRATEGY_PATH_FIELDS) {
    if (field === pending.requestedField) continue;
    const pendingValue = pending.strategy[field];
    if (!meaningfulPathValue(pendingValue)) continue;
    if (
      !sameStrategyPathFact(
        field,
        pendingValue,
        pending.strategy,
        confirmed.strategy,
      )
    ) {
      return false;
    }
    if (STRONG_STRATEGY_PATH_FIELDS.has(field)) strongMatches += 1;
  }
  return strongMatches > 0;
}

function activeConfirmation(message: Message): boolean {
  const confirmation = message.confirmation;
  return (
    message.role === "ai" &&
    message.kind === "strategy_confirmation" &&
    confirmation !== undefined &&
    (confirmation.confirmation_state ?? "active") === "active"
  );
}

function clarificationResolvedByLaterConfirmation(
  messages: readonly Message[],
  recovery: Message,
  recoveryIndex: number,
): boolean {
  return messages
    .slice(recoveryIndex + 1)
    .some(
      (message) =>
        activeConfirmation(message) &&
        confirmationContinuesClarification(recovery, message),
    );
}

function unresolvedClarification(
  messages: readonly Message[],
  message: Message,
  messageIndex: number,
): boolean {
  return (
    message.recoveryDisplay?.kind !== "clarification" ||
    !clarificationResolvedByLaterConfirmation(messages, message, messageIndex)
  );
}

/**
 * The cards the backend-declared computation names, one per calculation in
 * marker order: each calculation takes the next unmatched card whose
 * tool_name is its kind. Null when any calculation has no card.
 */
export function computedAnswerCards(message: Message): ToolResultCard[] | null {
  if (!message.computation) return null;
  const cards = message.toolResultCards ?? [];
  const taken = new Set<number>();
  const matched: ToolResultCard[] = [];
  for (const calculation of computationCalculations(message.computation)) {
    const position = cards.findIndex(
      (card, cardIndex) =>
        !taken.has(cardIndex) && card.tool_name === calculation.kind,
    );
    if (position < 0) return null;
    taken.add(position);
    matched.push(cards[position]);
  }
  return matched;
}

function computedAnswerTick(
  message: Message,
  index: number,
  cards: ToolResultCard[],
): ConversationRailTick {
  const base = {
    messageId: message.id,
    messageIndex: index,
    strategyTitle: null,
    symbols: message.computation?.symbols ?? [],
    periodDisplay: null,
    metrics: [],
    decisionState: message.decisionState ?? null,
    recovery: null,
    failedJobStatus: null,
  };
  const unsuccessful = cards.find((card) => card.outcome.status !== "succeeded");
  if (unsuccessful) {
    return { ...base, kind: "error_recovery", decisionState: null, toolOutcome: unsuccessful.outcome };
  }
  return {
    ...base,
    kind: message.decisionState ? "decision_saved" : "result",
    calculations: cards.map((card) => ({
      kind: card.tool_name,
      title: card.presentation.title,
      headline: card.presentation.answer,
    })),
  };
}

export function deriveConversationRailTicks(
  messages: Message[],
): ConversationRailTick[] {
  const ticks: ConversationRailTick[] = [];
  messages.forEach((message, index) => {
    if (message.role !== "ai") {
      // Retry-history normalization can move a coalesced assistant failure's
      // recovery onto its owning user turn — that turn is then the failure's
      // only visible carrier.
      if (
        message.recoveryDisplay &&
        unresolvedClarification(messages, message, index)
      ) {
        ticks.push({
          messageId: message.id,
          messageIndex: index,
          kind: "error_recovery",
          strategyTitle: null,
          symbols: [],
          periodDisplay: null,
          metrics: [],
          decisionState: null,
          recovery: message.recoveryDisplay,
          failedJobStatus: null,
        });
      }
      return;
    }
    if (isSettledStrategyResult(message)) {
      const result = message.result;
      ticks.push({
        messageId: message.id,
        messageIndex: index,
        kind: result.decisionState ? "decision_saved" : "result",
        strategyTitle: result.strategyLabel ?? result.strategyName ?? null,
        symbols: (result.symbols ?? []).slice(0, 5),
        periodDisplay: result.dateRange?.display ?? result.period ?? null,
        metrics: (result.metrics ?? []).slice(0, RAIL_PREVIEW_METRIC_LIMIT),
        decisionState: result.decisionState ?? null,
        recovery: null,
        failedJobStatus: null,
      });
      return;
    }
    const computedCards = computedAnswerCards(message);
    if (computedCards) {
      ticks.push(computedAnswerTick(message, index, computedCards));
      return;
    }
    if (message.kind === "backtest_job" && message.backtestJob) {
      const status = message.backtestJob.status;
      if (FAILED_JOB_STATUSES.has(status)) {
        ticks.push({
          messageId: message.id,
          messageIndex: index,
          kind: "error_recovery",
          strategyTitle: null,
          symbols: [],
          periodDisplay: null,
          metrics: [],
          decisionState: null,
          recovery: null,
          failedJobStatus: status as "failed" | "canceled" | "expired",
        });
      }
      return;
    }
    if (
      (message.recoveryDisplay &&
        unresolvedClarification(messages, message, index)) ||
      message.assistantRecoveryCode ||
      message.contentPresentation === "superseded_runtime_failure"
    ) {
      ticks.push({
        messageId: message.id,
        messageIndex: index,
        kind: "error_recovery",
        strategyTitle: null,
        symbols: [],
        periodDisplay: null,
        metrics: [],
        decisionState: null,
        recovery: message.recoveryDisplay ?? null,
        failedJobStatus: null,
      });
    }
  });
  return ticks;
}

export function conversationRailVisible(
  messageCount: number,
  tickCount: number,
): boolean {
  return (
    messageCount >= RAIL_MIN_TRANSCRIPT_MESSAGES && tickCount >= RAIL_MIN_TICKS
  );
}

/**
 * Proximity reveal: the rail wakes up gradually as the cursor approaches
 * instead of firing the instant it is touched. ~56px is roughly half an inch
 * at standard density.
 */
export const RAIL_PROXIMITY_RADIUS_PX = 56;

export function railRevealProgress(distancePx: number): number {
  if (!Number.isFinite(distancePx) || distancePx >= RAIL_PROXIMITY_RADIUS_PX) {
    return 0;
  }
  if (distancePx <= 0) {
    return 1;
  }
  return 1 - distancePx / RAIL_PROXIMITY_RADIUS_PX;
}

/**
 * Dwell gating: on cold entry a preview opens only after the pointer has
 * rested on a tick, never on first contact. Once a preview is open, gliding
 * to a neighboring tick switches it instantly — the accident being guarded
 * against is the first unintended opening, not deliberate browsing. Keyboard
 * focus opens immediately because focusing a tick is already a deliberate act.
 */
export const RAIL_PREVIEW_DWELL_MS = 180;

export type RailDwellState = {
  hoveredTickId: string | null;
  hoverStartedAt: number | null;
  openTickId: string | null;
};

export const INITIAL_RAIL_DWELL_STATE: RailDwellState = {
  hoveredTickId: null,
  hoverStartedAt: null,
  openTickId: null,
};

export type RailDwellEvent =
  | { type: "tick_enter"; tickId: string; at: number }
  | { type: "tick_leave" }
  | { type: "elapse"; at: number }
  | { type: "rail_exit" }
  | { type: "focus_open"; tickId: string };

export function railDwellReducer(
  state: RailDwellState,
  event: RailDwellEvent,
): RailDwellState {
  switch (event.type) {
    case "tick_enter":
      if (state.openTickId !== null) {
        return {
          hoveredTickId: event.tickId,
          hoverStartedAt: null,
          openTickId: event.tickId,
        };
      }
      return {
        hoveredTickId: event.tickId,
        hoverStartedAt: event.at,
        openTickId: null,
      };
    case "elapse": {
      if (
        state.hoveredTickId === null ||
        state.hoverStartedAt === null ||
        event.at - state.hoverStartedAt < RAIL_PREVIEW_DWELL_MS
      ) {
        return state;
      }
      if (state.openTickId === state.hoveredTickId) {
        return state;
      }
      return { ...state, openTickId: state.hoveredTickId };
    }
    case "tick_leave":
      return { ...state, hoveredTickId: null, hoverStartedAt: null };
    case "rail_exit":
      return INITIAL_RAIL_DWELL_STATE;
    case "focus_open":
      return {
        hoveredTickId: event.tickId,
        hoverStartedAt: null,
        openTickId: event.tickId,
      };
    default:
      return state;
  }
}

/**
 * Vertical placement: a compact queue stack at fixed pitch, centered on the
 * rail. Order carries sequence and the preview carries identity — spacing
 * deliberately does not encode transcript distance, so every tick stays one
 * small glide away.
 */
export const RAIL_TICK_STACK_PITCH_PX = 12;

export function railTickStackOffsetPx(
  index: number,
  count: number,
  pitch: number = RAIL_TICK_STACK_PITCH_PX,
): number {
  return (index - (count - 1) / 2) * pitch;
}

/**
 * Per-tick magnetization: how far a tick slides out given the pointer's
 * vertical distance to its center. The falloff spans about two neighbors so
 * the stack moves like piano keys under a gliding finger.
 */
export const RAIL_TICK_MAGNET_RADIUS_PX = 30;

export function railTickExtension(distancePx: number): number {
  if (
    !Number.isFinite(distancePx) ||
    distancePx >= RAIL_TICK_MAGNET_RADIUS_PX
  ) {
    return 0;
  }
  if (distancePx <= 0) {
    return 1;
  }
  const linear = 1 - distancePx / RAIL_TICK_MAGNET_RADIUS_PX;
  return linear * linear;
}
