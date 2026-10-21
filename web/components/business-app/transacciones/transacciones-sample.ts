import { minorToDecimal } from "@/lib/money-entry";
import type { NoComprobanteReason } from "./transacciones-model";

/**
 * A sample bank server for the local design preview and tests. It answers
 * the bank routes in the contract's own shapes (`docs/contracts/business-bank-matching.md`),
 * so the screen reads it through the real adapter. It keeps decisions, takes
 * them back, pages, and computes the period's totals per currency in minor
 * units, the way the server does. Every name, RNC and NCF is invented.
 */

type Kind = "receipt" | "venta";

type SampleDocument = Readonly<{ id: string; kind: Kind; counterparty: string; daysAgo: number; currency: string; totalMinor: number; itbisMinor: number | null; rnc: string | null; ncf: string | null; categoryId: string | null; settledOnBank?: boolean }>;

type SampleLine = Readonly<{ id: string; daysAgo: number; description: string; counterparty: string; amountMinor: number; currency: string; account: "corriente" | "tarjeta"; categoryId: string | null }>;

type Offer = Readonly<{ id: string; lineId: string; documentId: string; confidence: string; reasons: readonly { code: string; days: number | null }[] }>;

const ACCOUNTS = {
  corriente: { account_id: "acc-corriente", name: "Corriente", type: "checking" },
  tarjeta: { account_id: "acc-tarjeta", name: "Tarjeta", type: "credit_card" },
} as const;

const DOCUMENTS: readonly SampleDocument[] = [
  { id: "doc-ferreteria", kind: "receipt", counterparty: "Ferretería La Esquina SRL", daysAgo: 4, currency: "DOP", totalMinor: 345000, itbisMinor: 52627, rnc: "1-01-12345-6", ncf: "B0100004512", categoryId: "shopping" },
  { id: "doc-electrico", kind: "receipt", counterparty: "Empresa Distribuidora del Este", daysAgo: 11, currency: "DOP", totalMinor: 418000, itbisMinor: 63763, rnc: "1-01-82125-6", ncf: "B0100015530", categoryId: "housing" },
  { id: "doc-repuestos", kind: "venta", counterparty: "Repuestos Duarte", daysAgo: 10, currency: "DOP", totalMinor: 1250000, itbisMinor: 190678, rnc: "1-30-44210-9", ncf: "B0100000298", categoryId: null },
  { id: "doc-estacion", kind: "receipt", counterparty: "Estación Ruta 3", daysAgo: 4, currency: "DOP", totalMinor: 210000, itbisMinor: 32034, rnc: null, ncf: "B0100000877", categoryId: "transport" },
  { id: "doc-nube", kind: "receipt", counterparty: "Nube Hosting", daysAgo: 6, currency: "USD", totalMinor: 2400, itbisMinor: null, rnc: null, ncf: null, categoryId: "other" },
  { id: "doc-ozama", kind: "receipt", counterparty: "Inmobiliaria Ozama SRL", daysAgo: 10, currency: "DOP", totalMinor: 3500000, itbisMinor: null, rnc: null, ncf: "B0100000310", categoryId: "housing" },
  { id: "doc-pena", kind: "venta", counterparty: "Distribuidora Hermanos Peña", daysAgo: 15, currency: "DOP", totalMinor: 3514000, itbisMinor: null, rnc: null, ncf: "B0100000295", categoryId: null },
  { id: "doc-papeleria", kind: "receipt", counterparty: "Papelería El Estudiante", daysAgo: 14, currency: "DOP", totalMinor: 98000, itbisMinor: null, rnc: null, ncf: "B0200004410", categoryId: "shopping" },
  { id: "doc-taller", kind: "receipt", counterparty: "Taller Mecánico Reyes", daysAgo: 11, currency: "DOP", totalMinor: 450000, itbisMinor: null, rnc: null, ncf: "B0100000144", categoryId: "transport", settledOnBank: true },
];

const LINES: readonly SampleLine[] = [
  { id: "mv-ferreteria", daysAgo: 3, description: "COMPRA POS FERRET LA ESQUINA", counterparty: "COMPRA POS FERRET LA ESQUINA", amountMinor: -345000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-dgii", daysAgo: 3, description: "IMP DGII 0.15% TRANSF", counterparty: "IMP DGII 0.15% TRANSF", amountMinor: -518, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-estacion", daysAgo: 4, description: "COMPRA EST RUTA 3", counterparty: "COMPRA EST RUTA 3", amountMinor: -210000, currency: "DOP", account: "tarjeta", categoryId: null },
  { id: "mv-colmado", daysAgo: 4, description: "COMPRA POS COLMADO DON PEPE", counterparty: "COMPRA POS COLMADO DON PEPE", amountMinor: -86000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-caribe", daysAgo: 5, description: "TRANSF RECIBIDA INV CARIBE", counterparty: "TRANSF RECIBIDA INV CARIBE", amountMinor: 4294068, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-verificacion", daysAgo: 5, description: "VERIF TARJETA", counterparty: "VERIF TARJETA", amountMinor: 0, currency: "DOP", account: "tarjeta", categoryId: null },
  { id: "mv-nube", daysAgo: 6, description: "NUBE HOSTING INTL", counterparty: "NUBE HOSTING INTL", amountMinor: -2400, currency: "USD", account: "tarjeta", categoryId: null },
  { id: "mv-caja", daysAgo: 6, description: "TRANSF A CAJA CHICA", counterparty: "TRANSF A CAJA CHICA", amountMinor: -500000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-electrico", daysAgo: 7, description: "PAGO SERV ELECTRICO 4471", counterparty: "PAGO SERV ELECTRICO 4471", amountMinor: -418000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-supermercado", daysAgo: 8, description: "COMPRA SUPER LA ECONOMICA", counterparty: "COMPRA SUPER LA ECONOMICA", amountMinor: -329075, currency: "DOP", account: "tarjeta", categoryId: null },
  { id: "mv-repuestos", daysAgo: 9, description: "DEP TRANSF REPUESTOS DUARTE", counterparty: "DEP TRANSF REPUESTOS DUARTE", amountMinor: 1250000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-ozama", daysAgo: 10, description: "TRANSF INMOB OZAMA", counterparty: "TRANSF INMOB OZAMA", amountMinor: -3500000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-farmacia", daysAgo: 12, description: "COMPRA FARM LOS RIOS", counterparty: "COMPRA FARM LOS RIOS", amountMinor: -114550, currency: "DOP", account: "tarjeta", categoryId: null },
  { id: "mv-pena", daysAgo: 13, description: "DEP TRANSF DIST HNOS PENA", counterparty: "DEP TRANSF DIST HNOS PENA", amountMinor: 3514000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-papeleria", daysAgo: 14, description: "COMPRA PAPELERIA EL ESTUD", counterparty: "COMPRA PAPELERIA EL ESTUD", amountMinor: -98000, currency: "DOP", account: "tarjeta", categoryId: null },
  { id: "mv-comision", daysAgo: 15, description: "COMISION MANEJO CTA", counterparty: "COMISION MANEJO CTA", amountMinor: -35000, currency: "DOP", account: "corriente", categoryId: null },
  { id: "mv-retiro", daysAgo: 18, description: "RETIRO ATM", counterparty: "RETIRO ATM", amountMinor: -300000, currency: "DOP", account: "corriente", categoryId: null },
];

const OFFERS: readonly Offer[] = [
  { id: "sg-ferreteria", lineId: "mv-ferreteria", documentId: "doc-ferreteria", confidence: "0.930", reasons: [{ code: "monto_exacto", days: null }, { code: "fecha_cercana", days: -1 }, { code: "nombre_parecido", days: null }] },
  { id: "sg-repuestos", lineId: "mv-repuestos", documentId: "doc-repuestos", confidence: "0.860", reasons: [{ code: "monto_exacto", days: null }, { code: "fecha_cercana", days: -1 }, { code: "nombre_parecido", days: null }] },
  { id: "sg-electrico", lineId: "mv-electrico", documentId: "doc-electrico", confidence: "0.740", reasons: [{ code: "monto_exacto", days: null }, { code: "fecha_cercana", days: -4 }] },
];

const MATCHED: readonly [string, string][] = [["mv-estacion", "doc-estacion"], ["mv-nube", "doc-nube"], ["mv-ozama", "doc-ozama"], ["mv-pena", "doc-pena"], ["mv-papeleria", "doc-papeleria"]];
const MARKED: readonly [string, NoComprobanteReason][] = [["mv-dgii", "cargo_banco"], ["mv-caja", "entre_cuentas"], ["mv-comision", "cargo_banco"], ["mv-retiro", "personal"]];

export type SampleBankOptions = Readonly<{ noStatement?: boolean; failLoad?: boolean; failDecideOnce?: boolean; pageSize?: number }>;

type Fetch = <T>(path: string, init?: RequestInit) => Promise<T>;

const refuse = (status: number, code: string) => Object.assign(new Error(code), { status, code });

function shift(day: string, daysAgo: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

type Row = { kind: "movement" | "document"; id: string; occurredOn: string; amountMinor: number; currency: string; state: string; confidence: number; item: Record<string, unknown> };

/** A fresh sample bank per preview or test. Dates count back from the period's last day, so any month the preview opens has its rows. */
export function createSampleBankServer(options: SampleBankOptions = {}): Fetch {
  const matches = new Map<string, { documentId: string; at: string }>(MATCHED.map(([lineId, documentId]) => [lineId, { documentId, at: "2026-10-01T12:00:00Z" }]));
  const marks = new Map<string, { reason: NoComprobanteReason; at: string }>(MARKED.map(([lineId, reason]) => [lineId, { reason, at: "2026-10-01T12:00:00Z" }]));
  const declined = new Set<string>();
  const ended: { id: string; kind: "match" | "no_receipt"; lineId: string; documentId: string | null; reason: NoComprobanteReason | null; created_at: string; ended_at: string }[] = [];
  const answered = new Map<string, unknown>();
  let failDecide = options.failDecideOnce ?? false;
  let clock = 0;
  const now = () => new Date(Date.UTC(2026, 9, 21, 12, 0, clock++)).toISOString();

  const documentById = new Map(DOCUMENTS.map((document) => [document.id, document]));
  const lineById = new Map(LINES.map((line) => [line.id, line]));
  const heldBy = (documentId: string) => [...matches].find(([, match]) => match.documentId === documentId)?.[0] ?? null;

  const documentWire = (document: SampleDocument, anchor: string) => ({
    activity_id: document.id,
    kind: document.kind,
    counterparty: document.counterparty,
    occurred_on: shift(anchor, document.daysAgo),
    currency: document.currency,
    total_minor: document.totalMinor,
    total: minorToDecimal(document.totalMinor, document.currency),
    itbis_minor: document.itbisMinor,
    itbis: document.itbisMinor === null ? null : minorToDecimal(document.itbisMinor, document.currency),
    rnc: document.rnc,
    ncf: document.ncf,
    ecf: null,
    status: heldBy(document.id) || document.settledOnBank ? (document.kind === "venta" ? "cobrado" : "pagado") : "pendiente",
    settled_on: null,
    payment_method: null,
    category_id: document.categoryId,
  });

  const pendingOffers = (lineId: string) => OFFERS.filter((offer) => offer.lineId === lineId && !declined.has(offer.id) && heldBy(offer.documentId) === null);

  function lineRow(line: SampleLine, anchor: string, from: string): Row {
    const match = matches.get(line.id);
    const mark = marks.get(line.id);
    const offers = match || mark ? [] : pendingOffers(line.id);
    const matched = match ? documentById.get(match.documentId)! : null;
    const state = match ? "igualada" : mark || line.amountMinor === 0 ? "no_lleva_comprobante" : offers.length ? "sugerencia" : "falta_comprobante";
    const day = shift(anchor, line.daysAgo);
    const occurredOn = day < from ? from : day;
    const sense = line.amountMinor < 0 ? "charge" : line.amountMinor > 0 ? "deposit" : "zero";
    return {
      kind: "movement",
      id: line.id,
      occurredOn,
      amountMinor: line.amountMinor,
      currency: line.currency,
      state,
      confidence: offers.length ? Math.max(...offers.map((offer) => Number(offer.confidence))) : 0,
      item: {
        kind: "movement",
        id: line.id,
        occurred_on: occurredOn,
        description: line.description,
        counterparty: matched ? matched.counterparty : line.counterparty,
        sense,
        currency: line.currency,
        amount_minor: line.amountMinor,
        amount: minorToDecimal(line.amountMinor, line.currency),
        state,
        reason: mark ? mark.reason : state === "no_lleva_comprobante" ? "monto_cero" : null,
        category_id: matched ? matched.categoryId : line.categoryId,
        account: ACCOUNTS[line.account],
        method: line.account === "tarjeta" ? "tarjeta" : "transferencia",
        document: matched ? documentWire(matched, anchor) : null,
        suggestions: [...offers].sort((left, right) => Number(right.confidence) - Number(left.confidence)).map((offer) => ({ id: offer.id, confidence: offer.confidence, reasons: offer.reasons, document: documentWire(documentById.get(offer.documentId)!, anchor) })),
      },
    };
  }

  function documentRow(document: SampleDocument, anchor: string): Row {
    const signed = document.kind === "receipt" ? -document.totalMinor : document.totalMinor;
    const occurredOn = shift(anchor, document.daysAgo);
    return {
      kind: "document",
      id: document.id,
      occurredOn,
      amountMinor: signed,
      currency: document.currency,
      state: "sin_movimiento",
      confidence: 0,
      item: { kind: "document", id: document.id, occurred_on: occurredOn, description: null, counterparty: document.counterparty, sense: signed < 0 ? "charge" : "deposit", currency: document.currency, amount_minor: signed, amount: minorToDecimal(signed, document.currency), state: "sin_movimiento", reason: null, category_id: document.categoryId, account: ACCOUNTS.corriente, method: "transferencia", document: documentWire(document, anchor), suggestions: [] },
    };
  }

  function rowsOf(from: string, to: string): Row[] {
    if (options.noStatement) return [];
    const lines = LINES.map((line) => lineRow(line, to, from));
    const documents = DOCUMENTS.filter((document) => document.settledOnBank && heldBy(document.id) === null).map((document) => documentRow(document, to));
    return [...lines, ...documents];
  }

  function totalsOf(rows: readonly Row[]) {
    const blocks = new Map<string, { entradas: number; salidas: number; porIgualar: number; counts: Record<string, number> }>();
    for (const row of rows) {
      const block = blocks.get(row.currency) ?? { entradas: 0, salidas: 0, porIgualar: 0, counts: { movimientos: 0, igualadas: 0, no_lleva_comprobante: 0, sugerencias: 0, falta_comprobante: 0, sin_movimiento: 0, por_igualar: 0 } };
      blocks.set(row.currency, block);
      if (row.kind === "movement") {
        block.counts.movimientos += 1;
        if (row.amountMinor > 0) block.entradas += row.amountMinor;
        else block.salidas -= row.amountMinor;
      }
      const key = row.state === "sugerencia" ? "sugerencias" : row.state === "igualada" ? "igualadas" : row.state;
      block.counts[key] += 1;
      if (row.state === "sugerencia" || row.state === "falta_comprobante" || row.state === "sin_movimiento") {
        block.porIgualar += Math.abs(row.amountMinor);
        block.counts.por_igualar += 1;
      }
    }
    return [...blocks].map(([currency, block]) => ({ currency, entradas_minor: block.entradas, entradas: minorToDecimal(block.entradas, currency), salidas_minor: block.salidas, salidas: minorToDecimal(block.salidas, currency), por_igualar_minor: block.porIgualar, por_igualar: minorToDecimal(block.porIgualar, currency), counts: block.counts }));
  }

  const newestFirst = (left: Row, right: Row) => right.occurredOn.localeCompare(left.occurredOn) || left.id.localeCompare(right.id);

  function segmentRows(rows: readonly Row[], segment: string): Row[] {
    if (segment === "igualadas") return rows.filter((row) => row.state === "igualada" || row.state === "no_lleva_comprobante").sort(newestFirst);
    if (segment === "todas") return rows.filter((row) => row.kind === "movement").sort(newestFirst);
    const suggested = rows.filter((row) => row.state === "sugerencia").sort((left, right) => right.confidence - left.confidence || newestFirst(left, right));
    return [...suggested, ...rows.filter((row) => row.state === "falta_comprobante").sort(newestFirst), ...rows.filter((row) => row.state === "sin_movimiento").sort(newestFirst)];
  }

  function movements(query: URLSearchParams) {
    if (options.failLoad) throw refuse(503, "business_bank_unavailable");
    const from = query.get("period_start")!;
    const to = query.get("period_end")!;
    const segment = query.get("segment") ?? "todas";
    const limit = Math.min(Number(query.get("limit") ?? 50), options.pageSize ?? Number.POSITIVE_INFINITY);
    const cursor = query.get("cursor");
    if (cursor !== null && !/^o:\d+$/.test(cursor)) throw refuse(422, "invalid_cursor");
    const offset = cursor ? Number(cursor.slice(2)) : 0;
    const rows = rowsOf(from, to);
    const listed = segmentRows(rows, segment);
    const page = listed.slice(offset, offset + limit);
    return {
      period_start: from,
      period_end: to,
      segment,
      sense: null,
      accounts: [{ ...ACCOUNTS.corriente, bank_account_id: "bank-corriente", currency: "DOP", covered_through: options.noStatement ? null : shift(to, 3) }],
      totals: totalsOf(rows),
      items: page.map((row) => row.item),
      next_cursor: offset + limit < listed.length ? `o:${offset + limit}` : null,
    };
  }

  const anchorDay = () => new Date().toISOString().slice(0, 10);
  const itemOf = (lineId: string) => lineRow(lineById.get(lineId)!, anchorDay(), "2000-01-01").item;
  const lineOrRefuse = (lineId: string) => lineById.get(lineId) ?? (() => { throw refuse(404, "line_not_found"); })();
  const outcomeRefusal = (lineId: string) => (matches.has(lineId) ? refuse(409, "line_already_confirmed") : marks.has(lineId) ? refuse(409, "line_marked_no_receipt") : null);

  function endMatch(lineId: string) {
    const match = matches.get(lineId)!;
    matches.delete(lineId);
    ended.push({ id: `h-${ended.length}`, kind: "match", lineId, documentId: match.documentId, reason: null, created_at: match.at, ended_at: now() });
  }
  function endMark(lineId: string) {
    const mark = marks.get(lineId)!;
    marks.delete(lineId);
    ended.push({ id: `h-${ended.length}`, kind: "no_receipt", lineId, documentId: null, reason: mark.reason, created_at: mark.at, ended_at: now() });
  }

  function decide(path: string, method: string, body: Record<string, unknown>): unknown {
    const suggestion = /^\/business\/bank\/suggestions\/([^/]+)\/(confirm|decline)$/.exec(path);
    if (suggestion) {
      const offer = OFFERS.find((item) => item.id === decodeURIComponent(suggestion[1]));
      if (!offer) throw refuse(404, "suggestion_not_found");
      const confirmed = matches.get(offer.lineId)?.documentId === offer.documentId;
      if (suggestion[2] === "decline") {
        if (confirmed) throw refuse(409, "suggestion_not_pending");
        declined.add(offer.id);
      } else if (!confirmed) {
        if (declined.has(offer.id)) throw refuse(409, "pair_declined");
        const refusal = outcomeRefusal(offer.lineId);
        if (refusal) throw refusal;
        if (heldBy(offer.documentId)) throw refuse(409, "document_already_matched");
        matches.set(offer.lineId, { documentId: offer.documentId, at: now() });
      }
      return { id: offer.id, line_id: offer.lineId, target_id: offer.documentId, target_kind: documentById.get(offer.documentId)!.kind, status: declined.has(offer.id) ? "declined" : matches.get(offer.lineId)?.documentId === offer.documentId ? "confirmed" : "pending", amount_score: "1.000", date_score: "1.000", merchant_score: "1.000", confidence: offer.confidence, actionable: false };
    }
    const movement = /^\/business\/bank\/movements\/([^/]+)\/(match|unmatch|disposition)$/.exec(path);
    if (!movement) throw refuse(404, "not_found");
    const lineId = decodeURIComponent(movement[1]);
    const line = lineOrRefuse(lineId);
    if (movement[2] === "match") {
      const document = documentById.get(String(body.activity_id));
      if (!document) throw refuse(404, "business_record_not_found");
      const signed = document.kind === "receipt" ? -document.totalMinor : document.totalMinor;
      if (document.currency !== line.currency || signed !== line.amountMinor) throw refuse(422, "document_not_matchable");
      const refusal = outcomeRefusal(lineId);
      if (refusal) throw refusal;
      if (heldBy(document.id)) throw refuse(409, "document_already_matched");
      matches.set(lineId, { documentId: document.id, at: now() });
    } else if (movement[2] === "unmatch") {
      if (!matches.has(lineId)) throw refuse(409, "line_not_matched");
      endMatch(lineId);
    } else if (method === "PUT") {
      if (matches.has(lineId)) throw refuse(409, "line_already_confirmed");
      const reason = body.reason as NoComprobanteReason;
      if (marks.get(lineId)?.reason !== reason) {
        if (marks.has(lineId)) endMark(lineId);
        marks.set(lineId, { reason, at: now() });
      }
    } else {
      if (!marks.has(lineId)) throw refuse(409, "line_not_marked");
      endMark(lineId);
    }
    return itemOf(lineId);
  }

  function history(lineId: string) {
    lineOrRefuse(lineId);
    const live = [
      ...(matches.has(lineId) ? [{ id: `live-match-${lineId}`, kind: "match" as const, documentId: matches.get(lineId)!.documentId, reason: null, created_at: matches.get(lineId)!.at, ended_at: null }] : []),
      ...(marks.has(lineId) ? [{ id: `live-mark-${lineId}`, kind: "no_receipt" as const, documentId: null, reason: marks.get(lineId)!.reason, created_at: marks.get(lineId)!.at, ended_at: null }] : []),
    ];
    return [...ended.filter((entry) => entry.lineId === lineId), ...live]
      .sort((left, right) => left.created_at.localeCompare(right.created_at))
      .map((entry) => ({ id: entry.id, kind: entry.kind, target_kind: entry.documentId ? documentById.get(entry.documentId)!.kind : null, activity_id: entry.documentId, reason: entry.reason, created_at: entry.created_at, ended_at: entry.ended_at }));
  }

  return async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const [route, search = ""] = path.split("?");
    const method = init?.method ?? "GET";
    if (method === "GET" && route === "/business/bank/movements") return movements(new URLSearchParams(search)) as T;
    const historyRoute = /^\/business\/bank\/movements\/([^/]+)\/history$/.exec(route);
    if (method === "GET" && historyRoute) return history(decodeURIComponent(historyRoute[1])) as T;
    const key = new Headers(init?.headers).get("Idempotency-Key");
    if (!key) throw refuse(400, "idempotency_key_required");
    if (answered.has(key)) return answered.get(key) as T;
    if (failDecide) {
      failDecide = false;
      throw refuse(503, "business_bank_unavailable");
    }
    const answer = decide(route, method, init?.body ? JSON.parse(String(init.body)) : {});
    answered.set(key, answer);
    return answer as T;
  };
}
