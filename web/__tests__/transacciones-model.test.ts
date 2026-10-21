import assert from "node:assert/strict";
import { afterEach, describe, test } from "bun:test";
import { createBankTransaccionesSource, createRecordsTransaccionesSource, decisionProblem, parseHistory, parseMovementItem, parseMovementsPage, readVentas } from "@/components/business-app/transacciones/transacciones-adapter";
import { createSampleBankServer } from "@/components/business-app/transacciones/transacciones-sample";
import { currencyChoices, headerCurrency, inverse, perCurrency, segmentSections, suggestionRun, tableCounts, type Decision, type IgualarView } from "@/components/business-app/transacciones/transacciones-model";
import { DEFAULT_DENSITY, resetTableDensity, setTableDensity, type DensityProfile } from "@/components/business-app/transacciones/table-density";
import { formatMoney } from "@/components/business-app/business-format";

const OCTOBER = { from: "2026-10-01", to: "2026-10-31" };

/** The `GET /business/bank/movements` example in docs/contracts/business-bank-matching.md, verbatim in shape. */
const document = (overrides: Record<string, unknown> = {}) => ({
  activity_id: "doc-1",
  kind: "receipt",
  counterparty: "Ferreteria La Esquina",
  occurred_on: "2026-10-16",
  currency: "DOP",
  total_minor: 345000,
  total: "3450.00",
  itbis_minor: null,
  itbis: null,
  rnc: null,
  ncf: null,
  ecf: null,
  status: "pendiente",
  settled_on: null,
  payment_method: null,
  category_id: null,
  ...overrides,
});
const item = (overrides: Record<string, unknown> = {}) => ({
  kind: "movement",
  id: "line-1",
  occurred_on: "2026-10-17",
  description: "COMPRA  FERRETERIA LA ESQUINA",
  counterparty: "COMPRA FERRETERIA LA ESQUINA",
  sense: "charge",
  currency: "DOP",
  amount_minor: -345000,
  amount: "-3450.00",
  state: "sugerencia",
  reason: null,
  category_id: null,
  account: { account_id: "acc-1", name: "Cuenta Popular", type: "checking" },
  method: "transferencia",
  document: null,
  suggestions: [{ id: "sg-1", confidence: "0.850", reasons: [{ code: "monto_exacto", days: null }, { code: "fecha_cercana", days: -1 }, { code: "nombre_parecido", days: null }], document: document() }],
  ...overrides,
});
const counts = (overrides: Record<string, number> = {}) => ({ movimientos: 4, igualadas: 0, no_lleva_comprobante: 1, sugerencias: 2, falta_comprobante: 1, sin_movimiento: 1, por_igualar: 4, ...overrides });
const block = (overrides: Record<string, unknown> = {}) => ({ currency: "DOP", entradas_minor: 500000, entradas: "5000.00", salidas_minor: 360000, salidas: "3600.00", por_igualar_minor: 950000, por_igualar: "9500.00", counts: counts(), ...overrides });
const page = (overrides: Record<string, unknown> = {}) => ({
  period_start: "2026-10-01",
  period_end: "2026-10-31",
  segment: "por_igualar",
  sense: null,
  accounts: [{ account_id: "acc-1", name: "Cuenta Popular", type: "checking", bank_account_id: "bank-1", currency: "DOP", covered_through: "2026-10-20" }],
  currency: "DOP",
  totals: [block()],
  counts: counts({ movimientos: 5, sugerencias: 2, falta_comprobante: 2, sin_movimiento: 1, no_lleva_comprobante: 1, por_igualar: 5 }),
  other_currencies: [{ currency: "USD", count: 1 }],
  items: [item()],
  next_cursor: null,
  ...overrides,
});

const refusal = (status: number, code: string) => Object.assign(new Error(code), { status, code });

describe("Monto header currency", () => {
  const row = (currency: string) => ({ money: { amount: "1.00", currency } });
  test("it names the Business currency when a row holds it, else the only currency, and never guesses pesos", () => {
    assert.equal(headerCurrency([row("USD"), row("DOP")], "DOP"), "DOP");
    assert.equal(headerCurrency([row("USD"), row("DOP")], "USD"), "USD");
    assert.equal(headerCurrency([row("USD"), row("DOP")]), null);
    assert.equal(headerCurrency([row("USD"), row("EUR")], "DOP"), null);
    assert.equal(headerCurrency([row("USD"), row("USD")]), "USD");
    assert.equal(headerCurrency([]), null);
  });
});

describe("bank adapter: the movements read", () => {
  test("the contract's own answer maps to the view: state, suggestion, reasons, account, totals and coverage", () => {
    const { view, hasStatement } = parseMovementsPage(page());
    assert.equal(hasStatement, true);
    assert.equal(view.segment, "por_igualar");
    assert.equal(view.coverageThrough, "2026-10-20");
    assert.equal(view.accountCurrency, "DOP");
    const [row] = view.movements;
    assert.deepEqual(row.money, { amount: "-3450.00", currency: "DOP" });
    assert.equal(row.counterparty, "COMPRA FERRETERIA LA ESQUINA");
    assert.equal(row.bankText, "COMPRA  FERRETERIA LA ESQUINA");
    assert.deepEqual(row.account, { kind: "bank", name: "Cuenta Popular" });
    assert.ok(row.match.state === "sugerencia");
    assert.equal(row.match.suggestion.id, "sg-1");
    assert.equal(row.match.suggestion.document.counterparty, "Ferreteria La Esquina");
    assert.deepEqual(row.match.suggestion.document.total, { amount: "3450.00", currency: "DOP" });
    assert.deepEqual(row.match.suggestion.reasons, [{ kind: "amount" }, { kind: "date", days: -1 }, { kind: "name" }]);
    assert.deepEqual(view.totals, [{ currency: "DOP", entradas: "5000.00", salidas: "3600.00", porIgualar: "9500.00", counts: { movimientos: 4, igualadas: 0, noLleva: 1, sugerencias: 2, faltaComprobante: 1, sinMovimiento: 1, porIgualar: 4 } }]);
  });

  test("each server state is its own match; a zero line's reason is the server's own", () => {
    const states = [
      item({ id: "a", state: "igualada", suggestions: [], document: document({ ncf: null, ecf: "E310000000012" }) }),
      item({ id: "b", state: "falta_comprobante", suggestions: [] }),
      item({ id: "c", state: "no_lleva_comprobante", reason: "entre_cuentas", suggestions: [] }),
      item({ id: "d", state: "no_lleva_comprobante", reason: "monto_cero", amount_minor: 0, amount: "0.00", sense: "zero", suggestions: [] }),
      item({ id: "e", kind: "document", state: "sin_movimiento", description: null, suggestions: [], document: document() }),
    ].map((wire) => parseMovementItem(wire).match);
    assert.deepEqual(states.map((match) => match.state), ["igualada", "falta_comprobante", "no_lleva", "no_lleva", "sin_movimiento"]);
    assert.ok(states[0].state === "igualada" && states[0].document?.ncf === "E310000000012", "an e-CF stands in for the NCF");
    assert.ok(states[2].state === "no_lleva" && states[2].reason === "entre_cuentas");
    assert.ok(states[3].state === "no_lleva" && states[3].reason === "monto_cero");
  });

  test("a shape the screen cannot trust fails the load instead of rendering half a list", () => {
    assert.throws(() => parseMovementsPage(page({ items: [item({ amount: "mucho" })] })));
    assert.throws(() => parseMovementsPage(page({ items: [item({ state: "igualada_en_parte" })] })));
    assert.throws(() => parseMovementsPage(page({ items: [item({ suggestions: [] })] })), "a suggestion row with no suggestion");
    assert.throws(() => parseMovementsPage(page({ items: [item({ amount_minor: -3450.5 })] })), "minor units are whole");
    assert.throws(() => parseMovementsPage(page({ totals: [block({ counts: { movimientos: 1 } })] })));
    assert.throws(() => parseMovementsPage({ items: [] }));
  });

  test("a missing currency is never read as pesos: the row refuses, and nothing becomes DOP", () => {
    const { currency: _drop, ...noCurrency } = item();
    assert.throws(() => parseMovementItem(noCurrency));
    assert.throws(() => parseMovementItem(item({ currency: null })));
    assert.throws(() => parseMovementItem(item({ currency: "" })));
    assert.throws(() => parseMovementsPage(page({ totals: [block({ currency: undefined })] })));
  });

  test("each currency keeps its own exponent: no figure is padded, cut or re-scaled to two decimals", () => {
    const yen = parseMovementItem(item({ currency: "JPY", amount_minor: -1500, amount: "-1500", suggestions: [], state: "falta_comprobante" }));
    const dinar = parseMovementItem(item({ currency: "KWD", amount_minor: -1250, amount: "-1.250", suggestions: [], state: "falta_comprobante" }));
    assert.deepEqual(yen.money, { amount: "-1500", currency: "JPY" });
    assert.deepEqual(dinar.money, { amount: "-1.250", currency: "KWD" });
    assert.match(formatMoney("1500", "JPY", "es-419"), /1,500$/);
    assert.doesNotMatch(formatMoney("1500", "JPY", "es-419"), /\./);
    assert.match(formatMoney("1.250", "KWD", "es-419"), /1\.250$/);
    assert.match(formatMoney("24.00", "USD", "es-419"), /^US\$ 24\.00$/);
  });

  test("totals stay one per currency, never added", () => {
    const { view } = parseMovementsPage(page({
      currency: null,
      other_currencies: [],
      totals: [block(), block({ currency: "USD", entradas_minor: 0, entradas: "0.00", salidas_minor: 2400, salidas: "24.00", por_igualar_minor: 2400, por_igualar: "24.00", counts: counts({ movimientos: 1, sugerencias: 0, falta_comprobante: 1, sin_movimiento: 0, no_lleva_comprobante: 0, por_igualar: 1 }) })],
    }));
    assert.deepEqual(perCurrency(view.totals, "salidas"), [{ currency: "DOP", amount: "3600.00" }, { currency: "USD", amount: "24.00" }]);
    assert.deepEqual(perCurrency(view.totals, "porIgualar"), [{ currency: "DOP", amount: "9500.00" }, { currency: "USD", amount: "24.00" }]);
  });

  test("counts are the server's, never added on the web: the chosen currency's block for its rows, the period's across currencies", () => {
    const period = counts({ movimientos: 90, igualadas: 40, por_igualar: 33 });
    const chosen = parseMovementsPage(page({ counts: period, totals: [block({ counts: counts({ movimientos: 7, por_igualar: 3 }) })] })).view;
    assert.equal(chosen.currency, "DOP");
    assert.equal(chosen.counts?.movimientos, 90, "the period's own count, not a sum of blocks");
    assert.equal(chosen.counts?.igualadas, 40);
    assert.equal(tableCounts(chosen)?.porIgualar, 3, "the table covers DOP, so its count is DOP's block");
    assert.deepEqual(chosen.otherCurrencies, [{ currency: "USD", count: 1 }]);
    const none = parseMovementsPage(page({ totals: [] })).view;
    assert.equal(tableCounts(none)?.movimientos, 0, "a chosen currency with no row in the period is a known zero");
    const every = parseMovementsPage(page({ currency: null, other_currencies: [], counts: period, totals: [block(), block({ currency: "USD" })] })).view;
    assert.equal(tableCounts(every)?.movimientos, 90, "every currency listed: the period's counts");
    const older: Record<string, unknown> = page();
    for (const field of ["counts", "currency", "other_currencies"]) delete older[field];
    const old = parseMovementsPage(older).view;
    assert.equal(old.currency, null);
    assert.equal(old.counts, null, "an older server's missing counts are unknown, never summed");
    assert.equal(tableCounts(old), null);
    assert.deepEqual(old.otherCurrencies, []);
    assert.throws(() => parseMovementsPage(page({ other_currencies: [{ currency: "usd", count: 1 }] })));
  });

  test("the currency menu offers the Business currency first, the chosen one and each the server names; none while the server lists every currency", () => {
    const chosen = parseMovementsPage(page({ currency: "USD", totals: [], other_currencies: [{ currency: "DOP", count: 4 }, { currency: "EUR", count: 1 }] })).view;
    assert.deepEqual(currencyChoices(chosen, "DOP"), ["DOP", "USD", "EUR"]);
    assert.deepEqual(currencyChoices(parseMovementsPage(page({ other_currencies: [] })).view, "DOP"), ["DOP"], "one currency, nothing to choose");
    assert.deepEqual(currencyChoices(parseMovementsPage(page({ currency: null, other_currencies: [] })).view, "DOP"), []);
  });

  test("Por igualar comes in the server's order, grouped, each group named with the server's count", () => {
    const { view } = parseMovementsPage(page({
      items: [item({ id: "s1" }), item({ id: "s2" }), item({ id: "f1", state: "falta_comprobante", suggestions: [] }), item({ id: "d1", kind: "document", state: "sin_movimiento", description: null, suggestions: [], document: document() })],
      totals: [block({ counts: counts({ sugerencias: 7, falta_comprobante: 3, sin_movimiento: 1 }) })],
    }));
    const sections = segmentSections(view);
    assert.deepEqual(sections.map((section) => [section.group, section.count, section.rows.map((row) => row.id)]), [["sugerencias", 7, ["s1", "s2"]], ["falta_comprobante", 3, ["f1"]], ["sin_movimiento", 1, ["d1"]]]);
    assert.deepEqual(suggestionRun(view).map((row) => row.id), ["s1", "s2"]);
    assert.deepEqual(suggestionRun({ ...view, segment: "todas" } as IgualarView), [], "the run walks only the server's best-first order");
  });

  test("history parses the line's outcomes, ended ones included", () => {
    assert.deepEqual(parseHistory([{ id: "h1", kind: "match", target_kind: "receipt", activity_id: "doc-1", reason: null, created_at: "2026-10-21T12:00:00Z", ended_at: "2026-10-21T12:01:00Z" }, { id: "h2", kind: "no_receipt", target_kind: null, activity_id: null, reason: "personal", created_at: "2026-10-21T12:02:00Z", ended_at: null }]), [
      { id: "h1", outcome: "match", documentKind: "recibo", reason: null, from: "2026-10-21T12:00:00Z", until: "2026-10-21T12:01:00Z" },
      { id: "h2", outcome: "no_receipt", documentKind: null, reason: "personal", from: "2026-10-21T12:02:00Z", until: null },
    ]);
  });
});

describe("bank adapter: requests", () => {
  const recording = () => {
    const calls: { path: string; method: string; key: string | null; body: unknown }[] = [];
    const fetchJson = async <T,>(path: string, init?: RequestInit): Promise<T> => {
      calls.push({ path, method: init?.method ?? "GET", key: new Headers(init?.headers).get("Idempotency-Key"), body: init?.body ? JSON.parse(String(init.body)) : null });
      if (path.endsWith("/history")) return [] as T;
      return (path.startsWith("/business/bank/movements?") ? page() : item()) as T;
    };
    return { calls, fetchJson };
  };

  test("the read sends the period, the segment, the currency, the page size and the cursor", async () => {
    const { calls, fetchJson } = recording();
    const source = createBankTransaccionesSource(fetchJson);
    await source.load({ ...OCTOBER, segment: "igualadas", currency: "USD", limit: 50, cursor: "abc" });
    await source.load({ ...OCTOBER, segment: "todas", currency: null });
    assert.equal(calls[0].path, "/business/bank/movements?period_start=2026-10-01&period_end=2026-10-31&segment=igualadas&currency=USD&limit=50&cursor=abc");
    assert.equal(calls[1].path, "/business/bank/movements?period_start=2026-10-01&period_end=2026-10-31&segment=todas", "an unknown currency reads every currency");
  });

  test("the period's ventas come from the expenses read with kind=income", async () => {
    const { calls, fetchJson } = recording();
    await readVentas(async <T,>(path: string, init?: RequestInit) => { await fetchJson(path, init); return { items: [] } as T; })("2026-10-01", "2026-10-31");
    assert.equal(calls[0].path, "/business/expenses?from=2026-10-01&to=2026-10-31&kind=income");
  });

  test("every decision is one route with its Idempotency-Key, and Desigualar names which outcome it ends", async () => {
    const { calls, fetchJson } = recording();
    const source = createBankTransaccionesSource(fetchJson);
    const decisions: Decision[] = [
      { kind: "igualar", movementId: "l 1", suggestionId: "s 1", documentId: "doc-1" },
      { kind: "rechazar", movementId: "l1", suggestionId: "s2" },
      { kind: "igualar_con", movementId: "l1", documentId: "doc-9" },
      { kind: "desigualar", movementId: "l1", outcome: { kind: "match", documentId: "doc-9" } },
      { kind: "sin_comprobante", movementId: "l1", reason: "cargo_banco" },
      { kind: "desigualar", movementId: "l1", outcome: { kind: "no_receipt", reason: "cargo_banco" } },
    ];
    for (const [index, decision] of decisions.entries()) await source.decide(decision, `key-${index}`);
    await source.history("l1");
    assert.deepEqual(calls.map((call) => [call.method, call.path, call.key, call.body]), [
      ["POST", "/business/bank/suggestions/s%201/confirm", "key-0", null],
      ["POST", "/business/bank/suggestions/s2/decline", "key-1", null],
      ["POST", "/business/bank/movements/l1/match", "key-2", { activity_id: "doc-9" }],
      ["POST", "/business/bank/movements/l1/unmatch", "key-3", null],
      ["PUT", "/business/bank/movements/l1/disposition", "key-4", { reason: "cargo_banco" }],
      ["DELETE", "/business/bank/movements/l1/disposition", "key-5", null],
      ["GET", "/business/bank/movements/l1/history", null, null],
    ]);
  });

  test("with the routes off, or before any statement, the saved records list; any other failure stays a failure", async () => {
    const records = createRecordsTransaccionesSource({ expenses: async () => [], ventas: async () => [], overview: async () => ({ from: "2026-10-01", to: "2026-10-31", today: "2026-10-21", totals: [], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null }), workspace: async () => ({ accounts: [] }), ownerFunds: "Dinero del dueño" });
    const off = createBankTransaccionesSource(async () => { throw refusal(404, "business_unavailable"); }, records);
    assert.equal((await off.load({ ...OCTOBER, segment: "por_igualar" })).mode, "records");
    const noStatement = createBankTransaccionesSource(async <T,>() => page({ accounts: [{ account_id: "a", name: null, type: "checking", bank_account_id: "b", currency: "DOP", covered_through: null }], items: [], totals: [] }) as T, records);
    assert.equal((await noStatement.load({ ...OCTOBER, segment: "por_igualar" })).mode, "records");
    const down = createBankTransaccionesSource(async () => { throw refusal(503, "business_bank_unavailable"); }, records);
    await assert.rejects(down.load({ ...OCTOBER, segment: "por_igualar" }));
  });

  test("each refusal maps to what the screen says and the way out it offers", () => {
    const expected: Record<string, [string, string]> = {
      line_not_found: ["line_not_found", "reload"],
      line_marked_no_receipt: ["line_marked_no_receipt", "reload"],
      line_not_matched: ["line_not_matched", "reload"],
      line_not_marked: ["line_not_marked", "reload"],
      document_already_matched: ["document_already_matched", "reload"],
      business_document_matched: ["business_document_matched", "reload"],
      document_not_matchable: ["document_not_matchable", "none"],
      suggestion_not_pending: ["changed", "reload"],
      business_bank_unavailable: ["unavailable", "retry"],
      something_new: ["unavailable", "retry"],
    };
    for (const [code, [shown, action]] of Object.entries(expected)) assert.deepEqual(decisionProblem(refusal(409, code)), { code: shown, action }, code);
    assert.deepEqual(decisionProblem(new TypeError("Failed to fetch")), { code: "unavailable", action: "retry" });
  });

  test("Deshacer is each decision's inverse; a declined pair has none", () => {
    assert.deepEqual(inverse({ kind: "igualar", movementId: "l", suggestionId: "s", documentId: "d" }), { kind: "desigualar", movementId: "l", outcome: { kind: "match", documentId: "d" } });
    assert.deepEqual(inverse({ kind: "desigualar", movementId: "l", outcome: { kind: "match", documentId: "d" } }), { kind: "igualar_con", movementId: "l", documentId: "d" });
    assert.deepEqual(inverse({ kind: "sin_comprobante", movementId: "l", reason: "personal" }), { kind: "desigualar", movementId: "l", outcome: { kind: "no_receipt", reason: "personal" } });
    assert.deepEqual(inverse({ kind: "desigualar", movementId: "l", outcome: { kind: "no_receipt", reason: "personal" } }), { kind: "sin_comprobante", movementId: "l", reason: "personal" });
    assert.equal(inverse({ kind: "rechazar", movementId: "l", suggestionId: "s" }), null);
  });
});

describe("sample bank server", () => {
  const read = async (fetchJson: ReturnType<typeof createSampleBankServer>, segment: "por_igualar" | "igualadas" | "todas", extra = "") => parseMovementsPage(await fetchJson(`/business/bank/movements?period_start=2026-10-01&period_end=2026-10-31&segment=${segment}${extra}`)).view;
  const post = (fetchJson: ReturnType<typeof createSampleBankServer>, path: string, key: string, method = "POST", body?: unknown) => fetchJson(path, { method, headers: { "Idempotency-Key": key }, body: body ? JSON.stringify(body) : undefined });

  test("it answers in the contract's shape, with totals one per currency, and the counts move with a decision", async () => {
    const bank = createSampleBankServer();
    const before = await read(bank, "por_igualar");
    assert.deepEqual(before.totals.map((block) => block.currency), ["DOP", "USD"]);
    assert.equal(before.counts?.sugerencias, 3);
    assert.equal(perCurrency(before.totals, "salidas").find((money) => money.currency === "USD")?.amount, "24.00");
    await post(bank, "/business/bank/suggestions/sg-ferreteria/confirm", "k1");
    const after = await read(bank, "por_igualar");
    assert.equal(after.counts?.sugerencias, 2);
    assert.equal(after.counts?.porIgualar, before.counts!.porIgualar - 1);
    assert.equal((await read(bank, "igualadas")).movements.find((row) => row.id === "mv-ferreteria")?.match.state, "igualada");
  });

  test("the same key twice is one decision; Desigualar puts the suggestion back", async () => {
    const bank = createSampleBankServer();
    await post(bank, "/business/bank/movements/mv-colmado/disposition", "same", "PUT", { reason: "personal" });
    await post(bank, "/business/bank/movements/mv-colmado/disposition", "same", "PUT", { reason: "personal" });
    const history = parseHistory(await bank("/business/bank/movements/mv-colmado/history"));
    assert.equal(history.length, 1);
    await post(bank, "/business/bank/suggestions/sg-ferreteria/confirm", "c1");
    await post(bank, "/business/bank/movements/mv-ferreteria/unmatch", "u1");
    assert.equal((await read(bank, "por_igualar")).movements.find((row) => row.id === "mv-ferreteria")?.match.state, "sugerencia");
    await assert.rejects(post(bank, "/business/bank/movements/mv-ferreteria/unmatch", "u2"), /line_not_matched/);
  });

  test("with a currency it lists and totals only that currency, names what it leaves out, and keeps the period's counts", async () => {
    const bank = createSampleBankServer();
    const all = await read(bank, "todas");
    const dollars = await read(bank, "todas", "&currency=USD");
    assert.equal(dollars.currency, "USD");
    assert.deepEqual(dollars.movements.map((row) => row.money.currency), ["USD"]);
    assert.deepEqual(dollars.totals.map((block) => block.currency), ["USD"]);
    assert.deepEqual(dollars.otherCurrencies, [{ currency: "DOP", count: all.movements.length - 1 }]);
    assert.deepEqual(dollars.counts, all.counts, "the period's counts ignore the currency");
    assert.deepEqual((await read(bank, "por_igualar", "&currency=USD")).otherCurrencies.map((other) => other.currency), ["DOP"]);
    assert.deepEqual(all.otherCurrencies, [], "nothing is left out while no currency is chosen");
    await assert.rejects(read(bank, "todas", "&currency=usd"), /validation_error/);
  });

  test("a cursor is only a position: a DOP cursor sent with currency=USD returns no rows", async () => {
    const bank = createSampleBankServer();
    const pesos = await read(bank, "todas", "&currency=DOP&limit=5");
    assert.ok(pesos.nextCursor);
    assert.equal((await read(bank, "todas", `&currency=USD&limit=5&cursor=${pesos.nextCursor}`)).movements.length, 0);
  });

  test("it pages with a cursor, and refuses one it did not hand out", async () => {
    const bank = createSampleBankServer();
    const first = await read(bank, "todas", "&limit=5");
    assert.equal(first.movements.length, 5);
    assert.ok(first.nextCursor);
    const second = await read(bank, "todas", `&limit=5&cursor=${first.nextCursor}`);
    assert.equal(new Set([...first.movements, ...second.movements].map((row) => row.id)).size, 10);
    await assert.rejects(read(bank, "todas", "&cursor=nope"), /invalid_cursor/);
  });
});

describe("table density", () => {
  afterEach(() => resetTableDensity());
  const profile = (stored: unknown, write: DensityProfile["write"] = async () => undefined) => {
    const writes: string[] = [];
    return { writes, profile: { read: async () => stored, write: async (next: Parameters<DensityProfile["write"]>[0]) => { writes.push(next); await write(next); } } satisfies DensityProfile };
  };
  test("Normal is the default for everyone until the profile answers", () => {
    assert.equal(DEFAULT_DENSITY, "normal");
  });

  test("a choice is written to the profile; a refused write puts the kept choice back and says so", async () => {
    const saved = profile("normal");
    resetTableDensity(saved.profile);
    assert.equal(await setTableDensity("compacto"), true);
    assert.deepEqual(saved.writes, ["compacto"]);
    const refused = profile("normal", async () => { throw refusal(422, "validation_error"); });
    resetTableDensity(refused.profile);
    assert.equal(await setTableDensity("amplio"), false);
  });
});
