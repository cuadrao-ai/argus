import { openItemsHeaderCurrency } from "@/lib/business-month-close";

/**
 * Transacciones, as the screen reads it. A row is a movement (money that
 * moved) or an approved document with no movement; its `match` says how it
 * stands against its proof. Every adapter maps its source into these types,
 * so the screen never reads a wire shape.
 */

/** Signed decimal text in the currency's own exponent, exactly as the server sends it: below zero is money out. */
export type Money = Readonly<{ amount: string; currency: string }>;

export type DocumentKind = "recibo" | "venta";

export type DocumentSummary = Readonly<{
  id: string;
  kind: DocumentKind;
  counterparty: string | null;
  occurredOn: string;
  rnc: string | null;
  /** The paper NCF or the e-CF, whichever the document carries. */
  ncf: string | null;
  itbis: Money | null;
  total: Money;
}>;

/** Why the server offered a pair, in words the tray can say. `days` is the document's date minus the movement's. */
export type SuggestionReason = { kind: "amount" } | { kind: "date"; days: number } | { kind: "name" };

export type Suggestion = Readonly<{
  id: string;
  /** The server's confidence, 0 to 1; it orders the run and is never shown as a number. */
  confidence: number;
  document: DocumentSummary;
  reasons: readonly SuggestionReason[];
}>;

export const NO_COMPROBANTE_REASONS = ["cargo_banco", "entre_cuentas", "compra_informal", "personal"] as const;
export type NoComprobanteReason = (typeof NO_COMPROBANTE_REASONS)[number];
/** A zero-amount line needs no comprobante by the server's own rule; nobody chose it, so nobody can take it back. */
export type NoLlevaReason = NoComprobanteReason | "monto_cero";

/** How a row stands against its proof. Each state carries only what it can know. */
export type Match =
  | { state: "igualada"; document: DocumentSummary | null }
  | { state: "sugerencia"; suggestion: Suggestion }
  | { state: "falta_comprobante" }
  | { state: "no_lleva"; reason: NoLlevaReason }
  | { state: "sin_movimiento"; document: DocumentSummary };

export type MatchState = Match["state"];

export type AccountKind = "bank" | "card" | "cash";
export type MovementAccount = Readonly<{ kind: AccountKind; name: string | null }>;

export type Movement = Readonly<{
  id: string;
  occurredOn: string;
  counterparty: string | null;
  /** The bank's own text for the line; null for a document with no movement. */
  bankText: string | null;
  money: Money;
  categoryId: string | null;
  account: MovementAccount | null;
  match: Match;
}>;

export type Counts = Readonly<{
  movimientos: number;
  igualadas: number;
  noLleva: number;
  sugerencias: number;
  faltaComprobante: number;
  sinMovimiento: number;
  porIgualar: number;
}>;

/** One currency's totals for the whole period, whatever the segment or page. Currencies are never added together. */
export type CurrencyTotals = Readonly<{ currency: string; entradas: string; salidas: string; porIgualar: string; counts: Counts }>;

export type Segment = "por_igualar" | "igualadas" | "todas";
export const SEGMENTS: readonly Segment[] = ["por_igualar", "igualadas", "todas"];

/** How many rows of the segment another currency holds, which the chosen currency leaves out. */
export type OtherCurrency = Readonly<{ currency: string; count: number }>;

export type IgualarView = Readonly<{
  mode: "igualar";
  segment: Segment;
  /** The currency the rows and totals follow; null when the server lists every currency. */
  currency: string | null;
  /** The segment's rows in the server's order, every page read so far. */
  movements: readonly Movement[];
  nextCursor: string | null;
  /** With a currency, only its block, and none when the period has no row in it. */
  totals: readonly CurrencyTotals[];
  /** The period's counts across every currency, whatever the segment, currency or page. Null when the server does not send them. */
  counts: Counts | null;
  otherCurrencies: readonly OtherCurrency[];
  /** The currency of the account the statement comes from, for a total of a period with no rows. */
  accountCurrency: string | null;
  /** The last statement day the bank covers; null when no statement says. */
  coverageThrough: string | null;
}>;

export type RecordKind = "gasto" | "venta";

/** Where a saved record opens: the existing record tray's receipt, draft or plain expense. */
export type RecordTarget =
  | { kind: "receipt"; receiptId: string; list: "transactions" }
  | { kind: "draft"; draftId: string; list: "transactions" }
  | { kind: "expense"; expenseId: string };

/** A saved gasto or venta, as the screen lists it with no statement to igualar against. */
export type RecordRow = Readonly<{
  id: string;
  kind: RecordKind;
  occurredOn: string;
  counterparty: string | null;
  /** Signed like a movement: a gasto is money out, a venta money in. */
  money: Money;
  categoryId: string | null;
  account: MovementAccount | null;
  /** Its file: true shows the receipt icon, false nothing, null unknown. */
  hasProof: boolean | null;
  /** A personal gasto stays listed but out of Salidas, so the row says so; the fiscal mark is the same one Gastos showed. */
  marks: Readonly<{ personal: boolean; markedBy: string | null; fiscal: "sin_comprobante" | "missing_ncf" | null }>;
  /** Null while the record has no screen of its own. */
  opens: RecordTarget | null;
}>;

/** Salidas is the server's own total. No read serves a total of the period's ventas, so Entradas reads as unknown. */
export type RecordsTotals = Readonly<{ salidas: readonly Money[] }>;

/**
 * With no statement to igualar against, the screen lists the period's saved
 * gastos and ventas: no Por igualar flags, no suggestions, no coverage.
 */
export type RecordsView = Readonly<{ mode: "records"; records: readonly RecordRow[]; totals: RecordsTotals }>;

export type TransaccionesView = IgualarView | RecordsView;

/** Taking an outcome back names the outcome, so the inverse can put it back. */
export type Outcome = { kind: "match"; documentId: string } | { kind: "no_receipt"; reason: NoComprobanteReason };

export type Decision =
  | { kind: "igualar"; movementId: string; suggestionId: string; documentId: string }
  | { kind: "igualar_con"; movementId: string; documentId: string }
  | { kind: "rechazar"; movementId: string; suggestionId: string }
  | { kind: "sin_comprobante"; movementId: string; reason: NoComprobanteReason }
  | { kind: "desigualar"; movementId: string; outcome: Outcome };

export type DecisionKind = Decision["kind"];

/** The decision that takes this one back, or null when the server keeps it for good: a declined pair never returns. */
export function inverse(decision: Decision): Decision | null {
  switch (decision.kind) {
    case "igualar":
    case "igualar_con":
      return { kind: "desigualar", movementId: decision.movementId, outcome: { kind: "match", documentId: decision.documentId } };
    case "sin_comprobante":
      return { kind: "desigualar", movementId: decision.movementId, outcome: { kind: "no_receipt", reason: decision.reason } };
    case "desigualar":
      return decision.outcome.kind === "match"
        ? { kind: "igualar_con", movementId: decision.movementId, documentId: decision.outcome.documentId }
        : { kind: "sin_comprobante", movementId: decision.movementId, reason: decision.outcome.reason };
    case "rechazar":
      return null;
  }
}

/** One past outcome of a line, oldest first. */
export type HistoryEntry = Readonly<{ id: string; outcome: "match" | "no_receipt"; documentKind: DocumentKind | null; reason: NoComprobanteReason | null; from: string; until: string | null }>;

/** `currency` null reads every currency. A cursor is only a position in the list its segment and currency name. */
export type LoadRequest = Readonly<{ from: string; to: string | null; segment: Segment; currency?: string | null; cursor?: string | null; limit?: number }>;

/** The seam the backend plugs into. The screen re-reads after every decision; it never moves a row itself. */
export type TransaccionesSource = Readonly<{
  load: (request: LoadRequest) => Promise<TransaccionesView>;
  decide: (decision: Decision, idempotencyKey: string) => Promise<void>;
  history: (movementId: string) => Promise<readonly HistoryEntry[]>;
}>;

export type Group = "sugerencias" | "falta_comprobante" | "sin_movimiento";
export const GROUPS: readonly Group[] = ["sugerencias", "falta_comprobante", "sin_movimiento"];

/** Where each state lives: its Por igualar group, and the count that names the group. */
const GROUP_OF: Record<MatchState, Group | null> = { igualada: null, sugerencia: "sugerencias", falta_comprobante: "falta_comprobante", no_lleva: null, sin_movimiento: "sin_movimiento" };
const GROUP_COUNT: Record<Group, keyof Counts> = { sugerencias: "sugerencias", falta_comprobante: "faltaComprobante", sin_movimiento: "sinMovimiento" };

const NO_ROWS: Counts = { movimientos: 0, igualadas: 0, noLleva: 0, sugerencias: 0, faltaComprobante: 0, sinMovimiento: 0, porIgualar: 0 };

/**
 * The server's counts for the rows the table covers: the chosen currency's own
 * block (none means no row in it), or the period's while every currency is
 * listed. Null when the server does not send them.
 */
export function tableCounts(view: IgualarView): Counts | null {
  if (view.currency === null) return view.counts;
  return view.totals.find((block) => block.currency === view.currency)?.counts ?? NO_ROWS;
}

/** The currencies the person can switch the table to: the Business currency first, the chosen one, and each the server says holds rows. */
export function currencyChoices(view: IgualarView, businessCurrency: string | null): string[] {
  if (view.currency === null) return [];
  const found = new Set([view.currency, ...view.totals.map((block) => block.currency), ...view.otherCurrencies.map((other) => other.currency)]);
  if (businessCurrency) found.add(businessCurrency);
  return [...found].sort((left, right) => Number(right === businessCurrency) - Number(left === businessCurrency));
}

/** One figure per currency, never added across them. */
export function perCurrency(totals: readonly CurrencyTotals[], key: "entradas" | "salidas" | "porIgualar"): Money[] {
  return totals.map((block) => ({ currency: block.currency, amount: block[key] }));
}

export type Section = Readonly<{ group: Group | null; count: number | null; rows: readonly Movement[] }>;

/**
 * The rows a segment shows, in the server's order. Por igualar comes in its
 * three groups, each named with the server's count for the rows the table covers.
 */
export function segmentSections(view: IgualarView): Section[] {
  if (view.segment !== "por_igualar") return [{ group: null, count: null, rows: view.movements }];
  const counts = tableCounts(view);
  return GROUPS.map((group) => ({ group, count: counts ? counts[GROUP_COUNT[group]] : null, rows: view.movements.filter((movement) => GROUP_OF[movement.match.state] === group) }))
    .filter((section) => section.rows.length > 0);
}

/** The suggestion run: the Por igualar segment's suggestions, in the server's order, most confident first. */
export function suggestionRun(view: IgualarView): Movement[] {
  return view.segment === "por_igualar" ? view.movements.filter((movement) => movement.match.state === "sugerencia") : [];
}

/** The currency the Monto header names: the Business currency when a row holds it, else the only currency, else none. One owner: `openItemsHeaderCurrency`. */
export function headerCurrency(rows: readonly Readonly<{ money: Money }>[], businessCurrency: string | null = null): string | null {
  return openItemsHeaderCurrency({ count: 0, overdue: null, items: [], totals: rows.map((row) => ({ currency: row.money.currency, total: row.money.amount })) }, businessCurrency);
}

/** Totals in one currency each, the header's first. Never added across currencies. */
export function inHeaderOrder(totals: readonly Money[], header: string | null): Money[] {
  return [...totals].sort((left, right) => Number(right.currency === header) - Number(left.currency === header));
}

export type Sign = "in" | "out" | "zero";
export function signOf(money: Money): Sign {
  const trimmed = money.amount.trim();
  if (/^-?0*(\.0*)?$/.test(trimmed)) return "zero";
  return trimmed.startsWith("-") ? "out" : "in";
}

/** The amount without its sign, for a renderer that draws the sign itself. */
export function magnitude(money: Money): Money {
  return { ...money, amount: money.amount.trim().replace(/^[-+]/, "") };
}
