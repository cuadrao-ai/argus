import type { BusinessAccount, BusinessCapture, BusinessCaptureInput, ReceiptDetail } from "@/lib/business-api";
import { factsRevision, type BusinessActor, type BusinessDossier, type BusinessFact, type BusinessFactPatch, type BusinessFacts } from "@/lib/business-dossier";

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
} as const;

const sourceId = "20000000-0000-4000-8000-000000000001";
const reviewSourceId = "20000000-0000-4000-8000-000000000002";
const actor: BusinessActor = {
  actor_id: "30000000-0000-4000-8000-000000000001",
  actor_kind: "member",
  display_name: "Ana Peña",
  grant_id: "40000000-0000-4000-8000-000000000001",
  issuer_id: "30000000-0000-4000-8000-000000000002",
  issuer_display_name: "Lucía Mateo",
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
  for (const [name, id] of Object.entries(dossierFixtureIds)) {
    const ready = name !== "unknown" && name !== "unknownAmount";
    const current: BusinessFacts = { ...facts, category_id: { ...known("other"), origin: "member_set", source_ids: [reviewSourceId] }, funding: ready ? { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "member_set", source_ids: [reviewSourceId] } : unknown(), amount: name === "unknownAmount" ? unknown() : facts.amount, kind: name === "unknownKind" ? unknown() : name === "income" ? known("income") : facts.kind };
    dossiers.set(id, {
      draft_id: id,
      // The server's reading: every sample record has read facts.
      fiscal_known: true,
      space_id: "50000000-0000-4000-8000-000000000001",
      space_name: "Taller Lucía · sample business",
      accounts,
      version: 2,
      review_state: "open",
      facts: current,
      sources: [{ id: sourceId, kind: "message", channel: "whatsapp", received_at: "2026-10-10T14:20:00Z", text: "Ayer compré pintura y brochas para el taller en Ferretería La Esquina. Fueron 3,450. No tengo recibo." }, { id: reviewSourceId, kind: "web_action", channel: "web", received_at: "2026-10-10T14:25:00Z", text: JSON.stringify({ version: 1, facts: { category_id: { state: "known", value: "other" }, ...(ready ? { funding: { state: "known", value: { kind: "business_account", account_id: accounts[0].id } } } : {}) } }) }],
      questions: ready ? [] : [{ id: "60000000-0000-4000-8000-000000000001", draft_id: id, field: "funding", asked_of: "accountant", channel: "web", state: "open", prompt: "How was this paid?", allowed_answers: ["known", "owner_does_not_know"], answer_source_id: null, created_at: "2026-10-10T14:22:00Z" }],
      history: [{ draft_id: id, version: 1, actor: { ...actor, actor_kind: "owner_via_agent", display_name: "Lucía Mateo via Cuadrao" }, before: null, after: facts, source_ids: [sourceId], turn_key: null, created_at: "2026-10-10T14:21:00Z" }, { draft_id: id, version: 2, actor, before: facts, after: current, source_ids: [reviewSourceId], turn_key: null, created_at: "2026-10-10T14:25:00Z" }],
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
  dossiers.set(fiscalDossier.draft_id, { ...fiscalDossier, fiscal_value: "ncf", ecf_checks: fiscalChecks, dgii_qr: fiscalQr, facts: fiscalAfter, sources: [{ id: sourceId, kind: "message", channel: "whatsapp", received_at: "2026-10-10T14:20:00Z", text: "El RNC es 131999888, el NCF es B0100000099 y el ITBIS es 526.27. No sé el e-CF." }], history: [{ draft_id: fiscalDossier.draft_id, version: 2, actor: { ...actor, actor_kind: "owner_via_agent", display_name: "Lucía Mateo via Cuadrao" }, before: fiscalBefore, after: fiscalAfter, source_ids: [sourceId], turn_key: null, created_at: "2026-10-10T14:25:00Z" }] });
  const proposalDossier = dossiers.get(dossierFixtureIds.proposal)!;
  dossiers.set(proposalDossier.draft_id, { ...proposalDossier, facts: { ...proposalDossier.facts, funding: { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "extracted" }, category_id: { ...known("other"), origin: "extracted" } }, sources: [{ id: sourceId, kind: "agent_proposal", channel: "web", received_at: "2026-10-10T14:20:00Z", text: "Propuesta: gasto de 3,450 DOP en Ferretería La Esquina para pintura del taller. Revisar antes de aprobar." }], history: [{ ...proposalDossier.history[0], after: { ...proposalDossier.facts, funding: { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "extracted" }, category_id: { ...known("other"), origin: "extracted" } } }] });
  // Revision 2 approved (the approval took version 3), then Elena marked it Personal: revision 4.
  const marked = dossiers.get(dossierFixtureIds.recordedThenMarked)!;
  const elena: BusinessActor = { ...actor, actor_id: "30000000-0000-4000-8000-000000000003", grant_id: "40000000-0000-4000-8000-000000000003", display_name: "Elena Reyes" };
  const personalSourceId = "20000000-0000-4000-8000-000000000016";
  const personalFacts: BusinessFacts = { ...marked.facts, business_share: { state: "known", value: { kind: "none" }, origin: "member_set", verified: true, source_ids: [personalSourceId] } };
  dossiers.set(marked.draft_id, { ...marked, version: 4, review_state: "accepted", approval_available: false, personal: true, personal_marked_by: elena.display_name, facts: personalFacts, sources: [...marked.sources, { id: personalSourceId, kind: "web_action", channel: "web", received_at: "2026-10-10T15:05:00Z", text: JSON.stringify({ version: 3, personal: true }) }], history: [...marked.history, { draft_id: marked.draft_id, version: 4, actor: elena, before: marked.facts, after: personalFacts, source_ids: [personalSourceId], turn_key: null, created_at: "2026-10-10T15:05:00Z" }], approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000002", reviewed_version: 2, approved_revision: 2, approved_at: "2026-10-10T14:40:00Z", actor } });
  const reviewReceipts = new Map<string, { input: string; result: BusinessDossier }>();
  const fail = (status: number, code: string): never => { throw Object.assign(new Error(code), { status, code }); };
  const get = (id: string) => {
    const found = dossiers.get(id);
    return found ? structuredClone(found) : fail(404, "draft_not_found");
  };
  let receiptDraftCount = 0;
  let captureCount = 0;
  const captures: BusinessCapture[] = [];
  const captureReceipts = new Map<string, { input: string; draftId: string }>();
  return {
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
      captures.push({ draft_id: id, version, revision: version, source_id: noteSourceId, text: request.text, received_at: receivedAt, review_state: "open" });
      captureReceipts.set(key, { input, draftId: id });
      return get(id);
    },
    captures: async (query = "", limit = 20, view: "inbox" | "all" = "all") => {
      if (query.includes("\0") || [...query].length > 200 || !Number.isInteger(limit) || limit < 1 || limit > 50) fail(422, "invalid_request");
      // The Bandeja's notes, as the API answers them: drafts awaiting review that no receipt carries.
      const listed = (note: BusinessCapture) => view === "all" || (["open", "accepting"].includes(get(note.draft_id).review_state) && !get(note.draft_id).sources.some((item) => item.kind === "attachment"));
      return captures.filter((note) => listed(note) && note.text.toLowerCase().includes(query.toLowerCase())).sort((a, b) => b.received_at.localeCompare(a.received_at) || b.source_id.localeCompare(a.source_id)).slice(0, limit).map((note) => { const current = get(note.draft_id); return { ...note, version: current.version, review_state: current.review_state }; });
    },
    createReceiptDraft: (receipt: ReceiptDetail) => {
      const id = `80000000-0000-4000-8000-${String(++receiptDraftCount).padStart(12, "0")}`;
      const reviewed = <T>(value: T): BusinessFact<T> => ({ state: "known", value, origin: "member_set", verified: false, source_ids: [reviewSourceId] });
      const scalar = (value: string | null): BusinessFact<string> => value ? reviewed(value) : unknown();
      const current: BusinessFacts = {
        kind: reviewed("expense"),
        amount: scalar(receipt.amount),
        currency: scalar(receipt.currency),
        occurred_on: scalar(receipt.occurred_on),
        counterparty: scalar(receipt.merchant),
        funding: receipt.account_id ? reviewed({ kind: "business_account", account_id: receipt.account_id }) : unknown(),
        business_share: reviewed({ kind: "all" }),
        receipt_state: reviewed("informal_receipt"),
        category_id: scalar(receipt.category_id),
        fiscal: null,
      };
      const source = { id: sourceId, kind: "attachment" as const, channel: receipt.channel, received_at: receipt.received_at, connection_id: receipt.id, filename: receipt.filename, media_type: receipt.media_type };
      const action = { id: reviewSourceId, kind: "web_action" as const, channel: "web" as const, received_at: receipt.received_at, text: JSON.stringify({ version: receipt.version - 1, fields: { merchant: receipt.merchant, amount: receipt.amount, currency: receipt.currency, occurred_on: receipt.occurred_on, account_id: receipt.account_id, category_id: receipt.category_id } }) };
      dossiers.set(id, {
        draft_id: id, space_id: receipt.record_context?.space_id ?? "fixture-space", space_name: receipt.record_context?.space_name ?? "Mi negocio", accounts: receipt.record_context?.accounts ?? [],
        capabilities: receipt.record_context?.capabilities ?? [], version: 1, review_state: "open", facts: current, sources: [source, action], questions: [],
        history: [{ draft_id: id, version: 1, actor, before: null, after: current, source_ids: [reviewSourceId], turn_key: null, created_at: receipt.received_at }],
        blockers: [], approval_available: true, approval_result: null,
      });
      return id;
    },
    dossier: async (id: string) => id === dossierFixtureIds.unprepared ? fail(409, "draft_not_prepared") : get(id),
    reviewDraft: async (id: string, version: number, patch: BusinessFactPatch, key: string) => {
      if (!key) fail(422, "idempotency_key_required");
      const input = JSON.stringify({ id, version, facts: patch });
      const prior = reviewReceipts.get(key);
      if (prior) return prior.input === input ? structuredClone(prior.result) : fail(409, "idempotency_conflict");
      const current = get(id);
      if (!current.capabilities.includes("prepare")) fail(403, "permission_denied");
      if (current.version !== version) fail(409, "stale_version");
      if (id === dossierFixtureIds.saveConcurrent && version === 2) {
        const otherSourceId = "20000000-0000-4000-8000-000000000014";
        const otherFacts: BusinessFacts = { ...current.facts, counterparty: { state: "known", value: "Other human correction", origin: "member_set", verified: false, source_ids: [otherSourceId] } };
        dossiers.set(id, { ...current, version: 3, facts: otherFacts, sources: [...current.sources, { id: otherSourceId, kind: "web_action", channel: "web", received_at: "2026-10-10T14:31:00Z", text: JSON.stringify({ version, facts: { counterparty: { state: "known", value: "Other human correction" } } }) }], history: [...current.history, { draft_id: id, version: 3, actor: { ...actor, actor_id: "30000000-0000-4000-8000-000000000003", grant_id: "40000000-0000-4000-8000-000000000003", display_name: "Elena Reyes" }, before: current.facts, after: otherFacts, source_ids: [otherSourceId], turn_key: null, created_at: "2026-10-10T14:31:00Z" }] });
        throw new TypeError("Synthetic request interrupted before write; another human advanced the draft");
      }
      const actionSourceId = `20000000-0000-4000-8000-${String(current.version + 1).padStart(12, "0")}`;
      const updated = Object.fromEntries(Object.entries(patch).map(([key, fact]) => [key, { ...fact, origin: "member_set", verified: false, source_ids: [actionSourceId] }])) as Partial<BusinessFacts>;
      const next: BusinessDossier = { ...current, version: current.version + 1, facts: { ...current.facts, ...updated }, sources: [...current.sources, { id: actionSourceId, kind: "web_action", channel: "web", text: JSON.stringify({ version, facts: patch }), received_at: "2026-10-10T14:30:00Z" }], history: [...current.history, { draft_id: id, version: current.version + 1, actor, before: current.facts, after: { ...current.facts, ...updated }, source_ids: [actionSourceId], turn_key: null, created_at: "2026-10-10T14:30:00Z" }] };
      if (next.facts.funding.state === "known") {
        next.questions = next.questions.map((question) => question.field === "funding" ? { ...question, state: "answered", answer_source_id: actionSourceId } : question);
        next.blockers = next.blockers.filter((blocker) => blocker.field !== "funding");
      }
      if (next.facts.kind.state === "known" && next.facts.kind.value === "expense") next.blockers = next.blockers.filter((blocker) => blocker.field !== "kind");
      next.approval_available = next.blockers.length === 0 && next.capabilities.includes("approve") && next.facts.kind.state === "known" && next.facts.kind.value === "expense";
      dossiers.set(id, next);
      reviewReceipts.set(key, { input, result: get(id) });
      if (id === dossierFixtureIds.saveUnknown && version === 2) throw new TypeError("Synthetic saved response interrupted");
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
    approveDraft: async (id: string, version: number) => {
      const current = get(id);
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
      if (id === dossierFixtureIds.outcomeUnknown) {
        const next: BusinessDossier = { ...current, review_state: "accepting", approval_available: false, approval_result: { status: "outcome_unknown", code: "recording_unknown", reviewed_version: version } };
        dossiers.set(id, next);
        throw new TypeError("Synthetic connection interrupted");
      }
      const next: BusinessDossier = { ...current, version: current.version + 1, review_state: "accepted", approval_available: false, approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000001", reviewed_version: version, approved_revision: factsRevision(current), approved_at: "2026-10-10T14:40:00Z", actor } };
      dossiers.set(id, next);
      return get(id);
    },
  };
}
