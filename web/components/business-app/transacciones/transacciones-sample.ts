import type { Decision, DecisionKind, DocumentSummary, Match, Money, Movement, MovementAccount, TransaccionesSource, TransaccionesView } from "./transacciones-model";
import { MATCH_STATES, signOf, sumByCurrency as sums } from "./transacciones-model";

/**
 * Sample data for the local design preview, standing in for the movements
 * read the backend does not serve yet. Every name, RNC and NCF is invented.
 * The sample plays the server: it keeps decisions, takes them back, and
 * computes the period's totals, so the screen never adds rows itself.
 */

const CORRIENTE: MovementAccount = { kind: "bank", name: "Corriente", last4: "4521" };
const TARJETA: MovementAccount = { kind: "card", name: "Tarjeta", last4: "9932" };
const CAJA: MovementAccount = { kind: "cash", name: "Caja chica", last4: null };

const dop = (amount: string): Money => ({ amount, currency: "DOP" });

function doc(id: string, kind: DocumentSummary["kind"], counterparty: string, daysAgo: number, total: string, extra: Partial<DocumentSummary> = {}): (anchor: string) => DocumentSummary {
  return (anchor) => ({ id, kind, counterparty, occurredOn: shift(anchor, daysAgo), rnc: null, ncf: null, itbis: null, total: dop(total), ...extra });
}

type Seed = Readonly<{
  id: string;
  daysAgo: number;
  counterparty: string;
  bankText: string | null;
  money: Money;
  categoryId: string | null;
  account: MovementAccount | null;
  match: (anchor: string) => Match;
}>;

const SEEDS: readonly Seed[] = [
  { id: "mv-ferreteria", daysAgo: 3, counterparty: "Ferretería La Esquina", bankText: "COMPRA POS FERRET LA ESQUINA", money: dop("-3450.00"), categoryId: "shopping", account: CORRIENTE, match: (anchor) => ({ state: "sugerencia", suggestion: { id: "sg-ferreteria", confidence: 0.93, documentKind: "recibo", document: doc("doc-ferreteria", "recibo", "Ferretería La Esquina SRL", 4, "3450.00", { rnc: "1-01-12345-6", ncf: "B0100004512", itbis: dop("526.27") })(anchor), reasons: [{ kind: "amount" }, { kind: "date", daysBefore: 1 }, { kind: "name" }] } }) },
  { id: "mv-dgii", daysAgo: 3, counterparty: "Impuesto DGII 0.15%", bankText: "IMP DGII 0.15% TRANSF", money: dop("-5.18"), categoryId: "interest_fees", account: CORRIENTE, match: () => ({ state: "no_lleva", reason: "cargo_banco" }) },
  { id: "mv-estacion", daysAgo: 4, counterparty: "Estación Ruta 3", bankText: "COMPRA EST RUTA 3", money: dop("-2100.00"), categoryId: "transport", account: TARJETA, match: (anchor) => ({ state: "igualada", document: doc("doc-estacion", "recibo", "Estación Ruta 3", 4, "2100.00", { ncf: "B0100000877", itbis: dop("320.34") })(anchor) }) },
  { id: "mv-colmado", daysAgo: 4, counterparty: "Colmado Don Pepe", bankText: "COMPRA POS COLMADO DON PEPE", money: dop("-860.00"), categoryId: null, account: CORRIENTE, match: () => ({ state: "falta_comprobante" }) },
  { id: "mv-caribe", daysAgo: 5, counterparty: "Inversiones Caribe SRL", bankText: "TRANSF RECIBIDA INV CARIBE", money: dop("42940.68"), categoryId: null, account: CORRIENTE, match: (anchor) => ({ state: "igualada_en_parte", document: doc("doc-caribe", "venta", "Inversiones Caribe SRL", 12, "45000.00", { ncf: "B0100000301", rnc: "1-31-55555-2" })(anchor), missing: dop("2059.32") }) },
  { id: "mv-verificacion", daysAgo: 5, counterparty: "Verificación de tarjeta", bankText: "VERIF TARJETA", money: dop("0.00"), categoryId: "interest_fees", account: TARJETA, match: () => ({ state: "no_lleva", reason: "cargo_banco" }) },
  { id: "mv-nube", daysAgo: 6, counterparty: "Nube Hosting", bankText: "NUBE HOSTING INTL", money: { amount: "-24.00", currency: "USD" }, categoryId: "other", account: TARJETA, match: (anchor) => ({ state: "igualada", document: doc("doc-nube", "recibo", "Nube Hosting", 6, "24.00", { total: { amount: "24.00", currency: "USD" } })(anchor) }) },
  { id: "mv-caja", daysAgo: 6, counterparty: "Transferencia a Caja chica", bankText: "TRANSF A CAJA CHICA", money: dop("-5000.00"), categoryId: null, account: CORRIENTE, match: () => ({ state: "no_lleva", reason: "entre_cuentas" }) },
  { id: "mv-electrico", daysAgo: 7, counterparty: "Servicio eléctrico, contrato 4471", bankText: "PAGO SERV ELECTRICO 4471", money: dop("-4180.00"), categoryId: "housing", account: CORRIENTE, match: (anchor) => ({ state: "sugerencia", suggestion: { id: "sg-electrico", confidence: 0.74, documentKind: "recibo", document: doc("doc-electrico", "recibo", "Empresa Distribuidora del Este", 11, "4180.00", { rnc: "1-01-82125-6", ncf: "B0100015530", itbis: dop("637.63") })(anchor), reasons: [{ kind: "amount" }, { kind: "date", daysBefore: 4 }] } }) },
  { id: "mv-comedor", daysAgo: 8, counterparty: "Comedor Doña Ana", bankText: null, money: dop("-1250.00"), categoryId: "dining", account: CAJA, match: (anchor) => ({ state: "igualada", document: doc("doc-comedor", "recibo", "Comedor Doña Ana", 8, "1250.00")(anchor) }) },
  { id: "mv-supermercado", daysAgo: 8, counterparty: "Supermercado La Económica", bankText: "COMPRA SUPER LA ECONOMICA", money: dop("-3290.75"), categoryId: null, account: TARJETA, match: () => ({ state: "falta_comprobante" }) },
  { id: "mv-repuestos", daysAgo: 9, counterparty: "Repuestos Duarte", bankText: "DEP TRANSF REPUESTOS DUARTE", money: dop("12500.00"), categoryId: null, account: CORRIENTE, match: (anchor) => ({ state: "sugerencia", suggestion: { id: "sg-repuestos", confidence: 0.86, documentKind: "venta", document: doc("doc-repuestos", "venta", "Repuestos Duarte", 10, "12500.00", { rnc: "1-30-44210-9", ncf: "B0100000298", itbis: dop("1906.78") })(anchor), reasons: [{ kind: "amount" }, { kind: "date", daysBefore: 1 }, { kind: "name" }] } }) },
  { id: "mv-ozama", daysAgo: 10, counterparty: "Inmobiliaria Ozama SRL", bankText: "TRANSF INMOB OZAMA", money: dop("-35000.00"), categoryId: "housing", account: CORRIENTE, match: (anchor) => ({ state: "igualada", document: doc("doc-ozama", "recibo", "Inmobiliaria Ozama SRL", 10, "35000.00", { ncf: "B0100000310" })(anchor) }) },
  { id: "doc-taller", daysAgo: 11, counterparty: "Taller Mecánico Reyes", bankText: null, money: dop("-4500.00"), categoryId: "transport", account: CORRIENTE, match: (anchor) => ({ state: "sin_movimiento", document: doc("doc-taller", "recibo", "Taller Mecánico Reyes", 11, "4500.00", { ncf: "B0100000144" })(anchor) }) },
  { id: "mv-farmacia", daysAgo: 12, counterparty: "Farmacia Los Ríos", bankText: "COMPRA FARM LOS RIOS", money: dop("-1145.50"), categoryId: "health", account: TARJETA, match: () => ({ state: "falta_comprobante" }) },
  { id: "mv-pena", daysAgo: 13, counterparty: "Distribuidora Hermanos Peña", bankText: "DEP TRANSF DIST HNOS PENA", money: dop("35140.00"), categoryId: null, account: CORRIENTE, match: (anchor) => ({ state: "igualada", document: doc("doc-pena", "venta", "Distribuidora Hermanos Peña", 15, "35140.00", { ncf: "B0100000295" })(anchor) }) },
  { id: "mv-papeleria", daysAgo: 14, counterparty: "Papelería El Estudiante", bankText: "COMPRA PAPELERIA EL ESTUD", money: dop("-980.00"), categoryId: "shopping", account: TARJETA, match: (anchor) => ({ state: "igualada", document: doc("doc-papeleria", "recibo", "Papelería El Estudiante", 14, "980.00", { ncf: "B0200004410" })(anchor) }) },
  { id: "mv-comision", daysAgo: 15, counterparty: "Comisión por manejo de cuenta", bankText: "COMISION MANEJO CTA", money: dop("-350.00"), categoryId: "interest_fees", account: CORRIENTE, match: () => ({ state: "no_lleva", reason: "cargo_banco" }) },
  { id: "mv-gasolinera", daysAgo: 16, counterparty: "Gasolinera El Malecón", bankText: "COMPRA GAS EL MALECON", money: dop("-2500.00"), categoryId: "transport", account: TARJETA, match: (anchor) => ({ state: "igualada", document: doc("doc-gasolinera", "recibo", "Gasolinera El Malecón", 16, "2500.00", { ncf: "B0100007781" })(anchor) }) },
  { id: "mv-agua", daysAgo: 17, counterparty: "Agua Pura del Cibao", bankText: "COMPRA AGUA PURA CIBAO", money: dop("-1200.00"), categoryId: "groceries", account: CAJA, match: (anchor) => ({ state: "igualada", document: doc("doc-agua", "recibo", "Agua Pura del Cibao", 17, "1200.00")(anchor) }) },
  { id: "mv-retiro", daysAgo: 18, counterparty: "Retiro en cajero", bankText: "RETIRO ATM", money: dop("-3000.00"), categoryId: null, account: CORRIENTE, match: () => ({ state: "no_lleva", reason: "personal" }) },
];

function shift(day: string, daysAgo: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

export type SampleOptions = Readonly<{ empty?: boolean; failLoad?: boolean; failDecide?: boolean; supports?: readonly DecisionKind[] }>;

/**
 * A fresh sample per preview. Dates count back from the period's last day,
 * so whatever month the preview opens on has its rows.
 */
export function createSampleTransaccionesSource(options: SampleOptions = {}): TransaccionesSource {
  const decided = new Map<string, Match>();
  const seen = new Map<string, Match>();
  const undoStack = new Map<string, Match>();
  let failDecide = options.failDecide ?? false;
  const supported = new Set<DecisionKind>(options.supports ?? ["igualar", "rechazar", "sin_comprobante", "desigualar"]);

  const matchOf = (seed: Seed, anchor: string): Match => decided.get(seed.id) ?? seed.match(anchor);

  return {
    async load(period) {
      if (options.failLoad) throw Object.assign(new Error("sample: movements unavailable"), { status: 503, code: "sample_unavailable" });
      const anchor = period.to ?? new Date().toISOString().slice(0, 10);
      const seeds = options.empty ? [] : SEEDS;
      const movements: Movement[] = seeds.map((seed) => {
        const match = matchOf(seed, anchor);
        seen.set(seed.id, match);
        const occurredOn = shift(anchor, seed.daysAgo);
        return { id: seed.id, occurredOn: occurredOn < period.from ? period.from : occurredOn, counterparty: seed.counterparty, bankText: seed.bankText, money: seed.money, categoryId: seed.categoryId, account: seed.account, match };
      });
      const lines = movements.filter((movement) => movement.match.state !== "sin_movimiento");
      const pending = movements.filter((movement) => MATCH_STATES[movement.match.state].segment === "por_igualar");
      const view: TransaccionesView = {
        mode: "igualar",
        movements,
        totals: {
          entradas: sums(lines.filter((movement) => signOf(movement.money) === "in").map((movement) => movement.money)),
          salidas: sums(lines.filter((movement) => signOf(movement.money) === "out").map((movement) => movement.money)),
          porIgualar: { count: pending.length, amounts: sums(pending.map((movement) => movement.money)) },
          igualadas: { count: lines.length - pending.filter((movement) => movement.match.state !== "sin_movimiento").length, of: lines.length },
        },
        coverageThrough: lines.length ? shift(anchor, Math.min(...seeds.filter((seed) => seed.bankText).map((seed) => seed.daysAgo))) : null,
      };
      return view;
    },
    async decide(decision: Decision) {
      if (failDecide) {
        failDecide = false;
        throw Object.assign(new Error("sample: decision failed once"), { status: 503, code: "sample_unavailable" });
      }
      if (!supported.has(decision.kind)) throw new Error(`sample: ${decision.kind} is not served`);
      const before = seen.get(decision.movementId);
      if (!before) throw new Error("sample: unknown movement");
      const next = afterDecision(decision, before);
      undoStack.set(keyOf(decision), before);
      decided.set(decision.movementId, next);
      seen.set(decision.movementId, next);
    },
    supports: (kind) => supported.has(kind),
    async undo(decision: Decision) {
      const before = undoStack.get(keyOf(decision));
      if (!before) return;
      undoStack.delete(keyOf(decision));
      decided.set(decision.movementId, before);
      seen.set(decision.movementId, before);
    },
  };
}

/** What the sample server records for a decision; a pair that was not offered is refused, as the bank contract refuses it. */
function afterDecision(decision: Decision, before: Match): Match {
  switch (decision.kind) {
    case "igualar":
      if (before.state !== "sugerencia" || before.suggestion.id !== decision.suggestionId) throw Object.assign(new Error("sample: suggestion not pending"), { status: 409, code: "suggestion_not_pending" });
      return { state: "igualada", document: before.suggestion.document };
    case "rechazar":
      return { state: "falta_comprobante" };
    case "sin_comprobante":
      return { state: "no_lleva", reason: decision.reason };
    case "desigualar":
      return { state: "falta_comprobante" };
  }
}

const keyOf = (decision: Decision) => `${decision.kind}:${decision.movementId}`;
