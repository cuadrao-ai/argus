import type { BusinessAccount, BusinessApprovalOptions, BusinessCapture, BusinessCaptureInput, ReceiptDetail } from "@/lib/business-api";
import { LISTO_GAPS, factsRevision, type BusinessActor, type BusinessApprovalAction, type BusinessDossier, type BusinessDraftRevision, type BusinessFact, type BusinessFactPatch, type BusinessFacts, type BusinessMontosReview, type EditableDossierField, type ListoGap, type RefundCandidate } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiField, DgiiFields, DgiiReview, PurchaseChoice, SuggestedField, SuggestionSources } from "@/lib/business-dgii";
import { noteGroup } from "./fixture-server-rules";

const SUGGESTED: readonly SuggestedField[] = ["category", "payment_method"];
/** A 606 answer still to give: none saved, or a tipo de gasto nobody confirmed. */
const blankAnswer = (dgii: DgiiDeclaration | null | undefined, field: SuggestedField) => !dgii?.[field] || (field === "category" && dgii.category_suggested === true);
/** A person's write keeps a suggestion's source only beside an answer it left as it was. */
function keptSources(before: DgiiDeclaration | null | undefined, after: DgiiDeclaration): DgiiDeclaration {
  const kept: SuggestionSources = Object.fromEntries(SUGGESTED.flatMap((field) => before?.suggestion_sources?.[field] && after[field] === before[field] ? [[field, before.suggestion_sources[field]]] : []));
  const next: DgiiDeclaration = { ...after };
  delete next.suggestion_sources;
  return Object.keys(kept).length ? { ...next, suggestion_sources: kept } : next;
}

type SampleGap = { reason: ListoGap; confirmable: boolean };
const sampleGap = (reason: ListoGap, confirmable: boolean): SampleGap => ({ reason, confirmable });
const BLOCKED_FIELD_GAP: Partial<Record<string, SampleGap>> = {
  counterparty: sampleGap("missing_merchant", true),
  occurred_on: sampleGap("missing_date", false),
  amount: sampleGap("missing_amount", false),
  currency: sampleGap("missing_currency", false),
};

/**
 * `bandeja_group.py` in short, over what a sample record already states: its
 * duplicate candidates, its blockers, its RNC and its review flags. A sample
 * with `seeded` gaps (a receipt's draft, from its row) keeps those while open.
 * The standing is worked out on every read and never stored, so a write clears
 * what it fixed.
 */
function sampleStanding(draft: BusinessDossier, seeded?: readonly SampleGap[]): Pick<BusinessDossier, "bandeja_group" | "listo_gaps" | "confirmable"> {
  if (draft.deleted) return { bandeja_group: { group: "eliminados", reason: null, label: null }, listo_gaps: [], confirmable: [] };
  if (draft.review_state === "accepted") return { bandeja_group: { group: null, reason: null, label: "accepted" }, listo_gaps: [], confirmable: [] };
  if (draft.review_state === "dismissed") return { bandeja_group: { group: null, reason: null, label: null }, listo_gaps: [], confirmable: [] };
  if (draft.review_state === "accepting") return { bandeja_group: { group: "listo", reason: null, label: "ready" }, listo_gaps: [], confirmable: [] };
  const flags = draft.review_flags ?? [];
  const rnc = draft.facts.fiscal?.rnc;
  const digits = rnc?.state === "known" ? rnc.value.replace(/\D/g, "") : "";
  const gaps = seeded ?? [
    ...(draft.duplicate_candidates?.length || draft.blockers.some((blocker) => blocker.code === "possible_duplicate") ? [sampleGap("duplicate", true)] : []),
    ...draft.blockers.flatMap((blocker) => BLOCKED_FIELD_GAP[blocker.field ?? ""] ?? []),
    ...(draft.facts.fiscal && !digits ? [sampleGap("missing_rnc", true)] : []),
    ...(digits && (flags.some((flag) => flag.code === "rnc_check_digit") || (digits.length !== 9 && digits.length !== 11)) ? [sampleGap("invalid_rnc", true)] : []),
    ...(flags.some((flag) => flag.code === "ncf_malformed") ? [sampleGap("invalid_ncf", true)] : []),
    ...(flags.length ? [sampleGap("review_flag", true)] : []),
    ...(draft.blockers.some((blocker) => blocker.code !== "possible_duplicate" && !BLOCKED_FIELD_GAP[blocker.field ?? ""]) ? [sampleGap("blocked", false)] : []),
  ];
  return gaps.length
    ? { bandeja_group: { group: "attention", reason: gaps[0].reason, label: "needs_attention" }, listo_gaps: gaps.map((gap) => gap.reason), confirmable: gaps.filter((gap) => gap.confirmable).map((gap) => gap.reason) }
    : { bandeja_group: { group: "listo", reason: null, label: "ready" }, listo_gaps: [], confirmable: [] };
}

const SERVICE_EXPENSE_TYPES = new Set(["02", "03", "07", "11"]);
/** Forma de pago codes that pay at the purchase: Fecha de pago is the receipt's date. */
const PAID_AT_PURCHASE = new Set(["01", "02", "03", "07"]);
const PAYMENT_FORM_BY_ACCOUNT_TYPE: Partial<Record<string, string>> = { cash: "01", checking: "02", savings: "02", credit_card: "03" };
/** Every field the server dumps for a purchase declaration nobody answered, in its order. */
const BLANK_606: DgiiDeclaration = {
  id_type: null, modified_ncf: null, selective_tax: null, other_taxes: null, legal_tip: null, form: "606", category: null, category_suggested: false,
  paid_on: null, services_amount: null, goods_amount: null, itbis_withheld: null, itbis_proportionality: null, itbis_cost: null, itbis_perceived: null,
  income_withholding_type: null, income_withheld: null, income_perceived: null, payment_method: null, actual_refund: false, purchase_activity_id: null,
};
type LinkSource = NonNullable<BusinessDossier["inheritance"]>[string]["field"];
/** `INHERITANCE` for a purchase, in the server's order: each 606 field and the source it follows. */
const PURCHASE_LINKS: readonly (readonly [string, LinkSource])[] = [["goods_amount", "net_amount"], ["id_type", "rnc"], ["itbis", "itbis"], ["legal_tip", "legal_tip"], ["paid_on", "occurred_on"], ["services_amount", "net_amount"]];
const AMOUNT_SIDES = ["services_amount", "goods_amount"];
const MONEY_SOURCES = new Set<LinkSource>(["net_amount", "itbis", "legal_tip"]);
const cents = (value: string | null | undefined) => Math.round(Number(value ?? 0) * 100);
const money = (value: number) => (value / 100).toFixed(2);
const text = (value: DgiiDeclaration[string] | undefined) => typeof value === "string" ? value : null;
const heldValue = <T>(fact: BusinessFact<T> | null | undefined) => fact?.state === "known" ? fact.value : null;
const idTypeOf = (facts: BusinessFacts) => { const digits = heldValue(facts.fiscal?.rnc)?.replace(/\D/g, "").length; return digits === 9 ? "1" : digits === 11 ? "2" : null; };
const sameLinked = (source: LinkSource, a: string | null, b: string | null) => a === null || b === null ? a === b : MONEY_SOURCES.has(source) ? cents(a) === cents(b) : a === b;

type SampleDeclared = Required<Pick<BusinessDossier, "net_amount" | "inheritance" | "dgii_calculated" | "review_flags">> & Pick<BusinessDossier, "dgii">;

/**
 * The 606 a sample purchase shows, in short: `written_from` and
 * `inheritance_state` (amount_inheritance.py), `net_amount` and
 * `declaration_from_facts` (purchase_review.py), `purchase_calculated`
 * (dgii_validation.py) and the Montos check of review_flags.py. Worked out on
 * every read from the facts, the declaration a person saved, the fields that
 * person holds `apart` and the answers the server suggests, so a write moves
 * every field that follows it. `apart` is undefined for a declaration saved
 * before any link was recorded: a field then follows its source while it is
 * blank or equal to it. `corrected` is given when a revision is saved
 * (`saved_declaration_links`): the sources besides the amounts that it moved,
 * which an approved record follows in that save alone.
 */
function sampleDeclared(draft: BusinessDossier, { sinComprobante = false, apart, suggestions, corrected }: { sinComprobante?: boolean; apart: readonly string[] | undefined; suggestions?: BusinessDossier["declaration_suggestions"]; corrected?: ReadonlySet<LinkSource> }): SampleDeclared {
  const { facts } = draft;
  const saved = draft.dgii?.form === "606" ? draft.dgii : null;
  const itbis = heldValue(facts.fiscal?.itbis);
  const tip = heldValue(facts.legal_tip);
  const total = heldValue(facts.amount);
  const parts = cents(itbis) + cents(tip ?? text(saved?.legal_tip)) + cents(text(saved?.selective_tax)) + cents(text(saved?.other_taxes));
  const stated = facts.net_amount;
  const net: SampleDeclared["net_amount"] = stated?.state === "known" ? { amount: stated.value, source: stated.origin === "extracted" || stated.origin === "qr_decoded" ? "read" : "edited" }
    : total === null ? { amount: null, source: null } : { amount: money(cents(total) - parts), source: "calculated" };
  const difference = total === null || net.amount === null ? 0 : cents(total) - cents(net.amount) - parts;
  // An unknown ITBIS counts as zero and can only close a gap the Total leaves.
  const review_flags: SampleDeclared["review_flags"] = [...(draft.review_flags ?? []).filter((flag) => flag.code !== "amounts_mismatch"), ...(difference < -1 || (itbis !== null && difference > 1) ? [{ code: "amounts_mismatch" as const, field: "amount" as const, confirm: false, difference: money(difference) }] : [])];
  const none = { dgii: draft.dgii, net_amount: net, inheritance: {}, dgii_calculated: null, review_flags };
  if (draft.dgii?.form === "607") return none;

  const rnc = heldValue(facts.fiscal?.rnc);
  const number = heldValue(facts.fiscal?.ecf) ?? heldValue(facts.fiscal?.ncf);
  const idType = idTypeOf(facts);
  const approved = draft.review_state !== "open" && draft.review_state !== "accepting";
  const reviewing = draft.review_state === "open" && facts.kind.value === "expense" && draft.document_type !== "venta" && !sinComprobante;
  const funding = heldValue(facts.funding);
  const account = funding?.kind === "business_account" ? draft.accounts.find((item) => item.id === funding.account_id)?.type : undefined;
  // The 606 does not report a purchase with no RNC, no fiscal number, or a consumer one (B02, E32).
  const built: DgiiDeclaration | null = reviewing && rnc && number && !["02", "32"].includes(number.slice(1, 3)) ? { ...BLANK_606, id_type: idType, payment_method: PAYMENT_FORM_BY_ACCOUNT_TYPE[account ?? ""] ?? null } : null;
  const start: DgiiDeclaration | null = built ? saved ?? { ...built, payment_method: null } : saved;
  if (!start) return none;
  // A suggested Forma de pago stays beside its blank answer, so the account's fills only without one.
  const shown: DgiiDeclaration = built && !start.payment_method && !suggestions?.payment_method ? { ...start, payment_method: built.payment_method } : { ...start };
  // A suggested answer counts as given, so the links show what approving saves.
  const category = text(shown.category) && shown.category_suggested !== true ? text(shown.category) : suggestions?.category?.value ?? null;
  const paidBy = text(shown.payment_method) ?? suggestions?.payment_method?.value ?? null;
  const split = category && net.amount !== null && cents(net.amount) >= 0 ? money(cents(net.amount)) : null;
  const services = category !== null && SERVICE_EXPENSE_TYPES.has(category);
  const expected: Record<string, string | null> = {
    goods_amount: services ? null : split,
    id_type: idType,
    itbis,
    legal_tip: tip,
    paid_on: paidBy && PAID_AT_PURCHASE.has(paidBy) ? heldValue(facts.occurred_on) : null,
    services_amount: services ? split : null,
  };
  const inheritance: SampleDeclared["inheritance"] = {};
  for (const [target, source] of PURCHASE_LINKS) {
    // Tipo de ID and Fecha de pago follow their source while an open draft is reviewed, and in the save that corrects that source.
    if (approved && !MONEY_SOURCES.has(source) && !corrected?.has(source)) continue;
    const current = text(shown[target]);
    const inherited = apart ? !apart.includes(target) : current === null || sameLinked(source, current, expected[target]);
    inheritance[target] = { field: source, value: expected[target], inherited, paired_with: AMOUNT_SIDES.includes(target) ? AMOUNT_SIDES.filter((side) => side !== target) : [] };
    // An approved record shows what its last revision saved; one saved before links were recorded keeps its blank amounts filled.
    if (!inherited || (approved && apart && !corrected)) continue;
    const value = expected[target];
    shown[target] = value !== null && MONEY_SOURCES.has(source) ? cents(value) >= 0 ? money(cents(value)) : null : value;
  }
  if (shown.itbis == null) delete shown.itbis;
  const declaredItbis = text(shown.itbis) ?? (inheritance.itbis.inherited ? itbis : null);
  return {
    dgii: shown, net_amount: net, inheritance, review_flags,
    dgii_calculated: { billed_amount: money(cents(text(shown.services_amount)) + cents(text(shown.goods_amount))), itbis_advance: declaredItbis === null ? null : money(cents(declaredItbis) - cents(text(shown.itbis_cost))) },
  };
}

export const dossierFixtureIds = {
  unknown: "10000000-0000-4000-8000-000000000001",
  ready: "10000000-0000-4000-8000-000000000002",
  readOnly: "10000000-0000-4000-8000-000000000003",
  stale: "10000000-0000-4000-8000-000000000004",
  denied: "10000000-0000-4000-8000-000000000005",
  outcomeUnknown: "10000000-0000-4000-8000-000000000006",
  unknownAmount: "10000000-0000-4000-8000-000000000007",
  income: "10000000-0000-4000-8000-000000000008",
  unprepared: "10000000-0000-4000-8000-000000000009",
  unknownKind: "10000000-0000-4000-8000-000000000010",
  fiscal: "10000000-0000-4000-8000-000000000011",
  proposal: "10000000-0000-4000-8000-000000000012",
  saveUnknown: "10000000-0000-4000-8000-000000000013",
  saveConcurrent: "10000000-0000-4000-8000-000000000014",
  recordedThenMarked: "10000000-0000-4000-8000-000000000015",
  /** The fiscal record with its date missing: something blocks approval. */
  fiscalBlocked: "10000000-0000-4000-8000-000000000016",
  /** The fiscal record with every save refused, so the failed state can be seen. */
  saveRefused: "10000000-0000-4000-8000-000000000017",
  /** The fiscal record with a receipt image as its original. */
  fiscalAttached: "10000000-0000-4000-8000-000000000018",
  /** The fiscal record whose e-CF file does not add up to its total. */
  totalsOff: "10000000-0000-4000-8000-000000000019",
  /** The fiscal record with both owner choices saved, so Historial shows their labels. */
  fiscalDeclared: "10000000-0000-4000-8000-000000000020",
  /** A record with no NCF or e-CF and no answer yet: it can be marked Sin recibo. */
  noNumber: "10000000-0000-4000-8000-000000000021",
  /** The fiscal record with no currency: its amount cannot be shown as money and approval waits for it. */
  noCurrency: "10000000-0000-4000-8000-000000000022",
} as const;

export const EXPENSE_TYPES: Record<string, string> = { "01": "Gastos de personal", "02": "Gastos por trabajos, suministros y servicios", "03": "Arrendamientos", "04": "Gastos de activos fijo", "05": "Gastos de representación", "06": "Otras deducciones admitidas", "07": "Gastos financieros", "08": "Gastos extraordinarios", "09": "Compras y gastos que formarán parte del costo de venta", "10": "Adquisiciones de activos", "11": "Gastos de seguros" };
export const PAYMENT_FORMS: Record<string, string> = { "01": "Efectivo", "02": "Cheques/transferencias/depósito", "03": "Tarjeta crédito/débito", "04": "Compra a crédito", "05": "Permuta", "06": "Nota de crédito", "07": "Mixto" };
const sampleField = (name: string, label: string, kind: DgiiField["kind"] = "money", options: string[] = [], labels: Record<string, string> = {}): DgiiField => ({ name, label, kind, options, labels });
const SAMPLE_DGII_FIELDS: DgiiFields = {
  "606": [
    sampleField("rnc", "RNC o Cédula", "text"), sampleField("id_type", "Tipo Id", "select", ["1", "2"]),
    sampleField("category", "Tipo Bienes y Servicios Comprados", "select", Object.keys(EXPENSE_TYPES).sort(), EXPENSE_TYPES),
    sampleField("ncf", "NCF", "text"), sampleField("modified_ncf", "NCF ó Documento Modificado", "text"), sampleField("paid_on", "Fecha Pago", "date"),
    sampleField("services_amount", "Monto Facturado en Servicios"), sampleField("goods_amount", "Monto Facturado en Bienes"), sampleField("itbis", "ITBIS Facturado"),
    sampleField("itbis_withheld", "ITBIS Retenido"), sampleField("itbis_proportionality", "ITBIS sujeto a Proporcionalidad (Art. 349)"), sampleField("itbis_cost", "ITBIS llevado al Costo"), sampleField("itbis_perceived", "ITBIS percibido en compras"),
    sampleField("income_withholding_type", "Tipo de Retención en ISR", "select", ["01", "02", "03", "04", "05", "06", "07", "08", "09"]), sampleField("income_withheld", "Monto Retención Renta"), sampleField("income_perceived", "ISR Percibido en compras"),
    sampleField("selective_tax", "Impuesto Selectivo al Consumo"), sampleField("other_taxes", "Otros Impuesto/Tasas"), sampleField("legal_tip", "Monto Propina Legal"),
    sampleField("payment_method", "Forma de Pago", "select", Object.keys(PAYMENT_FORMS).sort(), PAYMENT_FORMS),
  ],
  "607": [
    sampleField("rnc", "RNC/Cédula o Pasaporte", "text"), sampleField("id_type", "Tipo Identificación", "select", ["1", "2", "3"]), sampleField("ncf", "Número Comprobante Fiscal", "text"), sampleField("modified_ncf", "Número Comprobante Fiscal Modificado", "text"),
    sampleField("income_type", "Tipo de Ingreso", "select", ["1", "2", "3", "4", "5", "6"]), sampleField("withheld_on", "Fecha de Retención", "date"), sampleField("billed_amount", "Monto Facturado"), sampleField("itbis", "ITBIS Facturado"),
    sampleField("itbis_withheld_by_third_parties", "ITBIS Retenido por Terceros"), sampleField("itbis_perceived", "ITBIS Percibido"), sampleField("income_withheld_by_third_parties", "Retención Renta por Terceros"), sampleField("income_perceived", "ISR Percibido"),
    sampleField("selective_tax", "Impuesto Selectivo al Consumo"), sampleField("other_taxes", "Otros Impuestos/Tasas"), sampleField("legal_tip", "Monto Propina Legal"),
    sampleField("cash", "Efectivo"), sampleField("bank", "Cheque/ Transferencia/ Depósito"), sampleField("card", "Tarjeta Débito/Crédito"), sampleField("credit", "Venta a Crédito"), sampleField("gift", "Bonos o Certificados de Regalo"), sampleField("barter", "Permuta"), sampleField("other_payment", "Otras Formas de Ventas"),
  ],
};
const printedIdentifier = (value: string | null) => value === null ? null : value.trim().replace(/(?<=[0-9])[-\s]+(?=[0-9])/g, "").toUpperCase();

const sourceId = "20000000-0000-4000-8000-000000000001";
const reviewSourceId = "20000000-0000-4000-8000-000000000002";
const actor: BusinessActor = {
  actor_id: "30000000-0000-4000-8000-000000000001",
  actor_kind: "member",
  display_name: "Ana Peña",
  shown_as: "name",
  grant_id: "40000000-0000-4000-8000-000000000001",
  issuer_id: "30000000-0000-4000-8000-000000000002",
  issuer_display_name: "Lucía Mateo",
  issuer_shown_as: "name",
};
const unknown = <T>(): BusinessFact<T> => ({ state: "unknown", value: null, origin: null, verified: false, source_ids: [] });
const known = <T>(value: T): Extract<BusinessFact<T>, { state: "known" }> => ({ state: "known", value, origin: "owner_stated", verified: false, source_ids: [sourceId] });

export function createDossierFixtures(accounts: BusinessAccount[]) {
  const currency: BusinessFacts["currency"] = { state: "known", value: "DOP", origin: "default", verified: false, source_ids: [] };
  const facts: BusinessFacts = {
    kind: known("expense"),
    amount: known("3450.00"),
    currency,
    occurred_on: known("2026-10-09"),
    counterparty: known("Ferretería La Esquina"),
    funding: unknown(),
    business_share: known({ kind: "all" }),
    receipt_state: known("no_receipt"),
    category_id: known("other"),
    fiscal: null,
  };
  const dossiers = new Map<string, BusinessDossier>();
  const seededGaps = new Map<string, readonly SampleGap[]>();
  /** The drafts of the sample's receipts. */
  const receiptDrafts = new Set<string>();
  /** The linked 606 fields a person holds apart from their source, per draft, once the sample recorded them. */
  const heldApart = new Map<string, readonly string[]>();
  for (const [name, id] of Object.entries(dossierFixtureIds)) {
    const ready = name !== "unknown" && name !== "unknownAmount";
    const current: BusinessFacts = { ...facts, category_id: { ...known("other"), origin: "member_set", source_ids: [reviewSourceId] }, funding: ready ? { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "member_set", source_ids: [reviewSourceId] } : unknown(), amount: name === "unknownAmount" ? unknown() : facts.amount, kind: name === "unknownKind" ? unknown() : name === "income" ? known("income") : facts.kind };
    dossiers.set(id, {
      draft_id: id,
      // The server's reading: every sample record has read facts.
      fiscal_known: true,
      space_id: "50000000-0000-4000-8000-000000000001",
      space_name: "Taller Lucía · negocio de muestra",
      accounts,
      version: 2,
      review_state: "open",
      facts: current,
      sources: [{ id: sourceId, kind: "message", channel: "whatsapp", received_at: "2026-10-10T14:20:00Z", text: "Ayer compré pintura y brochas para el taller en Ferretería La Esquina. Fueron 3,450. No tengo recibo." }, { id: reviewSourceId, kind: "web_action", channel: "web", received_at: "2026-10-10T14:25:00Z", text: JSON.stringify({ version: 1, facts: { category_id: { state: "known", value: "other" }, ...(ready ? { funding: { state: "known", value: { kind: "business_account", account_id: accounts[0].id } } } : {}) } }) }],
      questions: ready ? [] : [{ id: "60000000-0000-4000-8000-000000000001", draft_id: id, field: "funding", asked_of: "accountant", channel: "web", state: "open", prompt: "¿Cómo se pagó?", allowed_answers: ["known", "owner_does_not_know"], answer_source_id: null, created_at: "2026-10-10T14:22:00Z" }],
      history: [{ draft_id: id, version: 1, actor: { ...actor, actor_kind: "owner_via_agent", display_name: "Lucía Mateo vía Cuadrao" }, before: null, after: facts, source_ids: [sourceId], turn_key: null, created_at: "2026-10-10T14:21:00Z" }, { draft_id: id, version: 2, actor, before: facts, after: current, source_ids: [reviewSourceId], turn_key: null, created_at: "2026-10-10T14:25:00Z" }],
      capabilities: name === "readOnly" ? ["read"] : ["read", "prepare", "approve"],
      blockers: ready ? name === "unknownKind" ? [{ code: "missing_fields", field: "kind" }] : name === "income" ? [{ code: "unsupported_kind", field: "kind" }] : [] : [{ code: "unknown_funding", field: "funding" }, ...(name === "unknownAmount" ? [{ code: "missing_fields", field: "amount" as const }] : [])],
      approval_available: ready && name !== "readOnly" && name !== "income" && name !== "unknownKind",
      approval_result: null,
    });
  }
  const fiscalDossier = dossiers.get(dossierFixtureIds.fiscal)!;
  const fiscalBefore: BusinessFacts = { ...fiscalDossier.facts, receipt_state: known("fiscal_receipt"), fiscal: { rnc: unknown(), ncf: known("B0100000098"), ecf: unknown(), itbis: known("100.01") } };
  // The e-CF fixture carries a DGII QR: the RNC came from it; the merchant is the read's suggestion, not yet confirmed.
  const fiscalAfter: BusinessFacts = { ...fiscalBefore, counterparty: { ...known("Ferretería La Esquina"), origin: "extracted" }, fiscal: { rnc: { ...known("131999888"), origin: "qr_decoded" }, ncf: known("B0100000099"), ecf: { state: "owner_does_not_know", value: null, origin: "owner_stated", verified: false, source_ids: [sourceId] }, itbis: { state: "known", value: "526.27", origin: "matched", verified: true, source_ids: [sourceId] } } };
  const fiscalChecks: BusinessDossier["ecf_checks"] = { encf: "E310000000777", tipo_ecf: "31", checked_at: "2026-10-10T14:25:00Z", checks: [
    { name: "signature_integrity", state: "verified", code: null, detail: {} },
    { name: "totals_arithmetic", state: "verified", code: null, detail: { monto_total: "33254.91", sum_of_parts: "33254.91" } },
    { name: "read_matches_xml", state: "failed", code: "read_differs", detail: { itbis: "read=526.27 xml=526.72" } },
    { name: "certificate_validity", state: "verified", code: "revocation_not_checked", detail: { signed_at: "09-10-2026 14:05:00", at_signature: "valid", today: "valid", revocation: "not_checked" } },
    { name: "certificate_issuer", state: "not_checked", code: "issuer_not_on_trust_list", detail: { issuer: "Autoridad Ficticia de Prueba" } },
    { name: "subject_rnc", state: "verified", code: null, detail: {} },
    { name: "dgii_accepted", state: "not_checked", code: "network_not_in_tier_a", detail: {} },
    { name: "security_code", state: "not_checked", code: "no_printed_code", detail: { expected: "AbC123" } },
    { name: "qr_present", state: "verified", code: null, detail: { host: "ecf.dgii.gov.do", encf: "E310000000777", rnc_emisor: "131999888" } },
    { name: "qr_matches_read", state: "verified", code: null, detail: {}, read_vs_qr: { rnc: { read: "131999888", qr: "131999888" }, ecf: { read: "E310000000777", qr: "E310000000777" } } },
  ] };
  const fiscalQr: BusinessDossier["dgii_qr"] = { url: "https://ecf.dgii.gov.do/ecf/consultatimbre?RncEmisor=131999888&ENCF=E310000000777&MontoTotal=3450.00&CodigoSeguridad=AbC123", host: "ecf.dgii.gov.do", rnc_emisor: "131999888", encf: "E310000000777", monto_total: "3450.00", codigo_seguridad: "AbC123", fecha_emision: "2026-10-09", fecha_firma: null, rnc_comprador: null };
  dossiers.set(fiscalDossier.draft_id, { ...fiscalDossier, declaration_suggestions: { category: { value: "02", source: "last_choice" }, payment_method: { value: "03", source: "last_choice" } }, fiscal_value: "ncf", ecf_checks: fiscalChecks, ecf_checks_panel_available: true, dgii_qr: fiscalQr, facts: fiscalAfter, sources: [{ id: sourceId, kind: "message", channel: "whatsapp", received_at: "2026-10-10T14:20:00Z", text: "El RNC es 131999888, el NCF es B0100000099 y el ITBIS es 526.27. No sé el e-CF." }], history: [{ draft_id: fiscalDossier.draft_id, version: 2, actor: { ...actor, actor_kind: "owner_via_agent", display_name: "Lucía Mateo vía Cuadrao" }, before: fiscalBefore, after: fiscalAfter, source_ids: [sourceId], turn_key: null, created_at: "2026-10-10T14:25:00Z" }] });
  const fiscalSample = dossiers.get(fiscalDossier.draft_id)!;
  dossiers.set(dossierFixtureIds.saveRefused, { ...fiscalSample, draft_id: dossierFixtureIds.saveRefused });
  dossiers.set(dossierFixtureIds.fiscalBlocked, { ...fiscalSample, draft_id: dossierFixtureIds.fiscalBlocked, facts: { ...fiscalAfter, occurred_on: unknown() }, blockers: [{ code: "fact_required", field: "occurred_on" }], approval_available: false });
  dossiers.set(dossierFixtureIds.noCurrency, { ...fiscalSample, draft_id: dossierFixtureIds.noCurrency, facts: { ...fiscalAfter, currency: unknown() }, blockers: [{ code: "fact_required", field: "currency" }], approval_available: false });
  dossiers.set(dossierFixtureIds.fiscalAttached, { ...fiscalSample, draft_id: dossierFixtureIds.fiscalAttached, sources: [{ id: sourceId, kind: "attachment", channel: "whatsapp", received_at: "2026-10-10T14:20:00Z", connection_id: "rcpt-ferreteria", filename: "recibo-ferreteria.jpg", media_type: "image/jpeg" }] });
  dossiers.set(dossierFixtureIds.totalsOff, { ...fiscalSample, draft_id: dossierFixtureIds.totalsOff, ecf_checks: { ...fiscalChecks, checks: fiscalChecks.checks.map((check) => check.name === "totals_arithmetic" ? { ...check, state: "failed" as const, code: "totals_mismatch", detail: { monto_total: "3450.00", sum_of_parts: "3449.00" } } : check) } });
  const declaredSourceId = "20000000-0000-4000-8000-000000000020";
  const declaration: DgiiDeclaration = { form: "606", category: "02", payment_method: "03", id_type: "1", goods_amount: null, services_amount: "2923.73", paid_on: null };
  dossiers.set(dossierFixtureIds.fiscalDeclared, { ...fiscalSample, draft_id: dossierFixtureIds.fiscalDeclared, version: 3, dgii: declaration, history: [...fiscalSample.history, { draft_id: dossierFixtureIds.fiscalDeclared, version: 3, actor, before: fiscalAfter, after: fiscalAfter, before_dgii: null, after_dgii: declaration, source_ids: [declaredSourceId], turn_key: null, created_at: "2026-10-10T14:28:00Z" }] });
  const noNumberSample = dossiers.get(dossierFixtureIds.noNumber)!;
  const unanswered = (side: BusinessFacts): BusinessFacts => ({ ...side, receipt_state: unknown() });
  dossiers.set(noNumberSample.draft_id, { ...noNumberSample, facts: unanswered(noNumberSample.facts), history: noNumberSample.history.map((revision) => ({ ...revision, before: revision.before && unanswered(revision.before), after: unanswered(revision.after) })) });
  const proposalDossier = dossiers.get(dossierFixtureIds.proposal)!;
  dossiers.set(proposalDossier.draft_id, { ...proposalDossier, facts: { ...proposalDossier.facts, funding: { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "extracted" }, category_id: { ...known("other"), origin: "extracted" } }, sources: [{ id: sourceId, kind: "agent_proposal", channel: "web", received_at: "2026-10-10T14:20:00Z", text: "Propuesta: gasto de 3,450 DOP en Ferretería La Esquina para pintura del taller. Revisar antes de aprobar." }], history: [{ ...proposalDossier.history[0], after: { ...proposalDossier.facts, funding: { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "extracted" }, category_id: { ...known("other"), origin: "extracted" } } }] });
  // Revision 2 approved (the approval took version 3), then Elena marked it Personal: revision 4.
  const marked = dossiers.get(dossierFixtureIds.recordedThenMarked)!;
  const elena: BusinessActor = { ...actor, actor_id: "30000000-0000-4000-8000-000000000003", grant_id: "40000000-0000-4000-8000-000000000003", display_name: "Elena Reyes" };
  const personalSourceId = "20000000-0000-4000-8000-000000000016";
  const personalFacts: BusinessFacts = { ...marked.facts, business_share: { state: "known", value: { kind: "none" }, origin: "member_set", verified: true, source_ids: [personalSourceId] } };
  dossiers.set(marked.draft_id, { ...marked, version: 4, review_state: "accepted", approval_available: false, personal: true, personal_marked_by: { display_name: elena.display_name, email: null, shown_as: "name" }, facts: personalFacts, sources: [...marked.sources, { id: personalSourceId, kind: "web_action", channel: "web", received_at: "2026-10-10T15:05:00Z", text: JSON.stringify({ version: 3, personal: true }) }], history: [...marked.history, { draft_id: marked.draft_id, version: 4, actor: elena, before: marked.facts, after: personalFacts, source_ids: [personalSourceId], turn_key: null, created_at: "2026-10-10T15:05:00Z" }], approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000002", reviewed_version: 2, approved_revision: 2, approved_at: "2026-10-10T14:40:00Z", actor } });
  // The three gates the server serves on a dossier, by the rules its actions enforce. The sample's
  // owner holds approve, so a prepare-holder without it stands in for the accountant.
  const approvalActions: Record<string, BusinessApprovalAction> = { expense: "record_expense", income: "record_income", refund: "record_refund" };
  const refundCandidates = (draft: BusinessDossier): RefundCandidate[] => {
    const { kind, occurred_on: day, currency: money, fiscal } = draft.facts;
    const number = fiscal?.ecf.value ?? fiscal?.ncf.value ?? "";
    const creditNote = /^[BE](04|34)/.test(number);
    if (!(kind.value === "refund" || creditNote) || day.state !== "known" || money.state !== "known") return [];
    const from = new Date(`${day.value}T12:00:00Z`);
    from.setUTCDate(from.getUTCDate() - 30);
    const earliest = from.toISOString().slice(0, 10);
    const rnc = fiscal?.rnc.state === "known" ? fiscal.rnc.value : null;
    return [...dossiers.values()]
      .filter((other) => other.approval_result?.status === "recorded" && other.facts.kind.value === "expense" && other.facts.currency.value === money.value && other.facts.amount.state === "known" && other.facts.occurred_on.state === "known" && other.facts.occurred_on.value >= earliest && other.facts.occurred_on.value <= day.value && (!rnc || other.facts.fiscal?.rnc.value === rnc))
      .sort((a, b) => (b.facts.occurred_on.value ?? "").localeCompare(a.facts.occurred_on.value ?? ""))
      .slice(0, 20)
      .map((other) => ({ id: other.approval_result?.status === "recorded" ? other.approval_result.activity_id : other.draft_id, merchant: other.facts.counterparty.value, occurred_on: other.facts.occurred_on.value ?? "", amount: other.facts.amount.value ?? "", currency: money.value }));
  };
  const factsEditable = (draft: BusinessDossier) => !draft.deleted && draft.capabilities.includes("prepare") && (draft.review_state === "open" || (draft.review_state === "accepted" && draft.capabilities.includes("approve")));
  const declarationEditable = (draft: BusinessDossier) => factsEditable(draft) && draft.facts.kind.value !== "income";
  const editableFields = (draft: BusinessDossier): EditableDossierField[] => {
    if (!factsEditable(draft)) return [];
    const fields: EditableDossierField[] = ["kind", "amount", "occurred_on", "counterparty", "funding", "business_share", "receipt_state", "category_id", "rnc", "fiscal_number", "itbis", "net_amount", "legal_tip", "document_type", "due_on", "modified_ncf"];
    if (draft.review_state === "open" || (draft.facts.kind.value === "expense" && draft.dgii?.actual_refund === true)) fields.push("actual_refund");
    if (draft.review_state === "open" || draft.facts.funding.value?.kind !== "business_account") fields.push("currency");
    return fields;
  };
  const served = (draft: BusinessDossier): Pick<BusinessDossier, "approval_action" | "fiscal_inclusion_available" | "refund_candidates" | "declaration_editable" | "declaration_suggestions"> => ({
    declaration_editable: declarationEditable(draft),
    // The server offers a suggestion only for an answer the record lacks.
    // Only on an open expense, whose approval saves it, and only for an answer the record lacks.
    declaration_suggestions: Object.fromEntries(SUGGESTED.map((field) => [field, declarationEditable(draft) && draft.review_state === "open" && draft.facts.kind.value === "expense" && blankAnswer(draft.dgii, field) ? draft.declaration_suggestions?.[field] ?? null : null])),
    approval_action: draft.approval_available && draft.facts.kind.state === "known" ? approvalActions[draft.facts.kind.value] ?? null : null,
    fiscal_inclusion_available: draft.capabilities.includes("prepare") && !draft.capabilities.includes("approve") && (draft.review_state === "open" || draft.review_state === "accepted") && draft.personal === true && Boolean(draft.fiscal_value),
    refund_candidates: refundCandidates(draft),
  });
  const reviewReceipts = new Map<string, { input: string; result: BusinessDossier }>();
  const fail = (status: number, code: string, context?: unknown): never => { throw Object.assign(new Error(code), { status, code, context, requestId: `sample-${code}` }); };
  const get = (id: string) => {
    const found = dossiers.get(id);
    if (!found) return fail(404, "draft_not_found");
    const stated = found.facts.receipt_state.state === "known" && (found.facts.receipt_state.value === "no_receipt" || found.facts.receipt_state.value === "informal_receipt");
    const editable = editableFields(found);
    const offers = served(found);
    // Only a sample receipt's draft answers its 606 by the server's rule; a stand-in a test opens by id keeps what that test gives it.
    const declared = receiptDrafts.has(id) ? sampleDeclared(found, { sinComprobante: stated && !found.fiscal_value, apart: heldApart.get(id), suggestions: offers.declaration_suggestions }) : null;
    // As the server does on a first write: from here the links are recorded, so a stored copy of a followed value never reads as a person's.
    if (declared && !heldApart.has(id) && found.review_state === "open" && declared.dgii?.form === "606") heldApart.set(id, Object.entries(declared.inheritance).filter(([, link]) => !link.inherited).map(([name]) => name));
    return structuredClone({ document_type: "recibo" as const, ...found, ...sampleStanding({ ...found, review_flags: declared?.review_flags ?? found.review_flags }, seededGaps.get(id)), sin_comprobante: stated && !found.fiscal_value, facts_editable: factsEditable(found), editable_fields: editable, document_type_editable: editable.includes("document_type"), ...offers, ...declared });
  };
  let receiptDraftCount = 0;
  let captureCount = 0;
  const captures: BusinessCapture[] = [];
  const captureReceipts = new Map<string, { input: string; draftId: string }>();
  /**
   * `saved_declaration_links` in short: the 606 a revision of a sample receipt
   * saves, each linked field a person does not hold apart at the value it
   * follows after the write. An open draft is worked out on every read, so
   * only an approved record stores it.
   */
  const savedDeclaration = (before: BusinessFacts, next: BusinessDossier): BusinessDossier["dgii"] => {
    if (!receiptDrafts.has(next.draft_id) || next.review_state === "open" || next.review_state === "accepting") return next.dgii;
    const corrected = new Set<LinkSource>([...(heldValue(before.occurred_on) === heldValue(next.facts.occurred_on) ? [] : ["occurred_on" as const]), ...(idTypeOf(before) === idTypeOf(next.facts) ? [] : ["rnc" as const])]);
    return sampleDeclared(next, { apart: heldApart.get(next.draft_id), corrected }).dgii;
  };
  const writeDeclaration = (id: string, version: number, key: string, body: unknown, change: (current: BusinessDossier, stated: <T>(value: T | null) => BusinessFact<T>) => { facts?: BusinessFacts; dgii: DgiiDeclaration }, links: Pick<BusinessMontosReview, "override_inherited" | "restore_inherited"> = {}) => {
    if (!key) fail(422, "idempotency_key_required");
    const input = JSON.stringify({ id, version, body });
    const prior = reviewReceipts.get(key);
    if (prior) return prior.input === input ? structuredClone(prior.result) : fail(409, "idempotency_conflict");
    const current = get(id);
    if (!current.facts_editable) fail(403, "permission_denied");
    if (current.version !== version) fail(409, "stale_version");
    if (id === dossierFixtureIds.saveRefused) fail(422, "validation_error");
    const actionSourceId = `20000000-0000-4000-8000-${String(current.version + 1).padStart(12, "0")}`;
    const stated = <T>(value: T | null): BusinessFact<T> => value === null ? { state: "unknown", value: null, origin: "member_set", verified: false, source_ids: [actionSourceId] } : { state: "known", value, origin: "member_set", verified: false, source_ids: [actionSourceId] };
    const { facts: nextFacts = current.facts, dgii: written } = change(current, stated);
    // `inheritance_overrides` in short: a linked field a person changed or named is held apart, the two amount sides together, until it is restored.
    const apart = new Set(heldApart.get(id));
    if (current.dgii?.form === "606") for (const [name, source] of PURCHASE_LINKS) if (!sameLinked(source, text(written[name]), text(current.dgii[name]))) apart.add(name);
    for (const name of links.override_inherited ?? []) apart.add(name);
    const restored = new Set(links.restore_inherited);
    for (const side of AMOUNT_SIDES) if (AMOUNT_SIDES.some((other) => restored.has(other))) apart.delete(side); else if (AMOUNT_SIDES.some((other) => apart.has(other))) apart.add(side);
    for (const name of restored) apart.delete(name);
    heldApart.set(id, [...apart].sort());
    const dgii = savedDeclaration(current.facts, { ...current, facts: nextFacts, dgii: keptSources(current.dgii, written) });
    const fiscalValue = nextFacts.fiscal?.ecf.state === "known" ? "ecf" : nextFacts.fiscal?.ncf.state === "known" ? "ncf" : null;
    const next: BusinessDossier = { ...current, version: current.version + 1, facts: nextFacts, fiscal_value: fiscalValue, dgii, sources: [...current.sources, { id: actionSourceId, kind: "web_action", channel: "web", text: JSON.stringify({ version, body }), received_at: "2026-10-10T14:30:00Z" }], history: [...current.history, { draft_id: id, version: current.version + 1, actor, before: current.facts, after: nextFacts, before_dgii: current.dgii ?? null, after_dgii: dgii, source_ids: [actionSourceId], turn_key: null, created_at: "2026-10-10T14:30:00Z" }] };
    dossiers.set(id, next);
    reviewReceipts.set(key, { input, result: get(id) });
    return get(id);
  };
  const reviewFacts = (id: string, version: number, patch: BusinessFactPatch, key: string) => {
    if (!key) fail(422, "idempotency_key_required");
    const input = JSON.stringify({ id, version, facts: patch });
    const prior = reviewReceipts.get(key);
    if (prior) return prior.input === input ? structuredClone(prior.result) : fail(409, "idempotency_conflict");
    const current = get(id);
    if (!current.facts_editable) fail(403, "permission_denied");
    if (current.version !== version) fail(409, "stale_version");
    const required = (["amount", "currency", "occurred_on"] as const).find((field) => patch[field]?.state === "unknown");
    if (current.review_state === "accepted" && required) fail(422, "fact_required", { field: required });
    if (id === dossierFixtureIds.saveRefused) fail(422, "validation_error");
    if (id === dossierFixtureIds.saveConcurrent && version === 2) {
      const otherSourceId = "20000000-0000-4000-8000-000000000014";
      const otherFacts: BusinessFacts = { ...current.facts, counterparty: { state: "known", value: "Corrección de otra persona", origin: "member_set", verified: false, source_ids: [otherSourceId] } };
      dossiers.set(id, { ...current, version: 3, facts: otherFacts, sources: [...current.sources, { id: otherSourceId, kind: "web_action", channel: "web", received_at: "2026-10-10T14:31:00Z", text: JSON.stringify({ version, facts: { counterparty: { state: "known", value: "Corrección de otra persona" } } }) }], history: [...current.history, { draft_id: id, version: 3, actor: { ...actor, actor_id: "30000000-0000-4000-8000-000000000003", grant_id: "40000000-0000-4000-8000-000000000003", display_name: "Elena Reyes" }, before: current.facts, after: otherFacts, source_ids: [otherSourceId], turn_key: null, created_at: "2026-10-10T14:31:00Z" }] });
      throw new TypeError("Synthetic request interrupted before write; another human advanced the draft");
    }
    const actionSourceId = `20000000-0000-4000-8000-${String(current.version + 1).padStart(12, "0")}`;
    const updated = Object.fromEntries(Object.entries(patch).filter(([, fact]) => fact !== undefined).map(([key, fact]) => [key, { ...fact, origin: "member_set", verified: false, source_ids: [actionSourceId] }])) as Partial<BusinessFacts>;
    const next: BusinessDossier = { ...current, version: current.version + 1, facts: { ...current.facts, ...updated }, sources: [...current.sources, { id: actionSourceId, kind: "web_action", channel: "web", text: JSON.stringify({ version, facts: patch }), received_at: "2026-10-10T14:30:00Z" }], history: [...current.history, { draft_id: id, version: current.version + 1, actor, before: current.facts, after: { ...current.facts, ...updated }, source_ids: [actionSourceId], turn_key: null, created_at: "2026-10-10T14:30:00Z" }] };
    if (next.facts.funding.state === "known") {
      next.questions = next.questions.map((question) => question.field === "funding" ? { ...question, state: "answered", answer_source_id: actionSourceId } : question);
      next.blockers = next.blockers.filter((blocker) => blocker.field !== "funding");
    }
    if (next.facts.kind.state === "known" && next.facts.kind.value === "expense") next.blockers = next.blockers.filter((blocker) => blocker.field !== "kind");
    next.blockers = next.blockers.filter((blocker) => !(blocker.code === "fact_required" && blocker.field && next.facts[blocker.field]?.state === "known"));
    if (patch.net_amount) next.net_amount = { amount: next.facts.net_amount?.value ?? null, source: next.facts.net_amount?.value == null ? null : "edited" };
    next.approval_available = next.review_state === "open" && next.blockers.length === 0 && next.capabilities.includes("approve") && next.facts.kind.state === "known" && next.facts.kind.value === "expense";
    next.dgii = savedDeclaration(current.facts, next);
    dossiers.set(id, next);
    reviewReceipts.set(key, { input, result: get(id) });
    if (id === dossierFixtureIds.saveUnknown && version === 2) throw new TypeError("Synthetic saved response interrupted");
    return get(id);
  };
  return {
    dgiiFields: async () => structuredClone(SAMPLE_DGII_FIELDS),
    reviewFiscal: async (id: string, version: number, review: DgiiReview, key: string) => writeDeclaration(id, version, key, review, (current, stated) => {
      const number = printedIdentifier(review.fiscal.ncf);
      const rnc = printedIdentifier(review.fiscal.rnc);
      const fiscal = { ...(current.facts.fiscal ?? { rnc: unknown<string>(), ncf: unknown<string>(), ecf: unknown<string>(), itbis: unknown<string>() }) };
      const held = (fact: BusinessFact<string>) => fact.state === "known" ? fact.value : null;
      if (printedIdentifier(held(fiscal.rnc)) !== rnc) fiscal.rnc = stated(rnc);
      if (printedIdentifier(held(fiscal.ecf) ?? held(fiscal.ncf)) !== number) {
        fiscal.ecf = stated(number?.startsWith("E") ? number : null);
        fiscal.ncf = stated(number?.startsWith("E") ? null : number);
      }
      const itbis = held(fiscal.itbis);
      if (itbis === null || review.fiscal.itbis === null ? itbis !== review.fiscal.itbis : Number(itbis) !== Number(review.fiscal.itbis)) fiscal.itbis = stated(review.fiscal.itbis);
      return { facts: { ...current.facts, fiscal }, dgii: review.declaration };
    }, review.montos),
    reviewPurchase: async (id: string, version: number, purchase: PurchaseChoice, key: string) => writeDeclaration(id, version, key, purchase, (current) => {
      const blank = Object.fromEntries(SAMPLE_DGII_FIELDS["606"].filter(({ name }) => !["rnc", "ncf", "itbis"].includes(name)).map(({ name }) => [name, null]));
      const dgii: DgiiDeclaration = { ...blank, actual_refund: false, purchase_activity_id: null, ...current.dgii, ...purchase, form: "606" };
      if (typeof dgii.category === "string" && !dgii.services_amount && !dgii.goods_amount && current.facts.amount.state === "known") {
        const cents = Math.round(Number(current.facts.amount.value) * 100) - Math.round(Number(current.facts.fiscal?.itbis.value ?? 0) * 100);
        dgii[SERVICE_EXPENSE_TYPES.has(dgii.category) ? "services_amount" : "goods_amount"] = (cents / 100).toFixed(2);
      }
      return { dgii };
    }),
    captureNote: async (request: BusinessCaptureInput, key: string) => {
      const input = JSON.stringify(request);
      const receipt = captureReceipts.get(key);
      if (receipt) return receipt.input === input ? get(receipt.draftId) : fail(409, "idempotency_conflict");
      if (!request.text.trim() || [...request.text].length > 20000 || request.text.includes("\0")) fail(422, "invalid_request");
      const previous = request.draft ? get(request.draft.draft_id) : null;
      if (previous && !previous.capabilities.includes("prepare")) fail(403, "permission_denied");
      if (previous && previous.review_state !== "open") fail(409, "business_draft_not_open");
      if (previous && previous.version !== request.draft?.version) fail(409, "stale_version");
      const index = ++captureCount;
      const id = previous?.draft_id ?? `90000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
      const noteSourceId = `91000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
      const receivedAt = new Date(Date.UTC(2026, 9, 10, 15, 0, index)).toISOString();
      const current: BusinessFacts = previous?.facts ?? { kind: unknown(), amount: unknown(), currency: structuredClone(currency), occurred_on: unknown(), counterparty: unknown(), funding: unknown(), business_share: unknown(), receipt_state: unknown(), category_id: unknown(), fiscal: null };
      const version = (previous?.version ?? 0) + 1;
      const next: BusinessDossier = {
        ...(previous ?? get(dossierFixtureIds.unknown)), draft_id: id, version, facts: current,
        sources: [...(previous?.sources ?? []), { id: noteSourceId, kind: "message", channel: "web", received_at: receivedAt, text: request.text }],
        questions: previous?.questions ?? [],
        history: [...(previous?.history ?? []), { draft_id: id, version, actor, before: previous?.facts ?? null, after: current, source_ids: [noteSourceId], turn_key: null, created_at: receivedAt }],
        blockers: previous?.blockers ?? [{ code: "missing_fields", field: "kind" }, { code: "missing_fields", field: "amount" }, { code: "unknown_funding", field: "funding" }],
        approval_available: previous?.approval_available ?? false, approval_result: null,
      };
      dossiers.set(id, next);
      captures.push({ draft_id: id, version, revision: version, source_id: noteSourceId, text: request.text, received_at: receivedAt, review_state: "open", sent_by: { id: `member:${actor.actor_id}`, kind: "member", person: { display_name: actor.display_name, email: null, shown_as: actor.shown_as } } });
      captureReceipts.set(key, { input, draftId: id });
      return get(id);
    },
    captures: async (query = "", limit = 20, view: "inbox" | "all" | "eliminados" = "all") => {
      if (view === "eliminados") return { items: [], has_more: false };
      if (query.includes("\0") || [...query].length > 200 || !Number.isInteger(limit) || limit < 1 || limit > 50) fail(422, "invalid_request");
      // The Bandeja's notes, as the API answers them: drafts awaiting review that no receipt carries.
      const listed = (note: BusinessCapture) => view === "all" || (["open", "accepting"].includes(get(note.draft_id).review_state) && !get(note.draft_id).sources.some((item) => item.kind === "attachment"));
      const newestFirst = (a: BusinessCapture, b: BusinessCapture) => b.received_at.localeCompare(a.received_at) || b.source_id.localeCompare(a.source_id);
      // As the server counts it: every note of the draft before this one, whatever the query or the page keeps.
      const earlier = (note: BusinessCapture) => captures.filter((other) => other.draft_id === note.draft_id && newestFirst(other, note) > 0).length;
      const found = captures.filter((note) => listed(note) && note.text.toLowerCase().includes(query.toLowerCase())).sort(newestFirst);
      const items = found.slice(0, limit).map((note) => { const current = get(note.draft_id); return { ...note, version: current.version, review_state: current.review_state, earlier_count: earlier(note), bandeja_group: noteGroup(current.review_state, note.draft_id, current.version) }; });
      return { items, has_more: found.length > limit };
    },
    /**
     * The draft of a sample receipt, with the history the server writes. A read
     * (`by: "read"`) is revision 1 by the extractor, for the person whose grant
     * it used: read values from the file, and the answers no read gives left
     * open. A mark a person gave after it is revision 2, by that person. A
     * receipt a person filled in by hand (`by: "person"`) starts as theirs.
     * A fiscal read with its ITBIS also read the Subtotal. `suggestions` are
     * the 606 answers the server offers beside the blank ones, and `paidOn`
     * is a Fecha de pago a person then saved apart from the receipt's date.
     */
    createReceiptDraft: (receipt: ReceiptDetail, { fiscal, confirmable, by = "read", suggestions, paidOn }: { fiscal?: { rnc: string | null; ncf: string | null; itbis: string | null }; confirmable?: boolean; by?: "read" | "person"; suggestions?: BusinessDossier["declaration_suggestions"]; paidOn?: string } = {}) => {
      const id = `80000000-0000-4000-8000-${String(++receiptDraftCount).padStart(12, "0")}`;
      const read = by === "read";
      const stated = <T>(value: T): BusinessFact<T> => ({ state: "known", value, origin: "member_set", verified: false, source_ids: [reviewSourceId] });
      const found = <T>(value: T): BusinessFact<T> => read ? { state: "known", value, origin: "extracted", verified: false, source_ids: [sourceId] } : stated(value);
      const scalar = (value: string | null): BusinessFact<string> => value ? found(value) : unknown();
      const answer = <T>(value: T | null | undefined): BusinessFact<T> => value == null || read ? unknown() : stated(value);
      const first: BusinessFacts = {
        kind: found("expense"),
        amount: scalar(receipt.amount),
        currency: scalar(receipt.currency),
        occurred_on: scalar(receipt.occurred_on),
        counterparty: scalar(receipt.merchant),
        funding: answer(receipt.account_id ? { kind: "business_account" as const, account_id: receipt.account_id } : null),
        business_share: answer({ kind: "all" as const }),
        receipt_state: answer(receipt.sin_comprobante ? "no_receipt" as const : fiscal ? "fiscal_receipt" as const : "informal_receipt" as const),
        category_id: answer(receipt.category_id),
        fiscal: fiscal ? { rnc: scalar(fiscal.rnc), ncf: scalar(fiscal.ncf), ecf: unknown(), itbis: scalar(fiscal.itbis) } : null,
        ...(read && fiscal?.itbis && receipt.amount ? { net_amount: found(money(cents(receipt.amount) - cents(fiscal.itbis))) } : {}),
      };
      const marked = read && receipt.sin_comprobante;
      const current: BusinessFacts = marked ? { ...first, receipt_state: stated("no_receipt") } : first;
      // The read ends a moment after the file arrives, and a person marks it after that: seconds, so no sample time runs ahead of the clock for long.
      const later = (seconds: number) => new Date(Date.parse(receipt.received_at) + seconds * 1000).toISOString();
      const source = { id: sourceId, kind: "attachment" as const, channel: receipt.channel, received_at: receipt.received_at, connection_id: receipt.id, filename: receipt.filename, media_type: receipt.media_type };
      const action = { id: reviewSourceId, kind: "web_action" as const, channel: "web" as const, received_at: read ? later(20) : receipt.received_at, text: JSON.stringify(read ? { version: 1, facts: { receipt_state: { state: "known", value: "no_receipt" } } } : { version: receipt.version - 1, fields: { merchant: receipt.merchant, amount: receipt.amount, currency: receipt.currency, occurred_on: receipt.occurred_on, account_id: receipt.account_id, category_id: receipt.category_id } }) };
      const history: BusinessDraftRevision[] = [{ draft_id: id, version: 1, actor: read ? { ...actor, actor_kind: "extractor" } : actor, before: null, after: first, source_ids: [read ? sourceId : reviewSourceId], turn_key: null, created_at: read ? later(10) : receipt.received_at, before_document_type: null, after_document_type: "recibo" }];
      if (marked) history.push({ draft_id: id, version: 2, actor, before: first, after: current, source_ids: [reviewSourceId], turn_key: null, created_at: later(20) });
      dossiers.set(id, {
        draft_id: id, space_id: receipt.record_context?.space_id ?? "fixture-space", space_name: receipt.record_context?.space_name ?? "Mi negocio", accounts: receipt.record_context?.accounts ?? [],
        capabilities: receipt.record_context?.capabilities ?? [], version: history.length, review_state: "open", facts: current, sources: read && !marked ? [source] : [source, action], questions: [],
        history,
        blockers: [], approval_available: true, approval_result: null,
        sin_comprobante: receipt.sin_comprobante, personal: receipt.personal, personal_marked_by: receipt.personal_marked_by,
        ...(suggestions ? { declaration_suggestions: suggestions } : {}),
      });
      receiptDrafts.add(id);
      const shown = paidOn ? get(id) : null;
      if (shown?.dgii && paidOn) {
        const saved: DgiiDeclaration = { ...shown.dgii, paid_on: paidOn };
        const savedSourceId = "20000000-0000-4000-8000-000000000021";
        dossiers.set(id, {
          ...dossiers.get(id)!, version: shown.version + 1, dgii: saved,
          sources: [...shown.sources, { id: savedSourceId, kind: "web_action", channel: "web", received_at: later(40), text: JSON.stringify({ version: shown.version, dgii: { declaration: saved }, montos: { override_inherited: ["paid_on"] } }) }],
          history: [...shown.history, { draft_id: id, version: shown.version + 1, actor, before: current, after: current, before_dgii: null, after_dgii: saved, source_ids: [savedSourceId], turn_key: null, created_at: later(40) }],
        });
        heldApart.set(id, ["paid_on"]);
      }
      const previous = receipt.draft_id ? seededGaps.get(receipt.draft_id) : undefined;
      const reason = LISTO_GAPS.find((gap) => gap === receipt.bandeja_group?.reason);
      const previousGap = previous?.find((gap) => gap.reason === reason);
      seededGaps.set(id, reason ? [sampleGap(reason, confirmable ?? previousGap?.confirmable ?? false)] : []);
      return id;
    },
    dossier: async (id: string) => id === dossierFixtureIds.unprepared ? fail(409, "draft_not_prepared") : get(id),
    reviewMontos: async (id: string, version: number, montos: BusinessMontosReview, key: string) => reviewFacts(id, version, { net_amount: montos.net_amount, legal_tip: montos.legal_tip }, key),
    reviewDraft: async (id: string, version: number, patch: BusinessFactPatch, key: string) => reviewFacts(id, version, patch, key),
    setDocumentType: async (id: string, version: number, documentType: "recibo" | "venta") => {
      const current = get(id);
      if (current.version !== version) fail(409, "stale_version");
      if (!current.document_type_editable) fail(422, "document_type_locked");
      if (id === dossierFixtureIds.saveRefused) fail(422, "validation_error");
      dossiers.set(id, { ...current, version: current.version + 1, document_type: documentType, document_type_detected: undefined, history: [...current.history, { draft_id: id, version: current.version + 1, actor, before: current.facts, after: current.facts, before_document_type: current.document_type, after_document_type: documentType, source_ids: [], turn_key: null, created_at: "2026-10-10T14:30:00Z" }] });
      return get(id);
    },
    settleRemainder: async (id: string, version: number) => {
      const current = get(id);
      if (!current.capabilities.includes("approve")) fail(403, "permission_denied");
      if (current.version !== version) fail(409, "stale_version");
      if (current.review_state !== "accepted") fail(422, "business_draft_not_recorded");
      if (!current.unrecorded_purchases) fail(422, "business_remainder_none");
      dossiers.set(id, { ...current, version: current.version + 1, unrecorded_purchases: 0 });
      return get(id);
    },
    approveDraft: async (id: string, version: number, action: BusinessApprovalAction = "record_expense", { acceptGaps = [], suggestions }: BusinessApprovalOptions = {}) => {
      const current = get(id);
      if (current.approval_action && action !== current.approval_action) fail(422, "invalid_request");
      if (id === dossierFixtureIds.denied) fail(403, "permission_denied");
      if (id === dossierFixtureIds.stale) {
        // Another person saved a revision first: the facts changed, so the
        // history lists that revision and the header names it.
        const otherSourceId = "20000000-0000-4000-8000-000000000015";
        const otherFacts: BusinessFacts = { ...current.facts, amount: { state: "known", value: "3550.00", origin: "member_set", verified: false, source_ids: [otherSourceId] } };
        dossiers.set(id, { ...current, version: current.version + 1, facts: otherFacts, history: [...current.history, { draft_id: id, version: current.version + 1, actor: { ...actor, actor_id: "30000000-0000-4000-8000-000000000003", grant_id: "40000000-0000-4000-8000-000000000003", display_name: "Elena Reyes" }, before: current.facts, after: otherFacts, source_ids: [otherSourceId], turn_key: null, created_at: "2026-10-10T14:32:00Z" }] });
        fail(409, "stale_version");
      }
      if (current.version !== version) fail(409, "stale_version");
      if (!current.approval_available) fail(422, "unresolved_facts");
      const gaps = current.listo_gaps ?? [];
      const confirmable = current.confirmable ?? [];
      if (gaps.some((gap) => !confirmable.includes(gap) || !acceptGaps.includes(gap))) fail(422, "not_listo", { gaps, confirmable });
      if (id === dossierFixtureIds.outcomeUnknown) {
        const next: BusinessDossier = { ...current, review_state: "accepting", approval_available: false, approval_result: { status: "outcome_unknown", code: "recording_unknown", reviewed_version: version } };
        dossiers.set(id, next);
        throw new TypeError("Synthetic connection interrupted");
      }
      // The approval saves each suggestion the person saw into its blank answer, with its source.
      const taken = SUGGESTED.flatMap((field) => suggestions?.[field] ? [[field, suggestions[field]!] as const] : []);
      if (taken.some(([field]) => !blankAnswer(current.dgii, field))) fail(422, "suggestion_stale");
      const saved: DgiiDeclaration | null | undefined = taken.length ? { ...(current.dgii ?? { form: "606" }), ...Object.fromEntries(taken.map(([field, { value }]) => [field, value])), ...(taken.some(([field]) => field === "category") ? { category_suggested: false } : {}), suggestion_sources: { ...current.dgii?.suggestion_sources, ...Object.fromEntries(taken.map(([field, { source }]) => [field, source])) } } : current.dgii;
      const next: BusinessDossier = { ...current, dgii: saved, version: current.version + 1, review_state: "accepted", approval_available: false, approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000001", reviewed_version: version, approved_revision: factsRevision(current), approved_at: "2026-10-10T14:40:00Z", actor } };
      dossiers.set(id, next);
      return get(id);
    },
  };
}
