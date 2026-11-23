import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { Window } from "happy-dom";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import ReceiptDocumentType from "@/components/business-app/ReceiptDocumentType";
import ReceiptRecordFacts from "@/components/business-app/ReceiptRecordFacts";
import type { RowEdit } from "@/components/business-app/dossier/DossierParts";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { blockedFields, factStanding, fiscalFactRows, recordFactRows } from "@/components/business-app/receipt-fact-rows";
import type { BusinessDossier, BusinessFact, ListoGap } from "@/lib/business-dossier";
import { dossierProblems } from "@/components/business-app/dossier-attention";

const known = (origin: BusinessFact<string>["origin"] & string, verified = false): BusinessFact<string> => ({ state: "known", value: "x", origin, verified, source_ids: [] });
const unknown: BusinessFact<string> = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
const ownerUnknown: BusinessFact<string> = { state: "owner_does_not_know", value: null, origin: "owner_stated", verified: false, source_ids: [] };

async function i18n(lng: "es-419" | "en") {
  const instance = i18next.createInstance();
  await instance.init({ lng, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return instance;
}

async function fixture() {
  const fixtures = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  return fixtures.dossier(dossierFixtureIds.unknownAmount);
}

/** The General tab's rows as the panel mounts them: Compra or Venta as the type row, the problems from `listo_gaps`. */
async function render(dossier: BusinessDossier, lng: "es-419" | "en" = "es-419", confirmable = true, gaps: ListoGap[] = [], review = false) {
  const instance = await i18n(lng);
  const confirmed: string[] = [];
  const edit = (key: string): RowEdit => ({ open: false, saving: false, locked: false, onOpen: confirmable ? () => { confirmed.push(key); } : undefined, onSave: () => undefined, onCancel: () => undefined, editor: null });
  const problems = dossierProblems({ ...dossier, listo_gaps: gaps }, instance.t.bind(instance));
  const typeRow = dossier.document_type ? <ReceiptDocumentType dossier={dossier} edit={review ? edit("document_type") : undefined} /> : undefined;
  const html = renderToStaticMarkup(
    <I18nextProvider i18n={instance}>
      <ReceiptRecordFacts dossier={dossier} accounts={[]} problems={problems} typeRow={typeRow} review={review ? { noReceipt: { busy: false, note: null }, currency: { note: null }, onEdit: confirmable ? (key) => { confirmed.push(key); } : undefined, edit, note: () => null } : undefined} />
    </I18nextProvider>,
  );
  const page = new Window().document;
  page.body.innerHTML = html;
  const row = (fact: string) => page.querySelector(`li[data-fact="${fact}"]`);
  const facts = () => [...page.querySelectorAll("[data-fact]")].map((element) => element.getAttribute("data-fact"));
  return { html, page, row, facts, confirmed };
}

describe("where each fact stands", () => {
  test("every origin has its own standing; an origin the page does not know falls to a safe 'not verified'", () => {
    assert.equal(factStanding(known("extracted", true)), "verified");
    assert.equal(factStanding(known("owner_stated")), "person");
    assert.equal(factStanding(known("member_set")), "person");
    assert.equal(factStanding(known("matched")), "linked");
    assert.equal(factStanding(known("qr_decoded")), "qr");
    assert.equal(factStanding(known("extracted")), "suggestion");
    assert.equal(factStanding(known("default")), "default");
    assert.equal(factStanding({ ...known("extracted"), origin: "something_new" as never }), "unverified");
    assert.equal(factStanding(unknown), "empty");
    assert.equal(factStanding(ownerUnknown), "owner_unknown");
  });

  test("rows lead with missing data, then preserve the standing order; blockers and open questions mark their fields", () => {
    const dossier = {
      facts: { kind: known("member_set"), counterparty: known("extracted"), occurred_on: known("qr_decoded"), amount: known("extracted"), currency: known("default"), category_id: unknown, funding: unknown, business_share: known("owner_stated", true), receipt_state: ownerUnknown, fiscal: null },
      blockers: [{ code: "missing_fields", field: "amount" }, { code: "unknown_funding", field: "funding" }, { code: "unsupported_kind", field: null }],
      questions: [{ id: "q1", draft_id: "d", field: "receipt_state", asked_of: "owner", channel: "web", state: "open", prompt: "", allowed_answers: [], answer_source_id: null }],
    } as unknown as BusinessDossier;
    const rows = recordFactRows(dossier);
    assert.deepEqual(rows.map((row) => `${row.key}:${row.standing}${row.blocked ? ":blocked" : ""}${row.asked ? ":asked" : ""}`), [
      "category_id:empty",
      "funding:empty:blocked",
      "business_share:verified",
      "kind:person",
      "occurred_on:qr",
      "counterparty:suggestion",
      "amount:suggestion:blocked",
      "currency:default",
      "receipt_state:owner_unknown:asked",
    ]);
    // A blocker with no field is the attention strip's alone.
    assert.deepEqual([...blockedFields(dossier)].sort(), ["amount", "funding"]);
  });
});

describe("the form marks the rows the server's listo gaps name; blockers alone mark nothing", () => {
  test("all known and no gaps: no row carries a warning", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, amount: known("owner_stated") }, blockers: [], questions: [] } as BusinessDossier;
    const { page, html } = await render(dossier);
    assert.equal(page.querySelector('[data-status="warn"]'), null);
    assert.equal(page.querySelector('[data-attention="true"]'), null);
    assert.ok(!html.includes("Falta"));
  });

  test("blockers with no gap leave every row quiet: no warning, no decision line, and an empty field reads Sin dato", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, amount: unknown, funding: unknown, category_id: unknown },
      blockers: [{ code: "missing_fields", field: "amount" }, { code: "unknown_funding", field: "funding" }],
      questions: [],
    } as BusinessDossier;
    const { page, row, html } = await render(dossier);
    assert.ok(row("funding"), "the server waits on funding, so its row shows");
    assert.equal(page.querySelector('[data-status="warn"]'), null);
    assert.equal(page.querySelector('[data-attention="true"]'), null);
    assert.ok(!html.includes("Necesita una decisión"));
    for (const fact of ["amount", "funding"]) {
      const value = row(fact)?.querySelector("[data-row-value]");
      assert.equal(value?.getAttribute("data-empty"), "true", fact);
      assert.equal(value?.textContent, "Sin dato", fact);
    }
    assert.equal(row("category_id"), null, "a Business record shows no ledger category row; its 606 tipo de gasto is the one classification");
    assert.ok(!html.includes("Desconocido"));
  });

  test("a gap marks its row with the gap's words, and a read value nobody confirmed stays quiet", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, counterparty: known("extracted"), amount: unknown }, blockers: [{ code: "missing_fields", field: "amount" }], questions: [] } as BusinessDossier;
    const { row, page } = await render(dossier, "es-419", true, ["missing_amount"], true);
    assert.equal(row("amount")?.getAttribute("data-attention"), "true");
    const status = page.querySelector('[data-testid="row-status-amount"]');
    assert.equal(status?.getAttribute("data-status"), "warn");
    assert.equal(status?.getAttribute("aria-label"), "Escribe el total del documento.");
    assert.equal(row("counterparty")?.getAttribute("data-attention"), null);
    assert.equal(page.querySelector('[data-testid="row-status-counterparty"]'), null);
    assert.equal(page.querySelectorAll('[data-status="warn"]').length, 1);
  });

  test("NCF or e-CF: a fiscal receipt with one of them never counts the other as missing", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, amount: known("owner_stated"), fiscal: { rnc: known("qr_decoded"), ncf: unknown, ecf: { ...known("owner_stated"), value: "E310000000001" }, itbis: unknown } },
      // The server's reading of the same facts: an e-CF is known.
      fiscal_value: "ecf",
      blockers: [],
      questions: [],
    } as unknown as BusinessDossier;
    const rows = fiscalFactRows(dossier.facts);
    assert.deepEqual(rows.map((row) => `${row.key}:${row.standing}`), ["ecf:person", "rnc:qr", "ncf:empty", "itbis:empty"]);
    const { row, html } = await render(dossier);
    assert.equal(row("ncf"), null);
    assert.equal(row("ecf"), null);
    const number = row("fiscal_number");
    assert.equal(number?.firstElementChild?.textContent, "e-CF");
    assert.equal(number?.querySelector("[data-row-value]")?.textContent, "E310000000001");
    assert.equal(number?.querySelector("[data-row-value]")?.getAttribute("data-empty"), null);
    assert.equal(number?.querySelector('[data-status="warn"]'), null);
    assert.ok(!html.includes("Falta") && !html.includes("Faltan"));
  });

  test("a blocked field that has a value never offers Confirmar, and its blocker alone marks nothing", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, amount: known("extracted"), funding: ownerUnknown, currency: known("owner_stated") },
      blockers: [{ code: "invalid_amount", field: "amount" }, { code: "unknown_funding", field: "funding" }, { code: "currency_mismatch", field: "currency" }],
      questions: [],
    } as unknown as BusinessDossier;
    const { html, page, row } = await render(dossier);
    assert.ok(!html.includes("Falta"));
    // Confirming the value a blocker refuses cannot succeed, so the blocked suggestion offers no Confirmar.
    assert.ok(!html.includes("confirm-amount"));
    assert.equal(row("funding")?.querySelector("[data-row-value]")?.textContent, "El dueño no sabe");
    assert.equal(page.querySelector('[data-testid="montos-currency"]')?.getAttribute("data-fact"), "currency", "currency belongs to the Montos header");
    assert.equal(row("currency"), null);
    assert.equal(page.querySelector('[data-attention="true"]'), null);
    assert.ok(!html.includes("Necesita una decisión"));
  });
});

describe("the record facts on the review page", () => {
  test("a read value stays quiet: no tag for the receipt, the message, the QR or a link", async () => {
    const base = await fixture();
    const dossier = {
      ...base,
      facts: { ...base.facts, counterparty: known("extracted"), occurred_on: known("qr_decoded"), category_id: known("matched"), amount: unknown, fiscal: { rnc: known("qr_decoded"), ncf: unknown, ecf: known("extracted"), itbis: unknown } },
      // The server's reading of the same facts: an e-CF is known.
      fiscal_value: "ecf",
      blockers: [{ code: "missing_fields", field: "amount" }],
      questions: [],
    } as unknown as BusinessDossier;
    const { html, page, facts } = await render(dossier);
    assert.equal(page.querySelector("[data-origin]"), null, "a read value carries no origin tag");
    assert.ok(!/· (del recibo|del mensaje|del código QR|vinculada a la fuente|del dueño)/.test(html));
    assert.ok(!html.includes('data-testid="receipt-read-banner"'));
    assert.ok(!html.includes("Leído de la fuente · sugerencia sin verificar"));
    assert.ok(!html.includes("confirm-counterparty") && !html.includes("lucide-sparkles"));
    for (const quiet of ["counterparty", "occurred_on", "fiscal_number"]) assert.equal(page.querySelector(`[data-testid="row-status-${quiet}"]`), null, quiet);
    for (const chip of ["Sin verificar", "lucide-circle-dashed"]) assert.ok(!html.includes(chip), chip);
    assert.ok(!html.includes("confirm-ecf"));
    const order = facts();
    assert.ok(!order.includes("category_id"));
    assert.ok(order.indexOf("counterparty") < order.indexOf("occurred_on"));
    assert.ok(order.indexOf("amount") > order.indexOf("counterparty"));
    assert.ok(!html.includes("Desconocido"), "the unknown amount is an empty field");
    assert.ok(!html.includes("verificada") && !html.includes("—"));
  });

  test("an open draft: the read facts in card order, each with an edit control, ITBIS included, and nothing the owner no longer answers", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, fiscal: { rnc: { ...known("qr_decoded"), value: "131999888" }, ncf: known("extracted"), ecf: unknown, itbis: known("extracted") } }, fiscal_value: "ncf", blockers: [], questions: [] } as unknown as BusinessDossier;
    const { html, facts } = await render(dossier, "es-419", true, [], true);
    assert.deepEqual(facts(), ["rnc", "counterparty", "fiscal_number", "occurred_on", "currency", "net_amount", "itbis", "amount"]);
    for (const row of ["Emisor", "Fecha", "Subtotal", "Total", "RNC", "NCF", "ITBIS"]) assert.ok(html.includes(`Editar detalles · ${row}`), row);
    assert.ok(!html.includes("Editar detalles · Tipo"), "a clean purchase has no Compra/Venta row");
  });

  test("an open draft brings a row back only while the server waits on it; 'Parte del negocio' stays off even then", async () => {
    const base = await fixture();
    const blocked = { ...base, facts: { ...base.facts, kind: unknown, funding: unknown }, blockers: [{ code: "fact_required", field: "kind" }, { code: "fact_required", field: "funding" }], questions: [] } as unknown as BusinessDossier;
    const { row } = await render(blocked, "es-419", true, [], true);
    assert.ok(row("kind") && row("funding"));
    const settled = { ...base, facts: { ...base.facts, funding: { state: "known", value: { kind: "owner_funds" }, origin: "owner_stated", verified: false, source_ids: [] } }, blockers: [], questions: [] } as unknown as BusinessDossier;
    const quiet = await render(settled, "es-419", true, [], true);
    assert.equal(quiet.row("kind"), null, "Compra or Venta already says the kind");
    assert.equal(quiet.row("funding"), null, "nobody waits on funding");
    const asked = { ...blocked, blockers: [], questions: [{ id: "q", draft_id: base.draft_id, field: "business_share", asked_of: "owner", channel: "web", state: "open", prompt: "¿Qué parte?", allowed_answers: ["known"], answer_source_id: null }] } as unknown as BusinessDossier;
    const partial = { ...blocked, facts: { ...blocked.facts, business_share: { state: "known", value: { kind: "partial", amount: "100.00" }, origin: "owner_stated", verified: false, source_ids: [] } }, blockers: [{ code: "business_allocation_unsupported", field: "business_share" }] } as unknown as BusinessDossier;
    for (const waiting of [blocked, asked, partial]) {
      const shown = await render(waiting, "es-419", true, [], true);
      assert.ok(!shown.row("business_share") && !shown.html.includes("Parte del negocio"));
    }
  });

  test("a recorded receipt shows no 'Parte del negocio' row, whatever its share", async () => {
    const base = await fixture();
    for (const share of [{ kind: "all" }, { kind: "none" }, { kind: "partial", amount: "100.00" }]) {
      const dossier = { ...base, facts: { ...base.facts, funding: { state: "known", value: { kind: "owner_funds" }, origin: "owner_stated", verified: false, source_ids: [] }, business_share: { state: "known", value: share, origin: "owner_stated", verified: false, source_ids: [] } }, blockers: [], questions: [] } as unknown as BusinessDossier;
      const { html, row } = await render(dossier);
      assert.ok(!row("business_share") && !html.includes("Parte del negocio"), share.kind);
      for (const value of ["Todo para el negocio", "Solo personal", "Una parte para el negocio", "100.00"]) assert.ok(!html.includes(value), `${share.kind}: ${value}`);
    }
  });

  test("a read-only reader of an open draft sees the same rows with no edit control", async () => {
    const { html, row, page } = await render(await fixture(), "es-419", false, [], true);
    assert.ok(row("itbis"));
    assert.ok(!html.includes("Editar detalles"));
    assert.equal(page.querySelector("button[data-row-value]"), null);
  });

  test("an RNC nobody knows reads Sin dato, never a number", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, fiscal: { rnc: unknown, ncf: known("extracted"), ecf: unknown, itbis: unknown } }, fiscal_value: "ncf", fiscal_known: true } as unknown as BusinessDossier;
    const { html, row } = await render(dossier);
    const value = row("rnc")?.querySelector("[data-row-value]");
    assert.equal(value?.textContent, "Sin dato");
    assert.equal(value?.getAttribute("data-empty"), "true");
    assert.ok(!/0{9}/.test(html));
    const english = await render(dossier, "en", false);
    assert.equal(english.row("rnc")?.querySelector("[data-row-value]")?.textContent, "No value");
  });

  test("no banner when nothing read from the source waits for a person", async () => {
    const base = await fixture();
    const { html } = await render({ ...base, facts: { ...base.facts, counterparty: known("owner_stated") } } as BusinessDossier);
    assert.ok(!html.includes('data-testid="receipt-read-banner"'));
  });

  test("a field the owner does not know shows while a question on it is open, with no decision line", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, funding: ownerUnknown }, blockers: [], questions: [{ id: "q", draft_id: base.draft_id, field: "funding", asked_of: "accountant", channel: "web", state: "open", prompt: "¿Cómo se pagó?", allowed_answers: ["known"], answer_source_id: null }] } as unknown as BusinessDossier;
    const { html, row } = await render(dossier);
    assert.equal(row("funding")?.querySelector("[data-row-value]")?.textContent, "El dueño no sabe");
    assert.ok(!html.includes("Necesita una decisión"));
  });

  test("a row is marked only when the read is in doubt; a reviewer's change carries no 'del revisor' tag", async () => {
    const base = await fixture();
    const reviewed = { ...known("member_set"), value: "Ferretería Norte" };
    const dossier = { ...base, facts: { ...base.facts, counterparty: reviewed, fiscal: { rnc: unknown, ncf: { ...known("extracted"), value: "B01" }, ecf: unknown, itbis: { ...known("extracted"), value: "10.00" } } }, fiscal_value: "ncf", review_flags: [{ code: "ncf_malformed", field: "ncf", confirm: true }], ecf_checks: { encf: null, tipo_ecf: null, checked_at: "2026-10-10T14:25:00Z", checks: [{ name: "read_matches_xml", state: "failed", code: null, detail: { itbis: "read=10 xml=11" } }] } } as unknown as BusinessDossier;
    const reviewing = await render(dossier, "es-419", true, [], true);
    const doubted = [...reviewing.page.querySelectorAll('[data-status="warn"]')].map((status) => [status.getAttribute("data-testid"), status.getAttribute("aria-label")]);
    assert.deepEqual(doubted, [["row-status-fiscal_number", "revisar"], ["row-status-itbis", "revisar"]], "the flagged NCF and the disputed ITBIS say revisar in their status slot");
    for (const view of [reviewing, await render(dossier)]) {
      assert.equal(view.row("counterparty")?.querySelector("[data-row-value]")?.textContent, "Ferretería Norte");
      assert.equal(view.page.querySelector('[data-testid="row-status-counterparty"]'), null);
      assert.ok(!view.html.includes("del revisor") && !view.html.includes('data-origin="member_set"'));
    }
  });

  test("a reader who cannot prepare sees no Confirmar button; English words follow", async () => {
    const base = await fixture();
    const dossier = { ...base, facts: { ...base.facts, counterparty: known("extracted") } } as BusinessDossier;
    const { html, row } = await render(dossier, "en", false);
    assert.ok(!/· (from the receipt|from the message)/.test(html));
    assert.ok(!html.includes("Read from the source · suggestion, not verified"));
    assert.ok(!html.includes("confirm-counterparty"));
    assert.equal(row("counterparty")?.querySelector("[data-row-value]")?.textContent, "x");
    assert.equal(row("amount")?.firstElementChild?.textContent, "Total");
  });
});

for (const language of ["es-419", "en"] as const) {
  for (const documentType of ["recibo", "venta"] as const) {
    for (const reviewing of [false, true]) {
      test(`${language} ${documentType} payment wording while reviewing=${reviewing}`, async () => {
        const base = await fixture();
        const dossier = { ...base, document_type: documentType, blockers: [{ code: "unknown_funding", field: "funding" }] } as BusinessDossier;
        const { row } = await render(dossier, language, true, [], reviewing);
        const sale = documentType === "venta";
        const funding = language === "es-419" ? (sale ? "Forma de cobro" : "Cómo se pagó") : (sale ? "Collection method" : "How it was paid");
        assert.equal(row("funding")?.firstElementChild?.textContent, funding);
      });
    }
  }
}

describe("the NCF and the e-CF are one fiscal number, on a recorded receipt and in review", () => {
  const read = (value: string): BusinessFact<string> => ({ ...known("extracted"), value });
  const receipts = [
    { carries: "ncf", label: "NCF", number: "B0100000123", fiscal: { rnc: unknown, ncf: read("B0100000123"), ecf: unknown, itbis: unknown } },
    { carries: "ecf", label: "e-CF", number: "E310000000777", fiscal: { rnc: unknown, ncf: unknown, ecf: read("E310000000777"), itbis: unknown } },
  ] as const;

  for (const { carries, label, number, fiscal } of receipts) {
    test(`a receipt with an ${carries} shows one ${label} row with its number, the same row in both views`, async () => {
      const base = await fixture();
      const dossier = { ...base, facts: { ...base.facts, fiscal }, fiscal_known: true, fiscal_value: carries, blockers: [], questions: [] } as unknown as BusinessDossier;
      const recorded = await render(dossier);
      const reviewing = await render(dossier, "es-419", true, [], true);
      for (const view of [recorded, reviewing]) {
        assert.deepEqual(view.facts().filter((fact) => fact === "ncf" || fact === "ecf" || fact === "fiscal_number"), ["fiscal_number"]);
        const row = view.row("fiscal_number");
        assert.equal(row?.firstElementChild?.textContent, label);
        assert.equal(row?.querySelector("[data-row-value]")?.textContent, number);
        assert.equal(row?.querySelector("[data-status]"), null);
      }
      assert.ok(!recorded.page.querySelector('[data-testid="receipt-facts-comprobante"]')?.textContent?.includes("El dueño no sabe"));
    });
  }
});
