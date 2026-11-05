import { apiFetch } from "@/lib/argus-api-transport";
import type { BusinessAccount, BusinessExpense, BusinessOverview, BusinessWorkspaceInfo } from "@/lib/business-api";
import { todayIso } from "../business-format";
import { expensePanel } from "../business-expense-target";
import { recordFiscalMark } from "../business-ui";
import {
  NO_COMPROBANTE_REASONS,
  type AccountKind,
  type Counts,
  type CurrencyTotals,
  type Decision,
  type DocumentSummary,
  type HistoryEntry,
  type IgualarView,
  type Match,
  type Movement,
  type MovementAccount,
  type OtherCurrency,
  type RecordKind,
  type RecordRow,
  type RecordsView,
  type SuggestionReason,
  type TransaccionesSource,
} from "./transacciones-model";

/**
 * The one place the bank routes meet the screen. `GET /business/bank/movements`
 * serves the period's rows in one currency with their server-owned state, a
 * page at a time, that currency's totals and the period's counts; the
 * decisions are one route each. A shape the screen cannot trust fails the
 * load, never half-renders.
 */

class BankWireError extends Error {
  readonly code = "bank_wire_shape";
}

const fail = (field: string, what: string): never => {
  throw new BankWireError(`bank: ${field} ${what}`);
};
const record = (value: unknown, field: string): Record<string, unknown> => (typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : fail(field, "is not an object"));
const list = (value: unknown, field: string): unknown[] => (Array.isArray(value) ? value : fail(field, "is not a list"));
const text = (value: unknown, field: string): string => (typeof value === "string" ? value : fail(field, "is not text"));
const maybeText = (value: unknown, field: string): string | null => (value === null ? null : text(value, field));
const integer = (value: unknown, field: string): number => (typeof value === "number" && Number.isInteger(value) ? value : fail(field, "is not a whole number"));
const day = (value: unknown, field: string): string => {
  const raw = text(value, field);
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : fail(field, "is not a day");
};
const maybeDay = (value: unknown, field: string): string | null => (value === null ? null : day(value, field));
const currency = (value: unknown, field: string): string => {
  const raw = text(value, field);
  return /^[A-Z]{3}$/.test(raw) ? raw : fail(field, "is not a currency code");
};
/** Decimal text in the currency's exponent, as the server formats it from minor units. */
const decimal = (value: unknown, field: string): string => {
  const raw = text(value, field).trim();
  return /^-?\d+(\.\d+)?$/.test(raw) ? raw : fail(field, "is not a decimal");
};
function oneOf<T extends string>(value: unknown, allowed: readonly T[], field: string): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : fail(field, "is unknown");
}

const ACCOUNT_KINDS: Record<string, AccountKind> = { checking: "bank", savings: "bank", credit_card: "card", cash: "cash" };

function parseDocument(value: unknown, field: string): DocumentSummary {
  const wire = record(value, field);
  const money = currency(wire.currency, `${field}.currency`);
  integer(wire.total_minor, `${field}.total_minor`);
  if (wire.itbis_minor !== null) integer(wire.itbis_minor, `${field}.itbis_minor`);
  const itbis = wire.itbis === null ? null : decimal(wire.itbis, `${field}.itbis`);
  return {
    id: text(wire.activity_id, `${field}.activity_id`),
    kind: oneOf(wire.kind, ["receipt", "venta"] as const, `${field}.kind`) === "venta" ? "venta" : "recibo",
    counterparty: maybeText(wire.counterparty, `${field}.counterparty`),
    occurredOn: day(wire.occurred_on, `${field}.occurred_on`),
    rnc: maybeText(wire.rnc, `${field}.rnc`),
    ncf: maybeText(wire.ncf, `${field}.ncf`) ?? maybeText(wire.ecf, `${field}.ecf`),
    itbis: itbis === null ? null : { amount: itbis, currency: money },
    total: { amount: decimal(wire.total, `${field}.total`), currency: money },
  };
}

const REASON_CODES = ["monto_exacto", "misma_fecha", "fecha_cercana", "nombre_parecido"] as const;

function parseReason(value: unknown, field: string): SuggestionReason {
  const wire = record(value, field);
  const code = oneOf(wire.code, REASON_CODES, `${field}.code`);
  if (code === "monto_exacto") return { kind: "amount" };
  if (code === "nombre_parecido") return { kind: "name" };
  if (code === "misma_fecha") return { kind: "date", days: 0 };
  return { kind: "date", days: integer(wire.days, `${field}.days`) };
}

function parseMatch(wire: Record<string, unknown>, field: string): Match {
  const state = oneOf(wire.state, ["igualada", "sugerencia", "falta_comprobante", "no_lleva_comprobante", "sin_movimiento"] as const, `${field}.state`);
  switch (state) {
    case "igualada":
      return { state: "igualada", document: wire.document === null ? null : parseDocument(wire.document, `${field}.document`) };
    case "sugerencia": {
      const [best] = list(wire.suggestions, `${field}.suggestions`);
      const suggestion = record(best ?? fail(`${field}.suggestions`, "is empty on a suggestion"), `${field}.suggestions[0]`);
      const confidence = Number(decimal(suggestion.confidence, `${field}.suggestions[0].confidence`));
      return {
        state: "sugerencia",
        suggestion: {
          id: text(suggestion.id, `${field}.suggestions[0].id`),
          confidence,
          document: parseDocument(suggestion.document, `${field}.suggestions[0].document`),
          reasons: list(suggestion.reasons, `${field}.suggestions[0].reasons`).map((reason, index) => parseReason(reason, `${field}.suggestions[0].reasons[${index}]`)),
        },
      };
    }
    case "falta_comprobante":
      return { state: "falta_comprobante" };
    case "no_lleva_comprobante":
      return { state: "no_lleva", reason: oneOf(wire.reason, [...NO_COMPROBANTE_REASONS, "monto_cero"] as const, `${field}.reason`) };
    case "sin_movimiento":
      return { state: "sin_movimiento", document: parseDocument(wire.document, `${field}.document`) };
  }
}

function parseAccount(value: unknown, field: string): MovementAccount {
  const wire = record(value, field);
  return { kind: ACCOUNT_KINDS[text(wire.type, `${field}.type`)] ?? "bank", name: maybeText(wire.name, `${field}.name`) };
}

/** One movements item, the shape the list and every decision route answer with. */
export function parseMovementItem(value: unknown, field = "item"): Movement {
  const wire = record(value, field);
  oneOf(wire.kind, ["movement", "document"] as const, `${field}.kind`);
  integer(wire.amount_minor, `${field}.amount_minor`);
  return {
    id: text(wire.id, `${field}.id`),
    occurredOn: day(wire.occurred_on, `${field}.occurred_on`),
    counterparty: maybeText(wire.counterparty, `${field}.counterparty`),
    bankText: maybeText(wire.description, `${field}.description`),
    money: { amount: decimal(wire.amount, `${field}.amount`), currency: currency(wire.currency, `${field}.currency`) },
    categoryId: maybeText(wire.category_id, `${field}.category_id`),
    account: wire.account === null ? null : parseAccount(wire.account, `${field}.account`),
    match: parseMatch(wire, field),
  };
}

function parseCounts(value: unknown, field: string): Counts {
  const wire = record(value, field);
  const count = (key: string) => integer(wire[key], `${field}.${key}`);
  return {
    movimientos: count("movimientos"),
    igualadas: count("igualadas"),
    noLleva: count("no_lleva_comprobante"),
    sugerencias: count("sugerencias"),
    faltaComprobante: count("falta_comprobante"),
    sinMovimiento: count("sin_movimiento"),
    porIgualar: count("por_igualar"),
  };
}

function parseTotals(value: unknown, field: string): CurrencyTotals {
  const wire = record(value, field);
  for (const key of ["entradas_minor", "salidas_minor", "por_igualar_minor"]) integer(wire[key], `${field}.${key}`);
  return {
    currency: currency(wire.currency, `${field}.currency`),
    entradas: decimal(wire.entradas, `${field}.entradas`),
    salidas: decimal(wire.salidas, `${field}.salidas`),
    porIgualar: decimal(wire.por_igualar, `${field}.por_igualar`),
    counts: parseCounts(wire.counts, `${field}.counts`),
  };
}

function parseOtherCurrency(value: unknown, field: string): OtherCurrency {
  const wire = record(value, field);
  return { currency: currency(wire.currency, `${field}.currency`), count: integer(wire.count, `${field}.count`) };
}

export type MovementsPage = Readonly<{ view: IgualarView; hasStatement: boolean }>;

/**
 * `GET /business/bank/movements` as the view model. `hasStatement` is false
 * while no account has an imported line. A server older than the currency
 * filter sends no `currency`, `counts` or `other_currencies`: every currency
 * listed, counts unknown, nothing named as left out.
 */
export function parseMovementsPage(value: unknown): MovementsPage {
  const wire = record(value, "movements");
  const segment = oneOf(wire.segment, ["por_igualar", "igualadas", "todas"] as const, "movements.segment");
  const accounts = list(wire.accounts, "movements.accounts").map((account, index) => {
    const row = record(account, `movements.accounts[${index}]`);
    return { currency: currency(row.currency, `movements.accounts[${index}].currency`), coveredThrough: maybeDay(row.covered_through, `movements.accounts[${index}].covered_through`) };
  });
  const covered = accounts.map((account) => account.coveredThrough).filter((through): through is string => through !== null).sort();
  return {
    hasStatement: covered.length > 0,
    view: {
      mode: "igualar",
      segment,
      currency: wire.currency === undefined || wire.currency === null ? null : currency(wire.currency, "movements.currency"),
      movements: list(wire.items, "movements.items").map((item, index) => parseMovementItem(item, `movements.items[${index}]`)),
      nextCursor: maybeText(wire.next_cursor, "movements.next_cursor"),
      totals: list(wire.totals, "movements.totals").map((block, index) => parseTotals(block, `movements.totals[${index}]`)),
      counts: wire.counts === undefined ? null : parseCounts(wire.counts, "movements.counts"),
      otherCurrencies: wire.other_currencies === undefined ? [] : list(wire.other_currencies, "movements.other_currencies").map((other, index) => parseOtherCurrency(other, `movements.other_currencies[${index}]`)),
      accountCurrency: accounts[0]?.currency ?? null,
      // With more than one account, the bank is up to date only through the one that is furthest behind.
      coverageThrough: covered[0] ?? null,
    },
  };
}

export function parseHistory(value: unknown): HistoryEntry[] {
  return list(value, "history").map((entry, index) => {
    const wire = record(entry, `history[${index}]`);
    const field = `history[${index}]`;
    const outcome = oneOf(wire.kind, ["match", "no_receipt"] as const, `${field}.kind`);
    const target = wire.target_kind === null ? null : oneOf(wire.target_kind, ["receipt", "venta"] as const, `${field}.target_kind`);
    return {
      id: text(wire.id, `${field}.id`),
      outcome,
      documentKind: target === null ? null : target === "venta" ? "venta" : "recibo",
      reason: wire.reason === null ? null : oneOf(wire.reason, NO_COMPROBANTE_REASONS, `${field}.reason`),
      from: text(wire.created_at, `${field}.created_at`),
      until: maybeText(wire.ended_at, `${field}.ended_at`),
    };
  });
}

/** What the screen says when a decision fails, and the way out it offers. */
export type DecisionProblemCode =
  | "line_not_found"
  | "line_marked_no_receipt"
  | "line_not_matched"
  | "line_not_marked"
  | "document_already_matched"
  | "business_document_matched"
  | "document_not_matchable"
  | "changed"
  | "unavailable";
export type DecisionProblem = Readonly<{ code: DecisionProblemCode; action: "retry" | "reload" | "none" }>;

/**
 * The server's refusals. A decision that met a line or a document that moved
 * on reads the list again (Actualizar); one the server will never take offers
 * nothing; a server that could not answer offers Reintentar with the same key.
 */
const REFUSALS: Record<string, DecisionProblem> = {
  line_not_found: { code: "line_not_found", action: "reload" },
  line_marked_no_receipt: { code: "line_marked_no_receipt", action: "reload" },
  line_not_matched: { code: "line_not_matched", action: "reload" },
  line_not_marked: { code: "line_not_marked", action: "reload" },
  document_already_matched: { code: "document_already_matched", action: "reload" },
  business_document_matched: { code: "business_document_matched", action: "reload" },
  document_not_matchable: { code: "document_not_matchable", action: "none" },
  line_already_confirmed: { code: "changed", action: "reload" },
  suggestion_not_pending: { code: "changed", action: "reload" },
  suggestion_not_found: { code: "changed", action: "reload" },
  pair_declined: { code: "changed", action: "reload" },
  target_not_approved: { code: "changed", action: "reload" },
};

export function decisionProblem(error: unknown): DecisionProblem {
  const code = (error as { code?: unknown } | null)?.code;
  return (typeof code === "string" && REFUSALS[code]) || { code: "unavailable", action: "retry" };
}

/** Cargar más with a cursor the server no longer takes: the list changed under it. */
export const listChanged = (error: unknown) => (error as { code?: unknown } | null)?.code === "invalid_cursor";

type Fetch = <T>(path: string, init?: RequestInit) => Promise<T>;

/** The bank routes answer 404 while bank matching is off on the server, or the Business store is not durable. */
const bankRoutesOff = (error: unknown) => (error as { status?: unknown } | null)?.status === 404;

const line = (movementId: string, verb: string) => `/business/bank/movements/${encodeURIComponent(movementId)}/${verb}`;

function decisionRequest(decision: Decision): Readonly<{ path: string; method: string; body?: unknown }> {
  switch (decision.kind) {
    case "igualar":
      return { path: `/business/bank/suggestions/${encodeURIComponent(decision.suggestionId)}/confirm`, method: "POST" };
    case "rechazar":
      return { path: `/business/bank/suggestions/${encodeURIComponent(decision.suggestionId)}/decline`, method: "POST" };
    case "igualar_con":
      return { path: line(decision.movementId, "match"), method: "POST", body: { activity_id: decision.documentId } };
    case "sin_comprobante":
      return { path: line(decision.movementId, "disposition"), method: "PUT", body: { reason: decision.reason } };
    case "desigualar":
      return decision.outcome.kind === "match" ? { path: line(decision.movementId, "unmatch"), method: "POST" } : { path: line(decision.movementId, "disposition"), method: "DELETE" };
  }
}

/**
 * The live source over the bank routes. `fetchJson` is the API transport;
 * tests and the design preview hand in their own. With the routes off, or
 * before any statement is imported, the screen lists the saved records from
 * `records` instead.
 */
export function createBankTransaccionesSource(fetchJson: Fetch = apiFetch, records?: TransaccionesSource): TransaccionesSource {
  return {
    async load(request) {
      const query = new URLSearchParams({ period_start: request.from, period_end: request.to ?? todayIso(), segment: request.segment });
      if (request.currency) query.set("currency", request.currency);
      if (request.limit) query.set("limit", String(request.limit));
      if (request.cursor) query.set("cursor", request.cursor);
      let page: MovementsPage;
      try {
        page = parseMovementsPage(await fetchJson<unknown>(`/business/bank/movements?${query}`));
      } catch (error) {
        if (records && bankRoutesOff(error)) return records.load(request);
        throw error;
      }
      return !page.hasStatement && records ? records.load(request) : page.view;
    },
    async decide(decision, idempotencyKey) {
      const request = decisionRequest(decision);
      await fetchJson(request.path, {
        method: request.method,
        headers: { "Idempotency-Key": idempotencyKey },
        ...(request.body ? { body: JSON.stringify(request.body) } : {}),
      });
    },
    async history(movementId) {
      return parseHistory(await fetchJson<unknown>(line(movementId, "history")));
    },
  };
}

/** The period's ventas: `GET /business/expenses?kind=income`, each in its own currency, `merchant` being the client. */
export function readVentas(fetchJson: Fetch = apiFetch) {
  return async (from: string, to: string | null): Promise<BusinessExpense[]> => {
    const query = new URLSearchParams(to === null ? { from, kind: "income" } : { from, to, kind: "income" });
    return (await fetchJson<{ items: BusinessExpense[] }>(`/business/expenses?${query}`)).items;
  };
}

/** The reads the saved records come from: the same expenses read Gastos used, the period's ventas, the server's period totals, and the accounts. */
export type RecordReads = Readonly<{
  expenses: (from: string, to: string | null) => Promise<BusinessExpense[]>;
  ventas: (from: string, to: string | null) => Promise<BusinessExpense[]>;
  overview: (from: string, to: string | null) => Promise<BusinessOverview>;
  workspace: () => Promise<Pick<BusinessWorkspaceInfo, "accounts">>;
  /** The account words for an expense paid from the owner's own money. */
  ownerFunds: string;
}>;

function accountOf(expense: BusinessExpense, accounts: readonly BusinessAccount[], ownerFunds: string): MovementAccount | null {
  if (expense.funding === "owner_funds") return { kind: "cash", name: ownerFunds };
  const account = accounts.find((item) => item.id === expense.account_id);
  return account?.nickname ? { kind: ACCOUNT_KINDS[account.type] ?? "bank", name: account.nickname } : null;
}

function recordRow(kind: RecordKind, expense: BusinessExpense, accounts: readonly BusinessAccount[], ownerFunds: string): RecordRow {
  const amount = expense.amount.replace(/^[-+]/, "");
  return {
    id: expense.id,
    kind,
    occurredOn: expense.occurred_on,
    counterparty: expense.merchant,
    money: { amount: kind === "gasto" ? `-${amount}` : amount, currency: expense.currency },
    categoryId: expense.category_id,
    account: accountOf(expense, accounts, ownerFunds),
    hasProof: Boolean(expense.receipt_id),
    marks: { personal: Boolean(expense.personal), markedBy: expense.personal_marked_by ?? null, fiscal: recordFiscalMark(expense) },
    // The plain expense read serves expenses only, so a venta opens only through its receipt or draft.
    opens: kind === "gasto" || expense.receipt_id || expense.draft_id ? expensePanel(expense) : null,
  };
}

const newestFirst = (left: RecordRow, right: RecordRow) => right.occurredOn.localeCompare(left.occurredOn) || left.id.localeCompare(right.id);

/**
 * The saved gastos and ventas of a period, with no statement to igualar
 * against. Salidas is the server's own "Gastos reales" for the period, so a
 * personal gasto stays listed, marked, and out of it.
 */
export function createRecordsTransaccionesSource(reads: RecordReads): TransaccionesSource {
  return {
    async load(request): Promise<RecordsView> {
      const [expenses, ventas, overview, workspace] = await Promise.all([reads.expenses(request.from, request.to), reads.ventas(request.from, request.to), reads.overview(request.from, request.to), reads.workspace()]);
      return {
        mode: "records",
        records: [
          ...expenses.map((expense) => recordRow("gasto", expense, workspace.accounts, reads.ownerFunds)),
          ...ventas.map((venta) => recordRow("venta", venta, workspace.accounts, reads.ownerFunds)),
        ].sort(newestFirst),
        totals: { salidas: overview.totals.map((total) => ({ amount: total.amount, currency: total.currency })) },
      };
    },
    async decide() {
      throw new Error("records: nothing to igualar");
    },
    async history() {
      return [];
    },
  };
}
