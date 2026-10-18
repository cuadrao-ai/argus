import { apiFetch } from "./argus-api-transport";

/**
 * Cuadrar el mes. The web owns this view until the Business API ships the
 * same contract. `monthCloseClient` is the only binding the view imports;
 * point it at `createHttpMonthCloseClient()` when the backend is ready.
 *
 * Assumed HTTP contract, under `/api/v1`:
 *
 * - `GET /business/month-close?from=YYYY-MM-DD&to=YYYY-MM-DD`
 *   `to` may be omitted. The server then uses its own today.
 * - `POST /business/month-close/documents/{id}/cobrado`
 * - `POST /business/month-close/documents/{id}/pagado`
 * - `POST /business/month-close/{month}/close` with `{month}` as `YYYY-MM`
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
  documents: MonthCloseDocument[];
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

/** Pending collection or payment is not a close blocker. Only a missing RNC or comprobante is. */
export type MonthCloseBlockerKind = "missing_rnc" | "missing_ncf";

export type MonthCloseBlocker = {
  id: string;
  documentId: string;
  kind: MonthCloseBlockerKind;
};

export type MonthCloseGate =
  | { ok: true; month: string }
  | { ok: false; reason: "not_calendar_month" | "closed" | "blockers" };

/** A pending month has no money string. A final month has the net and nothing else that could be read as a second total. */
export type MonthCloseNetDisplay =
  | { state: "pending"; pending_count: number }
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
  load(window: MonthCloseWindow): Promise<MonthCloseSnapshot>;
  markCobrado(documentId: string): Promise<MonthCloseDocument>;
  markPagado(documentId: string): Promise<MonthCloseDocument>;
  closeMonth(month: string): Promise<MonthCloseSnapshot>;
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

/** Net result for the card. Pending wins over the computed number, which is withheld entirely. */
export function monthCloseNetDisplay(documents: readonly MonthCloseDocument[]): MonthCloseNetDisplay {
  const pendingCount = documents.reduce((count, document) => count + (document.status === "pendiente" ? 1 : 0), 0);
  if (pendingCount > 0) return { state: "pending", pending_count: pendingCount };
  return { state: "final", net_before_itbis: monthCloseSummary(documents).net_before_itbis };
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

/**
 * Pure close gate. The month-close button and the Exportar 606/607 checklist
 * both call this. Pending collection or payment is not an input.
 */
export function canCloseMonth(snapshot: Pick<MonthCloseSnapshot, "month" | "closed_at" | "documents">): MonthCloseGate {
  if (!snapshot.month) return { ok: false, reason: "not_calendar_month" };
  if (snapshot.closed_at) return { ok: false, reason: "closed" };
  if (monthCloseBlockers(snapshot.documents).length > 0) return { ok: false, reason: "blockers" };
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
  };
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
  return {
    month: value.month,
    from: value.from,
    to: value.to,
    currency: "DOP",
    closed_at: value.closed_at,
    documents: value.documents.map(readMonthCloseDocument),
  };
}

function localDay(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function shiftMonth(date: Date, offset: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + offset, 1);
}

function dayInMonth(monthStart: Date, day: number): string {
  return `${monthStart.getFullYear()}-${String(monthStart.getMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

type SampleInput = Omit<MonthCloseDocument, "occurred_on"> & { day: number };

function sample(monthStart: Date, input: SampleInput, now: Date): MonthCloseDocument {
  const { day, ...document } = input;
  const currentMonth = monthStart.getFullYear() === now.getFullYear() && monthStart.getMonth() === now.getMonth();
  // The open month runs through today, so a fixture day after today moves onto today.
  const used = currentMonth ? Math.min(day, now.getDate()) : day;
  return { ...document, occurred_on: dayInMonth(monthStart, used) };
}

/** Realistic Dominican fixtures for the open month and the month before it. */
export function monthCloseSampleDocuments(now = new Date()): MonthCloseDocument[] {
  const current = shiftMonth(now, 0);
  const previous = shiftMonth(now, -1);
  const row = (monthStart: Date, input: SampleInput) => sample(monthStart, input, now);
  return [
    row(current, { id: "inv-colmado", kind: "invoice", day: 3, counterparty: "Colmado Don Luis", amount: "29500.00", itbis: "4500.00", rnc: "101-23456-7", ncf: "B0100000042", ecf: null, status: "cobrado" }),
    row(current, { id: "inv-taller", kind: "invoice", day: 8, counterparty: "Taller Hermanos Peña", amount: "21240.00", itbis: "3240.00", rnc: "131-55544-3", ncf: null, ecf: "E310000000012", status: "pendiente" }),
    row(current, { id: "inv-farmacia", kind: "invoice", day: 12, counterparty: "Farmacia Central", amount: "6400.00", itbis: "0.00", rnc: null, ncf: "B0200000108", ecf: null, status: "pendiente" }),
    row(current, { id: "inv-caribe", kind: "invoice", day: 15, counterparty: "Suplidores del Caribe", amount: "10620.00", itbis: "1620.00", rnc: "101-00011-2", ncf: null, ecf: null, status: "cobrado" }),
    row(current, { id: "rcpt-ferreteria", kind: "receipt", day: 4, counterparty: "Ferretería La Esquina", amount: "4956.00", itbis: "756.00", rnc: "131-99988-8", ncf: "B0100000099", ecf: null, status: "pagado" }),
    row(current, { id: "rcpt-edenorte", kind: "receipt", day: 10, counterparty: "Edenorte", amount: "3658.00", itbis: "558.00", rnc: "101-01010-1", ncf: null, ecf: "E430000000077", status: "pendiente" }),
    row(current, { id: "rcpt-transporte", kind: "receipt", day: 14, counterparty: "Transporte Díaz", amount: "1500.00", itbis: null, rnc: null, ncf: null, ecf: null, status: "pendiente" }),
    row(current, { id: "rcpt-papeleria", kind: "receipt", day: 6, counterparty: "Papelería El Sol", amount: "944.00", itbis: "144.00", rnc: "131-24680-5", ncf: "B1400000033", ecf: null, status: "pagado" }),
    row(previous, { id: "inv-aurora", kind: "invoice", day: 5, counterparty: "Clínica Aurora", amount: "14160.00", itbis: "2160.00", rnc: "101-88877-6", ncf: "B0100000201", ecf: null, status: "cobrado" }),
    row(previous, { id: "inv-luna", kind: "invoice", day: 11, counterparty: "Panadería Luna", amount: "5900.00", itbis: "900.00", rnc: "131-22233-4", ncf: "B0100000202", ecf: null, status: "pendiente" }),
    row(previous, { id: "rcpt-isla", kind: "receipt", day: 7, counterparty: "Combustible Isla", amount: "2360.00", itbis: "360.00", rnc: "101-33322-1", ncf: "B1500000044", ecf: null, status: "pagado" }),
    row(previous, { id: "rcpt-rosa", kind: "receipt", day: 13, counterparty: "Limpieza Rosa", amount: "944.00", itbis: "144.00", rnc: "131-44455-6", ncf: "B0100000203", ecf: null, status: "pendiente" }),
  ];
}

function documentsInWindow(documents: readonly MonthCloseDocument[], from: string, to: string): MonthCloseDocument[] {
  return documents.filter((document) => document.occurred_on >= from && document.occurred_on <= to);
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
  const today = localDay(now);
  const failIds = new Set(options.failIds ?? []);
  let documents = monthCloseSampleDocuments(now);
  const closedAt = new Map<string, string>();

  function requireOpen(document: MonthCloseDocument): void {
    const month = document.occurred_on.slice(0, 7);
    if (closedAt.has(month)) throw new MonthCloseError("closed", "month is closed");
  }

  function mark(documentId: string, kind: MonthCloseKind, status: MonthCloseStatus): MonthCloseDocument {
    const document = documents.find((item) => item.id === documentId);
    if (!document) throw new MonthCloseError("not_found", "document not found");
    if (failIds.has(documentId)) throw new MonthCloseError("unavailable", "mark failed");
    if (document.kind !== kind) throw new MonthCloseError("invalid_status", "status does not fit the document");
    requireOpen(document);
    const next = { ...document, status };
    documents = documents.map((item) => (item.id === documentId ? next : item));
    return next;
  }

  return {
    mode: "mock",
    async load(window) {
      if (!DAY.test(window.from) || (window.to !== null && !DAY.test(window.to))) throw new MonthCloseError("unavailable", "month close window is unknown");
      return snapshotFor(documents, window, today, closedAt);
    },
    async markCobrado(documentId) {
      return mark(documentId, "invoice", "cobrado");
    },
    async markPagado(documentId) {
      return mark(documentId, "receipt", "pagado");
    },
    async closeMonth(month) {
      if (!MONTH.test(month)) throw new MonthCloseError("unavailable", "month close month is unknown");
      const [year, monthNumber] = month.split("-").map(Number);
      const from = `${month}-01`;
      const to = lastDayOfMonth(year, monthNumber);
      const included = documentsInWindow(documents, from, to);
      const gate = canCloseMonth({ month, closed_at: closedAt.get(month) ?? null, documents: included });
      if (!gate.ok && gate.reason === "blockers") throw new MonthCloseError("blockers", "month still has blockers");
      if (!closedAt.has(month)) closedAt.set(month, new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0, 0).toISOString());
      return snapshotFor(documents, { from, to }, today, closedAt);
    },
  };
}

async function readHttp<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await apiFetch<T>(path, init);
  } catch (error) {
    const code = (error as { code?: string }).code;
    const known: MonthCloseErrorCode[] = ["not_found", "closed", "invalid_status", "blockers", "unavailable"];
    throw new MonthCloseError(known.find((item) => item === code) ?? "unavailable", error instanceof Error ? error.message : "month close request failed");
  }
}

/** Backend client. Not selected until `monthCloseClient` points here. */
export function createHttpMonthCloseClient(): MonthCloseClient {
  return {
    mode: "http",
    async load(window) {
      const params = new URLSearchParams({ from: window.from });
      if (window.to) params.set("to", window.to);
      return readMonthCloseSnapshot(await readHttp(`/business/month-close?${params}`));
    },
    async markCobrado(documentId) {
      return readMonthCloseDocument(await readHttp(`/business/month-close/documents/${encodeURIComponent(documentId)}/cobrado`, { method: "POST" }));
    },
    async markPagado(documentId) {
      return readMonthCloseDocument(await readHttp(`/business/month-close/documents/${encodeURIComponent(documentId)}/pagado`, { method: "POST" }));
    },
    async closeMonth(month) {
      return readMonthCloseSnapshot(await readHttp(`/business/month-close/${encodeURIComponent(month)}/close`, { method: "POST" }));
    },
  };
}

/**
 * Swap `createMockMonthCloseClient()` for `createHttpMonthCloseClient()`
 * when the Business API serves the contract above. The view imports only this.
 */
export const monthCloseClient: MonthCloseClient = createMockMonthCloseClient();
