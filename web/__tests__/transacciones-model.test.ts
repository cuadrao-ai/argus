import assert from "node:assert/strict";
import { afterEach, describe, test } from "bun:test";
import { createBankTransaccionesSource, mapBankWire, parseBankWire } from "@/components/business-app/transacciones/transacciones-adapter";
import { createSampleTransaccionesSource } from "@/components/business-app/transacciones/transacciones-sample";
import { defaultSegment, headerCurrency, inHeaderOrder, rowActions, segmentSections, suggestionRun, type Movement } from "@/components/business-app/transacciones/transacciones-model";
import { DEFAULT_DENSITY, densityPreference, resetTableDensity } from "@/components/business-app/transacciones/table-density";

const OCTOBER = { from: "2026-10-01", to: "2026-10-31" };

const line = (id: string, overrides: Record<string, unknown> = {}) => ({ id, occurred_on: "2026-10-16", description: `COMPRA ${id}`, amount: "-860.00", currency: "DOP", sense: "charge", state: "sin_comprobante", ...overrides });
const suggestion = (id: string, lineId: string, overrides: Record<string, unknown> = {}) => ({ id, line_id: lineId, target_id: `doc-${id}`, target_kind: "receipt", status: "pending", amount_score: "1.000", date_score: "0.800", merchant_score: "0.000", confidence: "0.600", actionable: true, ...overrides });
const page = (lines: unknown[], count = lines.length) => ({ count, period_start: "2026-10-01", period_end: "2026-10-31", lines });

describe("bank adapter", () => {
  test("a charge with a pending suggestion is a Sugerencia; one without is Falta comprobante", () => {
    const view = mapBankWire(parseBankWire(page([line("a"), line("b")]), [suggestion("s1", "a")]));
    const [a, b] = view.movements;
    assert.equal(a.match.state, "sugerencia");
    assert.equal(b.match.state, "falta_comprobante");
    if (a.match.state !== "sugerencia") throw new Error("unreachable");
    assert.equal(a.match.suggestion.id, "s1");
    assert.equal(a.match.suggestion.documentKind, "recibo");
    assert.deepEqual(a.match.suggestion.reasons, [{ kind: "amount" }, { kind: "date", daysBefore: null }]);
    assert.deepEqual(a.money, { amount: "-860.00", currency: "DOP" });
    assert.equal(a.bankText, "COMPRA a");
  });

  test("the most confident pending pair is the one offered; declined and spent pairs never show", () => {
    const view = mapBankWire(parseBankWire(page([line("a"), line("b")]), [
      suggestion("low", "a", { confidence: "0.400" }),
      suggestion("high", "a", { confidence: "0.900", target_kind: "venta" }),
      suggestion("declined", "b", { status: "declined", actionable: false }),
      suggestion("spent", "b", { actionable: false }),
    ]));
    const [a, b] = view.movements;
    assert.ok(a.match.state === "sugerencia" && a.match.suggestion.id === "high" && a.match.suggestion.documentKind === "venta");
    assert.equal(b.match.state, "falta_comprobante");
  });

  test("facts the server does not serve stay unknown: no account, category, document or totals are invented", () => {
    const view = mapBankWire(parseBankWire(page([line("a")], 7), [suggestion("s1", "a")]));
    const [a] = view.movements;
    assert.equal(a.account, null);
    assert.equal(a.categoryId, null);
    assert.equal(a.counterparty, null);
    assert.ok(a.match.state === "sugerencia" && a.match.suggestion.document === null);
    assert.deepEqual(view.totals, { entradas: null, salidas: null, porIgualar: { count: 7, amounts: null }, igualadas: null });
    assert.equal(view.coverageThrough, null);
  });

  test("a malformed answer fails the load instead of rendering half a list", () => {
    assert.throws(() => parseBankWire(page([line("a", { amount: "mucho" })]), []));
    assert.throws(() => parseBankWire(page([line("a")]), [suggestion("s", "a", { target_kind: "factura" })]));
    assert.throws(() => parseBankWire({ lines: [] }, []));
  });

  test("the live source reads today's two routes for the period and posts confirm and decline with the key", async () => {
    const calls: { path: string; init?: RequestInit }[] = [];
    const fetchJson = async <T,>(path: string, init?: RequestInit): Promise<T> => {
      calls.push({ path, init });
      if (path.startsWith("/business/bank/unmatched")) return page([line("a")]) as T;
      if (path.startsWith("/business/bank/suggestions?")) return [suggestion("s1", "a")] as T;
      return {} as T;
    };
    const source = createBankTransaccionesSource(fetchJson);
    const view = await source.load(OCTOBER);
    assert.equal(view.movements.length, 1);
    assert.deepEqual(calls.map((call) => call.path).sort(), ["/business/bank/suggestions?status=pending", "/business/bank/unmatched?period_start=2026-10-01&period_end=2026-10-31"]);
    calls.length = 0;
    await source.decide({ kind: "igualar", movementId: "a", suggestionId: "s 1" }, "key-1");
    await source.decide({ kind: "rechazar", movementId: "a", suggestionId: "s2" }, "key-2");
    assert.deepEqual(calls.map((call) => [call.path, call.init?.method, new Headers(call.init?.headers).get("Idempotency-Key")]), [
      ["/business/bank/suggestions/s%201/confirm", "POST", "key-1"],
      ["/business/bank/suggestions/s2/decline", "POST", "key-2"],
    ]);
  });

  test("the live source offers only what the server serves, and no Deshacer", async () => {
    const source = createBankTransaccionesSource(async <T,>() => ({}) as T);
    assert.equal(source.supports("igualar"), true);
    assert.equal(source.supports("rechazar"), true);
    assert.equal(source.supports("sin_comprobante"), false);
    assert.equal(source.supports("desigualar"), false);
    assert.equal(source.undo, undefined);
    await assert.rejects(source.decide({ kind: "sin_comprobante", movementId: "a", reason: "cargo_banco" }, "k"));
  });
});

describe("transacciones view model", () => {
  test("Por igualar holds three groups in order; the suggestions run most confident first", async () => {
    const { movements } = await createSampleTransaccionesSource().load(OCTOBER);
    const sections = segmentSections(movements, "por_igualar");
    assert.deepEqual(sections.map((section) => section.group), ["sugerencias", "falta_comprobante", "sin_movimiento"]);
    assert.deepEqual(suggestionRun(movements).map((row) => row.counterparty), ["Ferretería La Esquina", "Repuestos Duarte", "Servicio eléctrico, contrato 4471"]);
    const falta = sections[1].rows.map((row) => row.match.state);
    assert.ok(falta.every((state) => state === "falta_comprobante" || state === "igualada_en_parte"));
    assert.equal(defaultSegment(movements), "por_igualar");
  });

  test("Igualadas holds igualadas and no lleva comprobante; Todas holds every row newest first", async () => {
    const { movements } = await createSampleTransaccionesSource().load(OCTOBER);
    const [igualadas] = segmentSections(movements, "igualadas");
    assert.ok(igualadas.rows.every((row) => row.match.state === "igualada" || row.match.state === "no_lleva"));
    const [todas] = segmentSections(movements, "todas");
    assert.equal(todas.rows.length, movements.length);
    const days = todas.rows.map((row) => row.occurredOn);
    assert.deepEqual(days, [...days].sort().reverse());
  });

  test("an empty list opens on Todas", () => {
    assert.equal(defaultSegment([]), "todas");
  });

  test("the Monto header names pesos when any row is in pesos, and totals list the header currency first", async () => {
    const { movements } = await createSampleTransaccionesSource().load(OCTOBER);
    assert.equal(headerCurrency(movements), "DOP");
    const usd: Movement[] = movements.filter((row) => row.money.currency === "USD");
    assert.equal(headerCurrency(usd), "USD");
    assert.deepEqual(inHeaderOrder([{ amount: "24.00", currency: "USD" }, { amount: "1.00", currency: "DOP" }], "DOP").map((money) => money.currency), ["DOP", "USD"]);
  });

  test("a row offers what its state allows and the source serves", async () => {
    const sample = createSampleTransaccionesSource();
    const { movements } = await sample.load(OCTOBER);
    const byId = new Map(movements.map((row) => [row.id, row]));
    assert.deepEqual(rowActions(byId.get("mv-ferreteria")!, sample), ["igualar", "rechazar", "sin_comprobante"]);
    assert.deepEqual(rowActions(byId.get("mv-colmado")!, sample), ["sin_comprobante"]);
    assert.deepEqual(rowActions(byId.get("mv-ferreteria")!, createBankTransaccionesSource(async <T,>() => ({}) as T)), ["igualar", "rechazar"]);
    assert.deepEqual(rowActions(byId.get("doc-taller")!, sample), []);
  });
});

describe("sample source", () => {
  test("the sample server owns the totals: exact, one per currency, and the counts move with a decision", async () => {
    const sample = createSampleTransaccionesSource();
    const before = await sample.load(OCTOBER);
    assert.deepEqual(before.totals.porIgualar?.count, 8);
    assert.deepEqual(before.totals.igualadas, { count: 13, of: 20 });
    assert.deepEqual(before.totals.entradas, [{ currency: "DOP", amount: "90580.68" }]);
    assert.deepEqual(before.totals.salidas, [{ currency: "DOP", amount: "64311.43" }, { currency: "USD", amount: "24.00" }]);
    await sample.decide({ kind: "igualar", movementId: "mv-ferreteria", suggestionId: "sg-ferreteria" }, "k1");
    const after = await sample.load(OCTOBER);
    assert.equal(after.totals.porIgualar?.count, 7);
    assert.deepEqual(after.totals.igualadas, { count: 14, of: 20 });
    assert.equal(after.movements.find((row) => row.id === "mv-ferreteria")?.match.state, "igualada");
  });

  test("Deshacer puts the row back where it stood", async () => {
    const sample = createSampleTransaccionesSource();
    await sample.load(OCTOBER);
    const decision = { kind: "sin_comprobante" as const, movementId: "mv-colmado", reason: "compra_informal" as const };
    await sample.decide(decision, "k1");
    assert.deepEqual((await sample.load(OCTOBER)).movements.find((row) => row.id === "mv-colmado")?.match, { state: "no_lleva", reason: "compra_informal" });
    await sample.undo!(decision);
    assert.equal((await sample.load(OCTOBER)).movements.find((row) => row.id === "mv-colmado")?.match.state, "falta_comprobante");
  });

  test("a pair that is no longer offered is refused", async () => {
    const sample = createSampleTransaccionesSource();
    await sample.load(OCTOBER);
    await assert.rejects(sample.decide({ kind: "igualar", movementId: "mv-colmado", suggestionId: "sg-ferreteria" }, "k"));
  });
});

describe("table density", () => {
  const original = (globalThis as { window?: unknown }).window;
  afterEach(() => {
    (globalThis as { window?: unknown }).window = original;
    resetTableDensity();
  });
  const withStorage = (storage: Partial<Storage>) => {
    (globalThis as { window?: unknown }).window = { localStorage: storage };
  };

  test("Normal is the default for everyone", () => {
    assert.equal(DEFAULT_DENSITY, "normal");
    withStorage({ getItem: () => null, setItem: () => undefined });
    assert.equal(densityPreference.read(), "normal");
  });

  test("the browser remembers the choice, and an unknown value reads as Normal", () => {
    const saved = new Map<string, string>();
    withStorage({ getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, value: string) => void saved.set(key, value) });
    densityPreference.write("compacto");
    assert.equal(densityPreference.read(), "compacto");
    saved.set("cuadrao:table_density", "gigante");
    assert.equal(densityPreference.read(), "normal");
  });

  test("storage that throws reads as Normal and a write never throws", () => {
    withStorage({ getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
    assert.equal(densityPreference.read(), "normal");
    assert.doesNotThrow(() => densityPreference.write("amplio"));
  });
});
