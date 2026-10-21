import { apiFetch } from "@/lib/argus-api-transport";
import { todayIso } from "../business-format";
import type { Decision, DecisionKind, Match, Movement, Suggestion, SuggestionReason, TransaccionesSource, TransaccionesView } from "./transacciones-model";

/**
 * The one place the bank routes meet the screen. Today the server serves the
 * unmatched charges of a period and the pending suggestions; it confirms and
 * declines. Everything else the view model holds (deposits, matched rows,
 * accounts, categories, document summaries, totals, undo) is not served yet,
 * so it maps to unknown here and the screen shows it as unknown. When the
 * movements read lands, only this module changes.
 */

type WireLine = {
  id: string;
  occurred_on: string;
  description: string;
  amount: string;
  currency: string;
  sense: "charge" | "deposit" | "zero";
  state: "matched" | "sin_comprobante" | "unmatched";
};

type WireSuggestion = {
  id: string;
  line_id: string;
  target_id: string;
  target_kind: "receipt" | "venta";
  status: "pending" | "confirmed" | "declined";
  amount_score: string;
  date_score: string;
  merchant_score: string;
  confidence: string;
  actionable: boolean;
};

type WireUnmatched = { count: number; period_start: string; period_end: string; lines: WireLine[] };

export type BankWire = Readonly<{ unmatched: WireUnmatched; suggestions: readonly WireSuggestion[] }>;

class BankWireError extends Error {
  readonly code = "bank_wire_shape";
}

const text = (value: unknown, field: string): string => {
  if (typeof value !== "string") throw new BankWireError(`bank: ${field} is not text`);
  return value;
};
const decimal = (value: unknown, field: string): string => {
  const raw = text(value, field);
  if (!/^-?\d+(\.\d+)?$/.test(raw.trim())) throw new BankWireError(`bank: ${field} is not a decimal`);
  return raw.trim();
};
const record = (value: unknown, field: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null) throw new BankWireError(`bank: ${field} is not an object`);
  return value as Record<string, unknown>;
};

function parseLine(value: unknown): WireLine {
  const line = record(value, "line");
  const sense = text(line.sense, "line.sense");
  const state = text(line.state, "line.state");
  if (sense !== "charge" && sense !== "deposit" && sense !== "zero") throw new BankWireError("bank: line.sense is unknown");
  if (state !== "matched" && state !== "sin_comprobante" && state !== "unmatched") throw new BankWireError("bank: line.state is unknown");
  return { id: text(line.id, "line.id"), occurred_on: text(line.occurred_on, "line.occurred_on"), description: text(line.description, "line.description"), amount: decimal(line.amount, "line.amount"), currency: text(line.currency, "line.currency"), sense, state };
}

function parseSuggestion(value: unknown): WireSuggestion {
  const row = record(value, "suggestion");
  const kind = text(row.target_kind, "suggestion.target_kind");
  const status = text(row.status, "suggestion.status");
  if (kind !== "receipt" && kind !== "venta") throw new BankWireError("bank: suggestion.target_kind is unknown");
  if (status !== "pending" && status !== "confirmed" && status !== "declined") throw new BankWireError("bank: suggestion.status is unknown");
  return {
    id: text(row.id, "suggestion.id"),
    line_id: text(row.line_id, "suggestion.line_id"),
    target_id: text(row.target_id, "suggestion.target_id"),
    target_kind: kind,
    status,
    amount_score: decimal(row.amount_score, "suggestion.amount_score"),
    date_score: decimal(row.date_score, "suggestion.date_score"),
    merchant_score: decimal(row.merchant_score, "suggestion.merchant_score"),
    confidence: decimal(row.confidence, "suggestion.confidence"),
    actionable: row.actionable === true,
  };
}

/** Parse the two bank answers; a shape the screen cannot trust fails the load, never half-renders. */
export function parseBankWire(unmatched: unknown, suggestions: unknown): BankWire {
  const page = record(unmatched, "unmatched");
  if (typeof page.count !== "number" || !Array.isArray(page.lines)) throw new BankWireError("bank: unmatched page is malformed");
  if (!Array.isArray(suggestions)) throw new BankWireError("bank: suggestions is not a list");
  return {
    unmatched: { count: page.count, period_start: text(page.period_start, "period_start"), period_end: text(page.period_end, "period_end"), lines: page.lines.map(parseLine) },
    suggestions: suggestions.map(parseSuggestion),
  };
}

/** The reasons a score part supports. The server owns the scoring; a part above zero is a reason it counted. */
function reasonsOf(suggestion: WireSuggestion): SuggestionReason[] {
  const reasons: SuggestionReason[] = [];
  if (Number(suggestion.amount_score) > 0) reasons.push({ kind: "amount" });
  if (Number(suggestion.date_score) > 0) reasons.push({ kind: "date", daysBefore: null });
  if (Number(suggestion.merchant_score) > 0) reasons.push({ kind: "name" });
  return reasons;
}

function toSuggestion(wire: WireSuggestion): Suggestion {
  return { id: wire.id, confidence: Number(wire.confidence), documentKind: wire.target_kind === "venta" ? "venta" : "recibo", document: null, reasons: reasonsOf(wire) };
}

function matchOf(line: WireLine, offered: readonly WireSuggestion[]): Match {
  if (line.state === "matched") return { state: "igualada", document: null };
  const best = [...offered].sort((left, right) => Number(right.confidence) - Number(left.confidence))[0];
  return best ? { state: "sugerencia", suggestion: toSuggestion(best) } : { state: "falta_comprobante" };
}

/** Today's bank answers as the view model. Unknown facts stay unknown: no account, category, totals or coverage is invented. */
export function mapBankWire(wire: BankWire): TransaccionesView {
  const offered = new Map<string, WireSuggestion[]>();
  for (const suggestion of wire.suggestions) {
    if (suggestion.status !== "pending" || !suggestion.actionable) continue;
    offered.set(suggestion.line_id, [...(offered.get(suggestion.line_id) ?? []), suggestion]);
  }
  const movements: Movement[] = wire.unmatched.lines.map((line) => ({
    id: line.id,
    occurredOn: line.occurred_on,
    counterparty: null,
    bankText: line.description,
    money: { amount: line.amount, currency: line.currency },
    categoryId: null,
    account: null,
    match: matchOf(line, offered.get(line.id) ?? []),
  }));
  return {
    movements,
    totals: { entradas: null, salidas: null, porIgualar: { count: wire.unmatched.count, amounts: null }, igualadas: null },
    coverageThrough: null,
  };
}

type Fetch = <T>(path: string, init?: RequestInit) => Promise<T>;

const SERVED: ReadonlySet<DecisionKind> = new Set(["igualar", "rechazar"]);

/** The live source over today's bank routes. `fetchJson` is the API transport; tests hand in their own. */
export function createBankTransaccionesSource(fetchJson: Fetch = apiFetch): TransaccionesSource {
  return {
    async load(period) {
      const query = new URLSearchParams({ period_start: period.from, period_end: period.to ?? todayIso() });
      const [unmatched, suggestions] = await Promise.all([
        fetchJson<unknown>(`/business/bank/unmatched?${query}`),
        fetchJson<unknown>("/business/bank/suggestions?status=pending"),
      ]);
      return mapBankWire(parseBankWire(unmatched, suggestions));
    },
    async decide(decision: Decision, idempotencyKey: string) {
      if (decision.kind !== "igualar" && decision.kind !== "rechazar") throw new Error(`bank: ${decision.kind} is not served yet`);
      const verb = decision.kind === "igualar" ? "confirm" : "decline";
      await fetchJson(`/business/bank/suggestions/${encodeURIComponent(decision.suggestionId)}/${verb}`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey } });
    },
    supports: (kind) => SERVED.has(kind),
  };
}
