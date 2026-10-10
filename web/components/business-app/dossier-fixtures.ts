import type { BusinessAccount, ReceiptDetail } from "@/lib/business-api";
import type { BusinessActor, BusinessDossier, BusinessFact, BusinessFactPatch, BusinessFacts } from "@/lib/business-dossier";

export const dossierFixtureIds = {
  unknown: "10000000-0000-4000-8000-000000000001",
  ready: "10000000-0000-4000-8000-000000000002",
  readOnly: "10000000-0000-4000-8000-000000000003",
  stale: "10000000-0000-4000-8000-000000000004",
  denied: "10000000-0000-4000-8000-000000000005",
  outcomeUnknown: "10000000-0000-4000-8000-000000000006",
  unknownAmount: "10000000-0000-4000-8000-000000000007",
  income: "10000000-0000-4000-8000-000000000008",
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
const known = <T>(value: T): BusinessFact<T> => ({ state: "known", value, origin: "owner_stated", verified: false, source_ids: [sourceId] });

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
    const current: BusinessFacts = { ...facts, category_id: { ...known("other"), origin: "member_set", source_ids: [reviewSourceId] }, funding: ready ? { ...known({ kind: "business_account", account_id: accounts[0].id }), origin: "member_set", source_ids: [reviewSourceId] } : unknown(), amount: name === "unknownAmount" ? unknown() : facts.amount, kind: name === "income" ? known("income") : facts.kind };
    dossiers.set(id, {
      draft_id: id,
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
      blockers: ready ? name === "income" ? [{ code: "unsupported_kind", field: "kind" }] : [] : [{ code: "unknown_funding", field: "funding" }, ...(name === "unknownAmount" ? [{ code: "missing_fields", field: "amount" as const }] : [])],
      approval_available: ready && name !== "readOnly" && name !== "income",
      approval_result: null,
    });
  }
  const fail = (status: number, code: string): never => { throw Object.assign(new Error(code), { status, code }); };
  const get = (id: string) => {
    const found = dossiers.get(id);
    return found ? structuredClone(found) : fail(404, "draft_not_found");
  };
  let receiptDraftCount = 0;
  return {
    createReceiptDraft: (receipt: ReceiptDetail) => {
      const id = `80000000-0000-4000-8000-${String(++receiptDraftCount).padStart(12, "0")}`;
      const scalar = (value: string | null): BusinessFact<string> => value ? known(value) : unknown();
      const current: BusinessFacts = {
        kind: known("expense"),
        amount: scalar(receipt.amount),
        currency: scalar(receipt.currency),
        occurred_on: scalar(receipt.occurred_on),
        counterparty: scalar(receipt.merchant),
        funding: receipt.account_id ? known({ kind: "business_account", account_id: receipt.account_id }) : unknown(),
        business_share: known({ kind: "all" }),
        receipt_state: known("informal_receipt"),
        category_id: scalar(receipt.category_id),
        fiscal: null,
      };
      const source = { id: sourceId, kind: "attachment" as const, channel: receipt.channel, received_at: receipt.received_at, connection_id: receipt.id, filename: receipt.filename, media_type: receipt.media_type };
      dossiers.set(id, {
        draft_id: id, space_id: receipt.space_id, space_name: receipt.space_name, accounts: receipt.accounts,
        capabilities: receipt.capabilities, version: 1, review_state: "open", facts: current, sources: [source], questions: [],
        history: [{ draft_id: id, version: 1, actor, before: null, after: current, source_ids: [sourceId], turn_key: null, created_at: receipt.received_at }],
        blockers: [], approval_available: true, approval_result: null,
      });
      return id;
    },
    dossier: async (id: string) => get(id),
    reviewDraft: async (id: string, version: number, patch: BusinessFactPatch) => {
      const current = get(id);
      if (!current.capabilities.includes("prepare")) fail(403, "permission_denied");
      if (current.version !== version) fail(409, "stale_version");
      const actionSourceId = `20000000-0000-4000-8000-${String(current.version + 1).padStart(12, "0")}`;
      const updated = Object.fromEntries(Object.entries(patch).map(([key, fact]) => [key, { ...fact, origin: "member_set", verified: false, source_ids: [actionSourceId] }])) as Partial<BusinessFacts>;
      const next: BusinessDossier = { ...current, version: current.version + 1, facts: { ...current.facts, ...updated }, sources: [...current.sources, { id: actionSourceId, kind: "web_action", channel: "web", text: JSON.stringify({ version, facts: patch }), received_at: "2026-10-10T14:30:00Z" }], history: [...current.history, { draft_id: id, version: current.version + 1, actor, before: current.facts, after: { ...current.facts, ...updated }, source_ids: [actionSourceId], turn_key: null, created_at: "2026-10-10T14:30:00Z" }] };
      if (next.facts.funding.state === "known") {
        next.questions = next.questions.map((question) => question.field === "funding" ? { ...question, state: "answered", answer_source_id: actionSourceId } : question);
        next.blockers = next.blockers.filter((blocker) => blocker.field !== "funding");
      }
      next.approval_available = next.blockers.length === 0 && next.capabilities.includes("approve");
      dossiers.set(id, next);
      return get(id);
    },
    approveDraft: async (id: string, version: number) => {
      const current = get(id);
      if (id === dossierFixtureIds.denied) fail(403, "permission_denied");
      if (id === dossierFixtureIds.stale) {
        dossiers.set(id, { ...current, version: current.version + 1, facts: { ...current.facts, amount: known("3550.00") } });
        fail(409, "stale_version");
      }
      if (current.version !== version) fail(409, "stale_version");
      if (!current.approval_available) fail(422, "unresolved_facts");
      if (id === dossierFixtureIds.outcomeUnknown) {
        const next: BusinessDossier = { ...current, review_state: "accepting", approval_available: false, approval_result: { status: "outcome_unknown", code: "recording_unknown", reviewed_version: version } };
        dossiers.set(id, next);
        throw new TypeError("Synthetic connection interrupted");
      }
      const next: BusinessDossier = { ...current, review_state: "accepted", approval_available: false, approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000001", reviewed_version: version, actor } };
      dossiers.set(id, next);
      return get(id);
    },
  };
}
