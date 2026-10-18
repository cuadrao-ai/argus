import { apiFetch } from "./argus-api-transport";

/**
 * Cuadrar el mes. `monthCloseClient` is the live client `/biz` uses.
 * The preview keeps `createMockMonthCloseClient()`.
 *
 * Assumed HTTP contract, under `/api/v1`:
 *
 * - `GET /business/month-close?month=YYYY-MM`
 *   The selected month is the only query. `closed` is derived: true when
 *   every business document has an RNC and a fiscal number. There is no
 *   close request.
 * - `PATCH /business/month-close/documents/{activity_id}`
 *   Body: `status`, `settled_on`, `payment_method`. A settled status needs
 *   both a date and a method. Pending omits them.
 *
 * Money is DOP decimal text with at most two fraction digits, never a float.
 * `amount` is the document total. `itbis` is the ITBIS printed on it, or null
 * when the document does not state one. The web does not invent ITBIS from a
 * rate. Net before ITBIS is invoice bases minus receipt bases, where the base
 * is `amount` minus a stated ITBIS (a missing ITBIS counts as zero). ITBIS
 * owed is invoice ITBIS minus receipt ITBIS, with the same zero rule.
 *
 * An RNC counts only when it has a nonzero digit, the same rule as
 * `tests/business/test_rnc_contract.py`. A paper NCF is `B` plus 10 digits.
 * An e-CF is `E` plus 12 digits and satisfies the comprobante requirement on
 * its own.
 *
 * `canCloseMonth` and `monthCloseBlockers` are the pure fiscal gate. A month
 * closes when the window is one calendar month, it is not already closed, and
 * every document has an RNC and either an NCF or an e-CF. A pending document
 * does not block the close. The Exportar "Listo para 606/607" checklist
 * imports this same pair; do not fork a second check.
 *
 * While any document in the window is still pending, `monthCloseNetDisplay`
 * returns `pending` and no money string. The net result is a number only
 * once nothing is pending. Income, expenses, and ITBIS stay numeric.
 *
 * `due_on` is optional. A pending document whose due day is before today is
 * overdue for display. Overdue does not change the stored status and does
 * not block the close.
 */

export type MonthCloseKind = "invoice" | "receipt";
export type MonthCloseStatus = "pendiente" | "cobrado" | "pagado";
export type MonthCloseCurrency = "DOP";

export type MonthCloseDocument = {
  id: string;
  kind: MonthCloseKind;
  counterparty: string;
  /** Calendar day, `YYYY-MM-DD`. */
  occurred_on: string;
  /** Day the document is due, `YYYY-MM-DD`. Null when the document has none. */
  due_on: string | null;
  /** Document total, DOP decimal text. */
  amount: string;
  /** Stated ITBIS. Null when the document does not print one. */
  itbis: string | null;
  /** Counterparty RNC as printed. Null when absent. */
  rnc: string | null;
  /** Paper NCF as printed. Null when absent. Distinct from `ecf`. */
  ncf: string | null;
  /** e-CF / e-NCF as printed. Null when absent. Distinct from `ncf`. */
  ecf: string | null;
  status: MonthCloseStatus;
  /**
   * False when this row does not carry RNC or fiscal-number text.
   * Absent means those fields are the record.
   */
  fiscal_known?: boolean;
};

export type MonthCloseWindow = {
  from: string;
  /** Null means through the server's today. */
  to: string | null;
};

export type MonthCloseSnapshot = {
  /** `YYYY-MM` when the window is one calendar month, otherwise null. */
  month: string | null;
  from: string;
  to: string;
  currency: MonthCloseCurrency;
  closed_at: string | null;
  /** First month with data, when the response includes it. Null when it does not. */
  earliest_month: string | null;
  documents: MonthCloseDocument[];
  /** Server-derived close. The mock still records `closed_at` when the sample month is locked. */
  closed?: boolean;
  /** Present means these blockers, including none. Absent means derive them from the documents. */
  blockers?: MonthCloseBlocker[];
  /** A null figure is unknown. Absent means the cards compute the figure from the documents. */
  figures?: MonthCloseFigures;
};

export type MonthCloseFigures = {
  income_before_itbis: string | null;
  expense_before_itbis: string | null;
  net_before_itbis: string | null;
  itbis_owed: string | null;
};

export type MonthCloseSummary = {
  currency: MonthCloseCurrency;
  /** Invoice bases. ITBIS is not part of this figure. */
  income_before_itbis: string;
  /** Receipt bases. ITBIS is not part of this figure. */
  expense_before_itbis: string;
  /** Invoice bases minus receipt bases. ITBIS is not part of this figure. */
  net_before_itbis: string;
  /** Invoice ITBIS minus receipt ITBIS. */
  itbis_owed: string;
};

/**
 * Close blockers. Fiscal gaps lock the month. The two statement kinds are
 * part of the same union so a later count can be added without a new gate.
 * This screen does not render them.
 */
export type MonthCloseBlocker =
  | { kind: "missing_rnc"; id: string; documentId: string }
  | { kind: "missing_ncf"; id: string; documentId: string }
  | { kind: "statement_missing" }
  | { kind: "unmatched_charges"; count: number };

export const statementMissingBlocker: MonthCloseBlocker = { kind: "statement_missing" };

/** A count of charges with no receipt. Zero is not a state. */
export function unmatchedCharges(count: number): MonthCloseBlocker {
  if (!Number.isInteger(count) || count < 1) throw new MonthCloseError("unavailable", "unmatched charges need a count");
  return { kind: "unmatched_charges", count };
}

export function isFiscalBlocker(
  blocker: MonthCloseBlocker,
): blocker is Extract<MonthCloseBlocker, { kind: "missing_rnc" | "missing_ncf" }> {
  return blocker.kind === "missing_rnc" || blocker.kind === "missing_ncf";
}

export type MonthCloseGate =
  | { ok: true; month: string }
  | { ok: false; reason: "not_calendar_month" | "closed" | "blockers" };

/** A pending or unknown month has no money string. A final month has the net and nothing else that could be read as a second total. */
export type MonthCloseNetDisplay =
  | { state: "pending"; pending_count: number; reason: "documents" | "unmatched" | "unknown" }
  | { state: "final"; net_before_itbis: string };

export type MonthCloseErrorCode = "not_found" | "closed" | "invalid_status" | "blockers" | "unavailable";

export class MonthCloseError extends Error {
  readonly code: MonthCloseErrorCode;

  constructor(code: MonthCloseErrorCode, message: string) {
    super(message);
    this.name = "MonthCloseError";
    this.code = code;
  }
}

export type MonthCloseClient = {
  readonly mode: "mock" | "http";
  /** `scope` is the selected Business grant. The mock keeps each grant's marks apart. The HTTP client refetches when the view's scope changes; the session already carries the grant. `month` is `YYYY-MM` and is the `month` query sent to the server. */
  load(month: string, scope?: string): Promise<MonthCloseSnapshot>;
  markCobrado(documentId: string, scope?: string, settledOn?: string): Promise<MonthCloseDocument>;
  markPagado(documentId: string, scope?: string, settledOn?: string): Promise<MonthCloseDocument>;
  /** The sample client locks the month locally. The HTTP client has no close request. */
  closeMonth(month: string, scope?: string): Promise<MonthCloseSnapshot>;
};

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const MONTH = /^\d{4}-\d{2}$/;
const PAPER_NCF = /^B\d{10}$/;
const ELECTRONIC_NCF = /^E\d{12}$/;
const AMOUNT = /^-?\d+(\.\d{1,2})?$/;
const ZERO = BigInt(0);
const HUNDRED = BigInt(100);

export function parseDopCents(amount: string): bigint {
  const trimmed = amount.trim();
  if (!AMOUNT.test(trimmed)) throw new MonthCloseError("unavailable", "DOP amounts use at most two decimal places");
  const negative = trimmed.startsWith("-");
  const [whole, fraction = ""] = trimmed.slice(negative ? 1 : 0).split(".");
  const cents = BigInt(whole) * HUNDRED + BigInt(fraction.padEnd(2, "0"));
  return negative ? -cents : cents;
}

export function formatDopCents(cents: bigint): string {
  const negative = cents < ZERO;
  const absolute = negative ? -cents : cents;
  const fraction = (absolute % HUNDRED).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${absolute / HUNDRED}.${fraction}`;
}

function addCents(left: bigint, right: string | null): bigint {
  return left + parseDopCents(right ?? "0");
}

/** An RNC with no nonzero digit is no RNC. */
export function rncPresent(value: string | null | undefined): boolean {
  return Boolean(value && /[1-9]/.test(value));
}

export function paperNcf(value: string | null | undefined): string | null {
  return value && PAPER_NCF.test(value) ? value : null;
}

export function electronicNcf(value: string | null | undefined): string | null {
  return value && ELECTRONIC_NCF.test(value) ? value : null;
}

/** A paper NCF or an e-CF. Either one is the comprobante. */
export function fiscalNumberPresent(document: Pick<MonthCloseDocument, "ncf" | "ecf">): boolean {
  return Boolean(paperNcf(document.ncf) || electronicNcf(document.ecf));
}

export function documentBaseCents(document: Pick<MonthCloseDocument, "amount" | "itbis">): bigint {
  return parseDopCents(document.amount) - parseDopCents(document.itbis ?? "0");
}

export function monthCloseSummary(documents: readonly MonthCloseDocument[]): MonthCloseSummary {
  let invoiceBase = ZERO;
  let receiptBase = ZERO;
  let invoiceItbis = ZERO;
  let receiptItbis = ZERO;
  for (const document of documents) {
    const base = documentBaseCents(document);
    const itbis = parseDopCents(document.itbis ?? "0");
    if (document.kind === "invoice") {
      invoiceBase += base;
      invoiceItbis += itbis;
    } else {
      receiptBase += base;
      receiptItbis += itbis;
    }
  }
  return {
    currency: "DOP",
    income_before_itbis: formatDopCents(invoiceBase),
    expense_before_itbis: formatDopCents(receiptBase),
    net_before_itbis: formatDopCents(invoiceBase - receiptBase),
    itbis_owed: formatDopCents(invoiceItbis - receiptItbis),
  };
}

/** Net result for the card. Pending documents, unmatched charges, or an unknown figure withhold the number. */
export function monthCloseNetDisplay(
  documents: readonly MonthCloseDocument[],
  blockers: readonly MonthCloseBlocker[] = [],
  net: string | null = monthCloseSummary(documents).net_before_itbis,
): MonthCloseNetDisplay {
  const pendingCount = documents.reduce((count, document) => count + (document.status === "pendiente" ? 1 : 0), 0);
  if (pendingCount > 0) return { state: "pending", pending_count: pendingCount, reason: "documents" };
  if (blockers.some((blocker) => blocker.kind === "unmatched_charges")) return { state: "pending", pending_count: 0, reason: "unmatched" };
  if (net === null) return { state: "pending", pending_count: 0, reason: "unknown" };
  return { state: "final", net_before_itbis: net };
}

export function documentsTotal(documents: readonly Pick<MonthCloseDocument, "amount">[]): string {
  return formatDopCents(documents.reduce((total, document) => addCents(total, document.amount), ZERO));
}

function utcDayNumber(day: string): number {
  const [year, month, date] = day.split("-").map(Number);
  return Math.floor(Date.UTC(year, month - 1, date) / 86400000);
}

/** Whole days from `today` to `dueOn`. Both are `YYYY-MM-DD`. */
export function dueDistance(dueOn: string, today: string): { direction: "past" | "today" | "future"; days: number } | null {
  if (!DAY.test(dueOn) || !DAY.test(today)) return null;
  const delta = utcDayNumber(dueOn) - utcDayNumber(today);
  if (delta === 0) return { direction: "today", days: 0 };
  if (delta < 0) return { direction: "past", days: -delta };
  return { direction: "future", days: delta };
}

/** Pending, and the due day is already behind `today`. A settled document is never overdue. */
export function documentOverdue(document: Pick<MonthCloseDocument, "status" | "due_on">, today: string): boolean {
  return document.status === "pendiente" && typeof document.due_on === "string" && dueDistance(document.due_on, today)?.direction === "past";
}

export function calendarDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function statusTotals(documents: readonly MonthCloseDocument[]): Record<MonthCloseStatus, { count: number; amount: string }> {
  const totals: Record<MonthCloseStatus, bigint> = { pendiente: ZERO, cobrado: ZERO, pagado: ZERO };
  const counts: Record<MonthCloseStatus, number> = { pendiente: 0, cobrado: 0, pagado: 0 };
  for (const document of documents) {
    counts[document.status] += 1;
    totals[document.status] = addCents(totals[document.status], document.amount);
  }
  return {
    pendiente: { count: counts.pendiente, amount: formatDopCents(totals.pendiente) },
    cobrado: { count: counts.cobrado, amount: formatDopCents(totals.cobrado) },
    pagado: { count: counts.pagado, amount: formatDopCents(totals.pagado) },
  };
}

/** Documents that cannot go into 606/607 yet: missing RNC, or missing both NCF and e-CF. */
export function monthCloseBlockers(documents: readonly MonthCloseDocument[]): MonthCloseBlocker[] {
  const blockers: MonthCloseBlocker[] = [];
  for (const document of sortDocuments(documents, "oldest")) {
    if (!rncPresent(document.rnc)) blockers.push({ id: `${document.id}:missing_rnc`, documentId: document.id, kind: "missing_rnc" });
    if (!fiscalNumberPresent(document)) blockers.push({ id: `${document.id}:missing_ncf`, documentId: document.id, kind: "missing_ncf" });
  }
  return blockers;
}

function lastDayOfMonth(year: number, month: number): string {
  const date = new Date(year, month, 0);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** The window is one calendar month, or null. An open end is that month only while today still falls inside it. */
export function calendarMonthOf(from: string, to: string | null, today: string): string | null {
  if (!DAY.test(from) || !from.endsWith("-01") || !DAY.test(today)) return null;
  const year = Number(from.slice(0, 4));
  const month = Number(from.slice(5, 7));
  if (month < 1 || month > 12) return null;
  const end = lastDayOfMonth(year, month);
  const key = from.slice(0, 7);
  if (to === null) return today >= from && today <= end ? key : null;
  return DAY.test(to) && to === end ? key : null;
}

/** `YYYY-MM` for a local calendar month. */
export function currentMonthKey(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Move a `YYYY-MM` key by whole months. January minus one is the previous December. */
export function shiftMonthKey(month: string, offset: number): string {
  if (!MONTH.test(month)) throw new MonthCloseError("unavailable", "month close month is unknown");
  return currentMonthKey(new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1 + offset, 1));
}

/** "Octubre 2026". The month name and the year stay separate so the label is not "octubre de 2026". */
export function formatMonthLabel(month: string, locale = "es-419"): string {
  if (!MONTH.test(month)) throw new MonthCloseError("unavailable", "month close month is unknown");
  const formatted = new Intl.DateTimeFormat(locale, { month: "long" }).format(
    new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1),
  );
  return `${formatted.charAt(0).toLocaleUpperCase(locale)}${formatted.slice(1)} ${month.slice(0, 4)}`;
}

/** How far back the month list goes when the API does not say where the data starts. */
export const MONTH_PICKER_LOOKBACK = 24;
/** Months after the current one stay in the list so they can be seen and not chosen. */
export const MONTH_PICKER_FUTURE = 12;

/** The first selectable month: the API's earliest month with data, or the last 24 months. */
export function monthPickerFloor(current: string, earliest: string | null): string {
  if (earliest && MONTH.test(earliest) && earliest <= current) return earliest;
  return shiftMonthKey(current, -(MONTH_PICKER_LOOKBACK - 1));
}

export type MonthChoice = { month: string; selectable: boolean };

/** Months only. Past months through the current one can be chosen. Later months are present and disabled. */
export function monthPickerMonths(current: string, earliest: string | null = null): MonthChoice[] {
  const floor = monthPickerFloor(current, earliest);
  const end = shiftMonthKey(current, MONTH_PICKER_FUTURE);
  const months: MonthChoice[] = [];
  for (let cursor = floor; cursor <= end; cursor = shiftMonthKey(cursor, 1)) {
    months.push({ month: cursor, selectable: cursor <= current });
  }
  return months;
}

/** Whether the previous or next arrow may leave `month`. Forward stops on the current month. */
export function canStepMonth(month: string, direction: -1 | 1, current: string, earliest: string | null = null): boolean {
  const next = shiftMonthKey(month, direction);
  return next <= current && next >= monthPickerFloor(current, earliest);
}

/** `GET /business/month-close?month=YYYY-MM`. */
export function monthCloseRequestPath(month: string): string {
  if (!MONTH.test(month)) throw new MonthCloseError("unavailable", "month close month is unknown");
  return `/business/month-close?${new URLSearchParams({ month }).toString()}`;
}

/**
 * Pure close gate. The month-close button and the Exportar 606/607 checklist
 * both call this. Pending collection or payment is not an input.
 */
export function canCloseMonth(snapshot: Pick<MonthCloseSnapshot, "month" | "closed_at" | "documents" | "blockers" | "closed">): MonthCloseGate {
  if (!snapshot.month) return { ok: false, reason: "not_calendar_month" };
  if (snapshot.closed_at || snapshot.closed) return { ok: false, reason: "closed" };
  const blockers = snapshot.blockers ?? monthCloseBlockers(snapshot.documents);
  if (blockers.some(isFiscalBlocker)) return { ok: false, reason: "blockers" };
  return { ok: true, month: snapshot.month };
}

/** Same function as `canCloseMonth`. */
export const closeGate = canCloseMonth;

export function sortDocuments(documents: readonly MonthCloseDocument[], order: "newest" | "oldest"): MonthCloseDocument[] {
  return [...documents].sort((left, right) => {
    const byDate = order === "newest" ? right.occurred_on.localeCompare(left.occurred_on) : left.occurred_on.localeCompare(right.occurred_on);
    return byDate || left.counterparty.localeCompare(right.counterparty, "es");
  });
}

export function filterDocuments(documents: readonly MonthCloseDocument[], status: MonthCloseStatus | "all"): MonthCloseDocument[] {
  return status === "all" ? [...documents] : documents.filter((document) => document.status === status);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function readAmount(value: unknown): string {
  if (typeof value !== "string" || !AMOUNT.test(value.trim())) throw new MonthCloseError("unavailable", "month close amount was not DOP text");
  return formatDopCents(parseDopCents(value));
}

function readNullableText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new MonthCloseError("unavailable", "month close text was not a string");
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function statusFits(kind: MonthCloseKind, status: string): status is MonthCloseStatus {
  return status === "pendiente" || (kind === "invoice" ? status === "cobrado" : status === "pagado");
}

export function readMonthCloseDocument(value: unknown): MonthCloseDocument {
  if (!isRecord(value)) throw new MonthCloseError("unavailable", "month close document was not an object");
  if (typeof value.id !== "string" || value.id.length === 0) throw new MonthCloseError("unavailable", "month close document has no id");
  if (value.kind !== "invoice" && value.kind !== "receipt") throw new MonthCloseError("unavailable", "month close document kind is unknown");
  if (typeof value.counterparty !== "string" || value.counterparty.trim().length === 0) throw new MonthCloseError("unavailable", "month close document has no counterparty");
  if (typeof value.occurred_on !== "string" || !DAY.test(value.occurred_on)) throw new MonthCloseError("unavailable", "month close document date is unknown");
  if (value.currency !== undefined && value.currency !== "DOP") throw new MonthCloseError("unavailable", "month close is DOP only");
  if (typeof value.status !== "string" || !statusFits(value.kind, value.status)) throw new MonthCloseError("unavailable", "month close status does not fit the document");
  return {
    id: value.id,
    kind: value.kind,
    counterparty: value.counterparty.trim(),
    occurred_on: value.occurred_on,
    amount: readAmount(value.amount),
    itbis: value.itbis === null || value.itbis === undefined ? null : readAmount(value.itbis),
    rnc: readNullableText(value.rnc),
    ncf: readNullableText(value.ncf),
    ecf: readNullableText(value.ecf),
    status: value.status,
    due_on: readDueOn(value.due_on),
  };
}

function readDueOn(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || !DAY.test(value)) throw new MonthCloseError("unavailable", "month close due day is unknown");
  return value;
}

export function readMonthCloseSnapshot(value: unknown): MonthCloseSnapshot {
  if (!isRecord(value)) throw new MonthCloseError("unavailable", "month close response was not an object");
  if (value.currency !== "DOP") throw new MonthCloseError("unavailable", "month close is DOP only");
  if (typeof value.from !== "string" || !DAY.test(value.from) || typeof value.to !== "string" || !DAY.test(value.to)) {
    throw new MonthCloseError("unavailable", "month close window is unknown");
  }
  if (!(value.month === null || (typeof value.month === "string" && MONTH.test(value.month)))) {
    throw new MonthCloseError("unavailable", "month close month is unknown");
  }
  if (!(value.closed_at === null || typeof value.closed_at === "string")) throw new MonthCloseError("unavailable", "month close timestamp is unknown");
  if (!Array.isArray(value.documents)) throw new MonthCloseError("unavailable", "month close documents are missing");
  const earliest = typeof value.earliest_month === "string" && MONTH.test(value.earliest_month) ? value.earliest_month : null;
  return {
    month: value.month,
    from: value.from,
    to: value.to,
    currency: "DOP",
    closed_at: value.closed_at,
    earliest_month: earliest,
    documents: value.documents.map(readMonthCloseDocument),
  };
}

function shiftMonth(date: Date, offset: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + offset, 1);
}

function dayInMonth(monthStart: Date, day: number): string {
  return `${monthStart.getFullYear()}-${String(monthStart.getMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

type SampleInput = Omit<MonthCloseDocument, "occurred_on" | "due_on"> & { day: number; dueDay: number | null };

function sample(monthStart: Date, input: SampleInput, now: Date): MonthCloseDocument {
  const { day, dueDay, ...document } = input;
  const currentMonth = monthStart.getFullYear() === now.getFullYear() && monthStart.getMonth() === now.getMonth();
  // The open month runs through today, so a fixture day after today moves onto today.
  const used = currentMonth ? Math.min(day, now.getDate()) : day;
  return {
    ...document,
    occurred_on: dayInMonth(monthStart, used),
    due_on: dueDay === null ? null : dayInMonth(monthStart, dueDay),
  };
}

/** Realistic Dominican fixtures for the open month and the month before it. */
export function monthCloseSampleDocuments(now = new Date()): MonthCloseDocument[] {
  const current = shiftMonth(now, 0);
  const previous = shiftMonth(now, -1);
  const row = (monthStart: Date, input: SampleInput) => sample(monthStart, input, now);
  return [
    row(current, { id: "inv-colmado", kind: "invoice", day: 3, dueDay: 10, counterparty: "Colmado Don Luis", amount: "29500.00", itbis: "4500.00", rnc: "101-23456-7", ncf: "B0100000042", ecf: null, status: "cobrado" }),
    row(current, { id: "inv-taller", kind: "invoice", day: 8, dueDay: 28, counterparty: "Taller Hermanos Peña", amount: "21240.00", itbis: "3240.00", rnc: "131-55544-3", ncf: null, ecf: "E310000000012", status: "pendiente" }),
    row(current, { id: "inv-farmacia", kind: "invoice", day: 1, dueDay: 2, counterparty: "Farmacia Central", amount: "6400.00", itbis: "0.00", rnc: null, ncf: "B0200000108", ecf: null, status: "pendiente" }),
    row(current, { id: "inv-caribe", kind: "invoice", day: 15, dueDay: 20, counterparty: "Suplidores del Caribe", amount: "10620.00", itbis: "1620.00", rnc: "101-00011-2", ncf: null, ecf: null, status: "cobrado" }),
    row(current, { id: "rcpt-ferreteria", kind: "receipt", day: 4, dueDay: 4, counterparty: "Ferretería La Esquina", amount: "4956.00", itbis: "756.00", rnc: "131-99988-8", ncf: "B0100000099", ecf: null, status: "pagado" }),
    row(current, { id: "rcpt-edenorte", kind: "receipt", day: 10, dueDay: 25, counterparty: "Edenorte", amount: "3658.00", itbis: "558.00", rnc: "101-01010-1", ncf: null, ecf: "E430000000077", status: "pendiente" }),
    row(current, { id: "rcpt-transporte", kind: "receipt", day: 14, dueDay: 5, counterparty: "Transporte Díaz", amount: "1500.00", itbis: null, rnc: null, ncf: null, ecf: null, status: "pendiente" }),
    row(current, { id: "rcpt-papeleria", kind: "receipt", day: 6, dueDay: 6, counterparty: "Papelería El Sol", amount: "944.00", itbis: "144.00", rnc: "131-24680-5", ncf: "B1400000033", ecf: null, status: "pagado" }),
    row(previous, { id: "inv-aurora", kind: "invoice", day: 5, dueDay: 12, counterparty: "Clínica Aurora", amount: "14160.00", itbis: "2160.00", rnc: "101-88877-6", ncf: "B0100000201", ecf: null, status: "cobrado" }),
    row(previous, { id: "inv-luna", kind: "invoice", day: 11, dueDay: 20, counterparty: "Panadería Luna", amount: "5900.00", itbis: "900.00", rnc: "131-22233-4", ncf: "B0100000202", ecf: null, status: "pendiente" }),
    row(previous, { id: "rcpt-isla", kind: "receipt", day: 7, dueDay: 7, counterparty: "Combustible Isla", amount: "2360.00", itbis: "360.00", rnc: "101-33322-1", ncf: "B1500000044", ecf: null, status: "pagado" }),
    row(previous, { id: "rcpt-rosa", kind: "receipt", day: 13, dueDay: 25, counterparty: "Limpieza Rosa", amount: "944.00", itbis: "144.00", rnc: "131-44455-6", ncf: "B0100000203", ecf: null, status: "pendiente" }),
  ];
}

function documentsInWindow(documents: readonly MonthCloseDocument[], from: string, to: string): MonthCloseDocument[] {
  return documents.filter((document) => document.occurred_on >= from && document.occurred_on <= to);
}

function earliestMonthOf(documents: readonly MonthCloseDocument[]): string | null {
  let earliest: string | null = null;
  for (const document of documents) {
    const key = document.occurred_on.slice(0, 7);
    if (!MONTH.test(key)) continue;
    if (!earliest || key < earliest) earliest = key;
  }
  return earliest;
}

function windowForMonth(month: string): MonthCloseWindow {
  if (!MONTH.test(month)) throw new MonthCloseError("unavailable", "month close month is unknown");
  const [year, monthNumber] = month.split("-").map(Number);
  return { from: `${month}-01`, to: lastDayOfMonth(year, monthNumber) };
}

function snapshotFor(documents: readonly MonthCloseDocument[], window: MonthCloseWindow, today: string, closedAt: Map<string, string>): MonthCloseSnapshot {
  const to = window.to ?? today;
  const month = calendarMonthOf(window.from, window.to, today);
  return {
    month,
    from: window.from,
    to,
    currency: "DOP",
    closed_at: month ? closedAt.get(month) ?? null : null,
    earliest_month: earliestMonthOf(documents),
    documents: documentsInWindow(documents, window.from, to),
  };
}

export type MockMonthCloseOptions = {
  now?: Date;
  /** Mark calls for these ids fail, so the view can roll the optimistic row back. */
  failIds?: readonly string[];
};

export function createMockMonthCloseClient(options: MockMonthCloseOptions = {}): MonthCloseClient {
  const now = options.now ?? new Date();
  const today = calendarDay(now);
  const failIds = new Set(options.failIds ?? []);
  const books = new Map<string, { documents: MonthCloseDocument[]; closedAt: Map<string, string> }>();

  function book(scope = "default") {
    const existing = books.get(scope);
    if (existing) return existing;
    const created = { documents: monthCloseSampleDocuments(now), closedAt: new Map<string, string>() };
    books.set(scope, created);
    return created;
  }

  function requireOpen(scope: string, document: MonthCloseDocument): void {
    const month = document.occurred_on.slice(0, 7);
    if (book(scope).closedAt.has(month)) throw new MonthCloseError("closed", "month is closed");
  }

  function mark(scope: string, documentId: string, kind: MonthCloseKind, status: MonthCloseStatus): MonthCloseDocument {
    const current = book(scope);
    const document = current.documents.find((item) => item.id === documentId);
    if (!document) throw new MonthCloseError("not_found", "document not found");
    if (failIds.has(documentId)) throw new MonthCloseError("unavailable", "mark failed");
    if (document.kind !== kind) throw new MonthCloseError("invalid_status", "status does not fit the document");
    requireOpen(scope, document);
    const next = { ...document, status };
    current.documents = current.documents.map((item) => (item.id === documentId ? next : item));
    return next;
  }

  return {
    mode: "mock",
    async load(month, scope = "default") {
      const current = book(scope);
      return snapshotFor(current.documents, windowForMonth(month), today, current.closedAt);
    },
    async markCobrado(documentId, scope = "default") {
      return mark(scope, documentId, "invoice", "cobrado");
    },
    async markPagado(documentId, scope = "default") {
      return mark(scope, documentId, "receipt", "pagado");
    },
    async closeMonth(month, scope = "default") {
      if (!MONTH.test(month)) throw new MonthCloseError("unavailable", "month close month is unknown");
      const current = book(scope);
      const [year, monthNumber] = month.split("-").map(Number);
      const from = `${month}-01`;
      const to = lastDayOfMonth(year, monthNumber);
      const included = documentsInWindow(current.documents, from, to);
      const gate = canCloseMonth({ month, closed_at: current.closedAt.get(month) ?? null, documents: included });
      if (!gate.ok && gate.reason === "blockers") throw new MonthCloseError("blockers", "month still has blockers");
      if (!current.closedAt.has(month)) current.closedAt.set(month, new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0, 0).toISOString());
      return snapshotFor(current.documents, { from, to }, today, current.closedAt);
    },
  };
}

/** The settlement body the month-close route accepts. One tap uses the residual method. */
export const MONTH_CLOSE_MARK_METHOD = "otro";

export type MonthCloseSettlementBody = {
  status: "cobrado" | "pagado" | "pendiente";
  settled_on?: string;
  payment_method?: string;
};

export type MonthCloseRequest = {
  method: "GET" | "PATCH";
  path: string;
  body?: MonthCloseSettlementBody;
};

/** `GET /business/month-close?month=YYYY-MM`. No other query. */
export function monthCloseLoadRequest(month: string): MonthCloseRequest {
  return { method: "GET", path: monthCloseRequestPath(month) };
}

/** `PATCH /business/month-close/documents/{activity_id}`. A settled status carries the day and the method. */
export function monthCloseSettlementRequest(activityId: string, status: "cobrado" | "pagado", settledOn: string): MonthCloseRequest {
  if (!DAY.test(settledOn)) throw new MonthCloseError("unavailable", "settlement date is unknown");
  if (activityId.length === 0) throw new MonthCloseError("unavailable", "month close document has no id");
  return {
    method: "PATCH",
    path: `/business/month-close/documents/${encodeURIComponent(activityId)}`,
    body: { status, settled_on: settledOn, payment_method: MONTH_CLOSE_MARK_METHOD },
  };
}

function minorToAmount(minor: number): string {
  if (!Number.isInteger(minor)) throw new MonthCloseError("unavailable", "month close amount was not a minor-unit integer");
  return formatDopCents(BigInt(minor));
}

type WireLine = {
  activity_id: string;
  document_kind: MonthCloseKind;
  occurred_on: string;
  total_minor: number;
  itbis_minor: number | null;
  status: string;
};

function readWireLine(value: unknown): WireLine {
  if (!isRecord(value)) throw new MonthCloseError("unavailable", "month close document was not an object");
  if (typeof value.activity_id !== "string" || value.activity_id.length === 0) throw new MonthCloseError("unavailable", "month close document has no id");
  if (value.document_kind !== "invoice" && value.document_kind !== "receipt") throw new MonthCloseError("unavailable", "month close document kind is unknown");
  if (typeof value.occurred_on !== "string" || !DAY.test(value.occurred_on)) throw new MonthCloseError("unavailable", "month close document date is unknown");
  if (typeof value.total_minor !== "number") throw new MonthCloseError("unavailable", "month close amount was not a minor-unit integer");
  if (!(value.itbis_minor === null || typeof value.itbis_minor === "number")) throw new MonthCloseError("unavailable", "month close amount was not a minor-unit integer");
  if (typeof value.status !== "string" || !statusFits(value.document_kind, value.status)) throw new MonthCloseError("unavailable", "month close status does not fit the document");
  return {
    activity_id: value.activity_id,
    document_kind: value.document_kind,
    occurred_on: value.occurred_on,
    total_minor: value.total_minor,
    itbis_minor: value.itbis_minor,
    status: value.status,
  };
}

function wireDocument(line: WireLine): MonthCloseDocument {
  return {
    id: line.activity_id,
    kind: line.document_kind,
    counterparty: line.document_kind === "invoice" ? "Factura" : "Gasto",
    occurred_on: line.occurred_on,
    due_on: null,
    amount: minorToAmount(line.total_minor),
    itbis: line.itbis_minor === null ? null : minorToAmount(line.itbis_minor),
    rnc: null,
    ncf: null,
    ecf: null,
    status: line.status as MonthCloseStatus,
    fiscal_known: false,
  };
}

function readFigures(value: unknown): MonthCloseFigures | undefined {
  if (!Array.isArray(value)) throw new MonthCloseError("unavailable", "month close currencies are missing");
  const dop = value.find((item) => isRecord(item) && item.currency === "DOP");
  if (!dop || !isRecord(dop)) return {
    income_before_itbis: null,
    expense_before_itbis: null,
    net_before_itbis: null,
    itbis_owed: null,
  };
  const text = (field: string) => (typeof dop[field] === "string" ? readAmount(dop[field]) : null);
  return {
    income_before_itbis: text("income_before_itbis"),
    expense_before_itbis: text("expense_before_itbis"),
    net_before_itbis: text("net_result"),
    itbis_owed: text("itbis_owed"),
  };
}

/** The month-close GET body: derived `closed`, currency figures, and the four document lists. */
export function readMonthCloseWire(value: unknown): MonthCloseSnapshot {
  if (!isRecord(value)) throw new MonthCloseError("unavailable", "month close response was not an object");
  if (typeof value.month !== "string" || !MONTH.test(value.month)) throw new MonthCloseError("unavailable", "month close month is unknown");
  if (typeof value.from !== "string" || !DAY.test(value.from) || typeof value.to !== "string" || !DAY.test(value.to)) {
    throw new MonthCloseError("unavailable", "month close window is unknown");
  }
  if (typeof value.closed !== "boolean") throw new MonthCloseError("unavailable", "month close timestamp is unknown");
  if (!Array.isArray(value.reasons)) throw new MonthCloseError("unavailable", "month close documents are missing");
  const lists = ["missing_rnc", "missing_ncf", "cuentas_por_cobrar", "cuentas_por_pagar"] as const;
  const lines: WireLine[] = [];
  const seen = new Set<string>();
  for (const key of lists) {
    if (!Array.isArray(value[key])) throw new MonthCloseError("unavailable", "month close documents are missing");
    for (const item of value[key]) {
      const line = readWireLine(item);
      if (seen.has(line.activity_id)) continue;
      seen.add(line.activity_id);
      lines.push(line);
    }
  }
  const blockers: MonthCloseBlocker[] = value.reasons.map((reason) => {
    if (!isRecord(reason) || (reason.code !== "missing_rnc" && reason.code !== "missing_ncf") || typeof reason.activity_id !== "string") {
      throw new MonthCloseError("unavailable", "month close document was not an object");
    }
    return { kind: reason.code, id: `${reason.activity_id}:${reason.code}`, documentId: reason.activity_id };
  });
  return {
    month: value.month,
    from: value.from,
    to: value.to,
    currency: "DOP",
    closed_at: null,
    closed: value.closed,
    earliest_month: null,
    documents: lines.map(wireDocument),
    blockers,
    figures: readFigures(value.currencies),
  };
}

export type MonthCloseTransport = (path: string, init?: RequestInit) => Promise<unknown>;

function monthCloseError(error: unknown): MonthCloseError {
  const code = (error as { code?: string }).code;
  const mapped: Record<string, MonthCloseErrorCode> = {
    business_record_not_found: "not_found",
    business_status_invalid: "invalid_status",
    business_settlement_incomplete: "invalid_status",
    business_payment_method_invalid: "invalid_status",
    not_found: "not_found",
    closed: "closed",
    invalid_status: "invalid_status",
    blockers: "blockers",
    unavailable: "unavailable",
  };
  return new MonthCloseError(mapped[code ?? ""] ?? "unavailable", error instanceof Error ? error.message : "month close request failed");
}

async function readTransport(transport: MonthCloseTransport, request: MonthCloseRequest): Promise<unknown> {
  try {
    return await transport(request.path, {
      method: request.method,
      ...(request.body ? { body: JSON.stringify(request.body) } : {}),
    });
  } catch (error) {
    throw monthCloseError(error);
  }
}

/** Backend client. Not selected until `monthCloseClient` points here. */
export function createHttpMonthCloseClient(transport: MonthCloseTransport = (path, init) => apiFetch(path, init)): MonthCloseClient {
  return {
    mode: "http",
    async load(month) {
      return readMonthCloseWire(await readTransport(transport, monthCloseLoadRequest(month)));
    },
    async markCobrado(documentId, _scope, settledOn) {
      if (!settledOn) throw new MonthCloseError("unavailable", "settlement date is unknown");
      const request = monthCloseSettlementRequest(documentId, "cobrado", settledOn);
      const saved = await readTransport(transport, request);
      if (!isRecord(saved) || saved.status !== "cobrado") throw new MonthCloseError("unavailable", "month close status does not fit the document");
      return wireDocument({ activity_id: documentId, document_kind: "invoice", occurred_on: settledOn, total_minor: 0, itbis_minor: null, status: "cobrado" });
    },
    async markPagado(documentId, _scope, settledOn) {
      if (!settledOn) throw new MonthCloseError("unavailable", "settlement date is unknown");
      const request = monthCloseSettlementRequest(documentId, "pagado", settledOn);
      const saved = await readTransport(transport, request);
      if (!isRecord(saved) || saved.status !== "pagado") throw new MonthCloseError("unavailable", "month close status does not fit the document");
      return wireDocument({ activity_id: documentId, document_kind: "receipt", occurred_on: settledOn, total_minor: 0, itbis_minor: null, status: "pagado" });
    },
    async closeMonth() {
      throw new MonthCloseError("unavailable", "the month closes from the recorded documents");
    },
  };
}

/** Live month close for `/biz`. The preview does not use this. */
export const monthCloseClient: MonthCloseClient = createHttpMonthCloseClient();
