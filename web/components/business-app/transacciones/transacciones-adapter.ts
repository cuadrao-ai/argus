import { apiFetch } from "@/lib/argus-api-transport";
import type { BusinessAccount, BusinessExpense, BusinessOverview, BusinessWorkspaceInfo } from "@/lib/business-api";
import type { MonthCloseDocument, MonthCloseSnapshot } from "@/lib/business-month-close";
import { todayIso } from "../business-format";
import { expensePanel } from "../business-expense-target";
import { recordFiscalMark } from "../business-ui";
import { sumByCurrency, type AccountKind, type Decision, type DecisionKind, type IgualarView, type Match, type Movement, type MovementAccount, type RecordRow, type RecordsView, type Suggestion, type SuggestionReason, type TransaccionesSource } from "./transacciones-model";

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
export function mapBankWire(wire: BankWire): IgualarView {
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
    mode: "igualar",
    movements,
    totals: { entradas: null, salidas: null, porIgualar: { count: wire.unmatched.count, amounts: null }, igualadas: null },
    coverageThrough: null,
  };
}

type Fetch = <T>(path: string, init?: RequestInit) => Promise<T>;

const SERVED: ReadonlySet<DecisionKind> = new Set(["igualar", "rechazar"]);

/** The bank routes answer 404 while bank matching is off on the server. */
const bankRoutesOff = (error: unknown) => (error as { status?: unknown } | null)?.status === 404;

/**
 * The live source over today's bank routes. `fetchJson` is the API
 * transport; tests hand in their own. While the server has the routes off,
 * the screen lists the saved records from `records` instead.
 */
export function createBankTransaccionesSource(fetchJson: Fetch = apiFetch, records?: TransaccionesSource): TransaccionesSource {
  return {
    async load(period) {
      const query = new URLSearchParams({ period_start: period.from, period_end: period.to ?? todayIso() });
      try {
        const [unmatched, suggestions] = await Promise.all([
          fetchJson<unknown>(`/business/bank/unmatched?${query}`),
          fetchJson<unknown>("/business/bank/suggestions?status=pending"),
        ]);
        return mapBankWire(parseBankWire(unmatched, suggestions));
      } catch (error) {
        if (records && bankRoutesOff(error)) return records.load(period);
        throw error;
      }
    },
    async decide(decision: Decision, idempotencyKey: string) {
      if (decision.kind !== "igualar" && decision.kind !== "rechazar") throw new Error(`bank: ${decision.kind} is not served yet`);
      const verb = decision.kind === "igualar" ? "confirm" : "decline";
      await fetchJson(`/business/bank/suggestions/${encodeURIComponent(decision.suggestionId)}/${verb}`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey } });
    },
    supports: (kind) => SERVED.has(kind),
  };
}

/** The reads the saved records come from: the same expenses read Gastos used, the server's period totals, the accounts, and the month a venta lives in. */
export type RecordReads = Readonly<{
  expenses: (from: string, to: string | null) => Promise<BusinessExpense[]>;
  overview: (from: string, to: string | null) => Promise<BusinessOverview>;
  workspace: () => Promise<Pick<BusinessWorkspaceInfo, "accounts">>;
  /** One calendar month of documents, `YYYY-MM`: the one read that serves ventas today. */
  month: (month: string) => Promise<MonthCloseSnapshot>;
  /** The account words for an expense paid from the owner's own money. */
  ownerFunds: string;
}>;

/** Ventas come a month at a time; a longer period would read past what is worth a page load, so its Entradas reads as unknown. */
const VENTAS_MONTHS = 13;

/** Every `YYYY-MM` from `from`'s month through `to`'s, oldest first. */
function monthsBetween(from: string, to: string): string[] {
  const months: string[] = [];
  let year = Number(from.slice(0, 4));
  let month = Number(from.slice(5, 7));
  const last = to.slice(0, 7);
  for (let key = from.slice(0, 7); key <= last; key = `${year}-${String(month).padStart(2, "0")}`) {
    months.push(key);
    month += 1;
    if (month > 12) { month = 1; year += 1; }
  }
  return months;
}

const ACCOUNT_KINDS: Record<string, AccountKind> = { checking: "bank", savings: "bank", credit_card: "card", cash: "cash" };

function accountOf(expense: BusinessExpense, accounts: readonly BusinessAccount[], ownerFunds: string): MovementAccount | null {
  if (expense.funding === "owner_funds") return { kind: "cash", name: ownerFunds, last4: null };
  const account = accounts.find((item) => item.id === expense.account_id);
  return account?.nickname ? { kind: ACCOUNT_KINDS[account.type] ?? "bank", name: account.nickname, last4: null } : null;
}

function gastoRow(expense: BusinessExpense, accounts: readonly BusinessAccount[], ownerFunds: string): RecordRow {
  return {
    id: expense.id,
    kind: "gasto",
    occurredOn: expense.occurred_on,
    counterparty: expense.merchant,
    money: { amount: `-${expense.amount.replace(/^[-+]/, "")}`, currency: expense.currency },
    categoryId: expense.category_id,
    account: accountOf(expense, accounts, ownerFunds),
    hasProof: Boolean(expense.receipt_id),
    marks: { personal: Boolean(expense.personal), markedBy: expense.personal_marked_by ?? null, fiscal: recordFiscalMark(expense) },
    opens: expensePanel(expense),
  };
}

function ventaRow(document: MonthCloseDocument): RecordRow {
  // The month read does not say whether a file backs the venta, and an invoice has no record screen yet.
  return { id: document.id, kind: "venta", occurredOn: document.occurred_on, counterparty: document.counterparty, money: { amount: document.amount, currency: document.currency }, categoryId: null, account: null, hasProof: null, marks: { personal: false, markedBy: null, fiscal: null }, opens: null };
}

const newestFirst = (left: RecordRow, right: RecordRow) => right.occurredOn.localeCompare(left.occurredOn) || left.id.localeCompare(right.id);

/**
 * The saved gastos and ventas of a period, with no statement to igualar
 * against. Salidas is the server's own "Gastos reales" for the period, so a
 * personal gasto stays listed, marked, and out of it. Entradas is the exact
 * sum of the ventas listed, unknown when the period is too long to read.
 */
export function createRecordsTransaccionesSource(reads: RecordReads): TransaccionesSource {
  return {
    async load(period): Promise<RecordsView> {
      const to = period.to ?? todayIso();
      const months = monthsBetween(period.from, to);
      const [expenses, overview, workspace, snapshots] = await Promise.all([
        reads.expenses(period.from, period.to),
        reads.overview(period.from, period.to),
        reads.workspace(),
        months.length <= VENTAS_MONTHS ? Promise.all(months.map((month) => reads.month(month))) : Promise.resolve(null),
      ]);
      const last = period.to ?? overview.today;
      const ventas = snapshots === null ? null : snapshots.flatMap((snapshot) => snapshot.documents).filter((document) => document.kind === "invoice" && document.occurred_on >= period.from && document.occurred_on <= last).map(ventaRow);
      return {
        mode: "records",
        records: [...expenses.map((expense) => gastoRow(expense, workspace.accounts, reads.ownerFunds)), ...(ventas ?? [])].sort(newestFirst),
        totals: {
          entradas: ventas === null ? null : sumByCurrency(ventas.map((row) => row.money)),
          salidas: overview.totals.map((total) => ({ amount: total.amount, currency: total.currency })),
        },
      };
    },
    async decide() {
      throw new Error("records: nothing to igualar");
    },
    supports: () => false,
  };
}
