import { formatDopCents, openItemsHeaderCurrency, parseDopCents } from "@/lib/business-month-close";

/**
 * Transacciones, as the screen reads it. A row is a movement (money that
 * moved) or an approved document with no movement; its `match` says how it
 * stands against its proof. Every adapter maps its source into these types,
 * so the screen never reads a wire shape.
 */

/** Signed decimal text, exactly as the server sends it: below zero is money out. */
export type Money = Readonly<{ amount: string; currency: string }>;

export type DocumentKind = "recibo" | "venta";

export type DocumentSummary = Readonly<{
  id: string;
  kind: DocumentKind;
  counterparty: string | null;
  occurredOn: string | null;
  rnc: string | null;
  ncf: string | null;
  itbis: Money | null;
  total: Money | null;
}>;

/** Why the server offered a pair, in words the tray can say. `daysBefore` is null when the server did not say. */
export type SuggestionReason = { kind: "amount" } | { kind: "date"; daysBefore: number | null } | { kind: "name" };

export type Suggestion = Readonly<{
  id: string;
  /** The server's confidence, 0 to 1; it orders the run and is never shown as a number. */
  confidence: number | null;
  documentKind: DocumentKind;
  /** Null while the server sends only the document's id. */
  document: DocumentSummary | null;
  reasons: readonly SuggestionReason[];
}>;

export const NO_COMPROBANTE_REASONS = ["cargo_banco", "entre_cuentas", "compra_informal", "personal"] as const;
export type NoComprobanteReason = (typeof NO_COMPROBANTE_REASONS)[number];

/** How a row stands against its proof. Each state carries only what it can know. */
export type Match =
  | { state: "igualada"; document: DocumentSummary | null }
  | { state: "sugerencia"; suggestion: Suggestion }
  | { state: "falta_comprobante" }
  | { state: "igualada_en_parte"; document: DocumentSummary | null; missing: Money }
  | { state: "no_lleva"; reason: NoComprobanteReason }
  | { state: "sin_movimiento"; document: DocumentSummary };

export type MatchState = Match["state"];

export type AccountKind = "bank" | "card" | "cash";
export type MovementAccount = Readonly<{ kind: AccountKind; name: string; last4: string | null }>;

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

/** The server's totals for the period. A null part is one the server does not serve: the screen shows it as unknown. */
export type Totals = Readonly<{
  entradas: readonly Money[] | null;
  salidas: readonly Money[] | null;
  porIgualar: Readonly<{ count: number; amounts: readonly Money[] | null }> | null;
  igualadas: Readonly<{ count: number; of: number }> | null;
}>;

export type IgualarView = Readonly<{
  mode: "igualar";
  movements: readonly Movement[];
  totals: Totals;
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
  /** Null while the record has no screen of its own (a venta today). */
  opens: RecordTarget | null;
}>;

/** A null total is one no read can give exactly for this period: the screen shows it as unknown. */
export type RecordsTotals = Readonly<{ entradas: readonly Money[] | null; salidas: readonly Money[] | null }>;

/**
 * With no statement to igualar against, the screen lists the period's saved
 * gastos and ventas: no Por igualar flags, no suggestions, no coverage.
 */
export type RecordsView = Readonly<{ mode: "records"; records: readonly RecordRow[]; totals: RecordsTotals }>;

export type TransaccionesView = IgualarView | RecordsView;

export type Decision =
  | { kind: "igualar"; movementId: string; suggestionId: string }
  | { kind: "rechazar"; movementId: string; suggestionId: string }
  | { kind: "sin_comprobante"; movementId: string; reason: NoComprobanteReason }
  | { kind: "desigualar"; movementId: string };

export type DecisionKind = Decision["kind"];

/**
 * The seam the backend plugs into. `supports` says which decisions the
 * server takes today; `undo` is absent while the server cannot take a
 * decision back, and the screen then offers no Deshacer.
 */
export type TransaccionesSource = Readonly<{
  load: (period: Readonly<{ from: string; to: string | null }>) => Promise<TransaccionesView>;
  decide: (decision: Decision, idempotencyKey: string) => Promise<void>;
  supports: (kind: DecisionKind) => boolean;
  undo?: (decision: Decision) => Promise<void>;
}>;

export type Segment = "por_igualar" | "igualadas" | "todas";
export const SEGMENTS: readonly Segment[] = ["por_igualar", "igualadas", "todas"];
export type Group = "sugerencias" | "falta_comprobante" | "sin_movimiento";
export const GROUPS: readonly Group[] = ["sugerencias", "falta_comprobante", "sin_movimiento"];

/** Where each state lives: its segment, its Por igualar group, and the actions a row in it offers. */
export const MATCH_STATES: Record<MatchState, Readonly<{ segment: "por_igualar" | "igualadas"; group: Group | null; actions: readonly DecisionKind[] }>> = {
  igualada: { segment: "igualadas", group: null, actions: ["desigualar"] },
  sugerencia: { segment: "por_igualar", group: "sugerencias", actions: ["igualar", "rechazar", "sin_comprobante"] },
  falta_comprobante: { segment: "por_igualar", group: "falta_comprobante", actions: ["sin_comprobante"] },
  igualada_en_parte: { segment: "por_igualar", group: "falta_comprobante", actions: ["desigualar"] },
  no_lleva: { segment: "igualadas", group: null, actions: ["desigualar"] },
  sin_movimiento: { segment: "por_igualar", group: "sin_movimiento", actions: [] },
};

/** The actions a row offers now: what its state allows and the source takes. */
export function rowActions(movement: Movement, source: Pick<TransaccionesSource, "supports">): DecisionKind[] {
  return MATCH_STATES[movement.match.state].actions.filter((kind) => source.supports(kind));
}

const newestFirst = (left: Movement, right: Movement) => (left.occurredOn === right.occurredOn ? left.id.localeCompare(right.id) : left.occurredOn < right.occurredOn ? 1 : -1);
const confidenceOf = (movement: Movement) => (movement.match.state === "sugerencia" ? movement.match.suggestion.confidence ?? 0 : 0);

export type Section = Readonly<{ group: Group | null; rows: readonly Movement[] }>;

/**
 * The rows a segment shows. Por igualar comes in its three groups, the
 * suggestions most confident first; the others are one list, by date.
 */
export function segmentSections(movements: readonly Movement[], segment: Segment, order: "desc" | "asc" = "desc"): Section[] {
  const byDate = (left: Movement, right: Movement) => (order === "desc" ? newestFirst(left, right) : -newestFirst(left, right));
  if (segment !== "por_igualar") {
    const rows = movements.filter((movement) => segment === "todas" || MATCH_STATES[movement.match.state].segment === segment);
    return [{ group: null, rows: [...rows].sort(byDate) }];
  }
  return GROUPS.map((group) => {
    const rows = movements.filter((movement) => MATCH_STATES[movement.match.state].group === group);
    return { group, rows: group === "sugerencias" ? [...rows].sort((left, right) => confidenceOf(right) - confidenceOf(left) || newestFirst(left, right)) : [...rows].sort(byDate) };
  }).filter((section) => section.rows.length > 0);
}

/** The suggestion run: every pending suggestion, most confident first. */
export function suggestionRun(movements: readonly Movement[]): Movement[] {
  return [...(segmentSections(movements, "por_igualar").find((section) => section.group === "sugerencias")?.rows ?? [])];
}

export function segmentCount(movements: readonly Movement[], segment: Segment): number {
  return segmentSections(movements, segment).reduce((sum, section) => sum + section.rows.length, 0);
}

/** Por igualar when it has rows; Todas otherwise. */
export function defaultSegment(movements: readonly Movement[]): Segment {
  return segmentCount(movements, "por_igualar") > 0 ? "por_igualar" : "todas";
}

/** The currency the Monto header names: DOP when any row is in pesos. One owner: `openItemsHeaderCurrency`. */
export function headerCurrency(rows: readonly Readonly<{ money: Money }>[]): string | null {
  return openItemsHeaderCurrency({ count: 0, items: [], totals: rows.map((row) => ({ currency: row.money.currency, total: row.money.amount })) });
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

/** Exact sums of the amounts' sizes in minor units, one per currency, in the order each currency first appears. */
export function sumByCurrency(items: readonly Money[]): Money[] {
  const totals = new Map<string, bigint>();
  for (const item of items) totals.set(item.currency, (totals.get(item.currency) ?? BigInt(0)) + parseDopCents(magnitude(item).amount));
  return [...totals].map(([currency, cents]) => ({ currency, amount: formatDopCents(cents) }));
}

/** The amount without its sign, for a renderer that draws the sign itself. */
export function magnitude(money: Money): Money {
  return { ...money, amount: money.amount.trim().replace(/^[-+]/, "") };
}

/** The unknown mark: a value the system does not know. Screen readers hear "sin dato". */
export const UNKNOWN = "—";
