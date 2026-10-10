import { test } from "bun:test";
import assert from "node:assert/strict";
import { approveBusinessDraft, getBusinessDossier, reviewBusinessDraft, listBusinessExpenses, type BusinessExpense } from "@/lib/business-api";
import { withBusinessSpace } from "@/components/business-app/business-data";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { presentBusinessFact, presentFiscalFact } from "@/components/business-app/receipt-fact-presentation";

test("canonical draft transport binds explicit ID, version, human effect and idempotency", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const calls: { url: string; method: string; body: unknown; key: string | null }[] = [];
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null, key: new Headers(init?.headers).get("Idempotency-Key") });
    return new Response(JSON.stringify({ draft_id: dossierFixtureIds.ready }), { headers: { "Content-Type": "application/json" } });
  };
  try {
    await getBusinessDossier(dossierFixtureIds.ready);
    await reviewBusinessDraft(dossierFixtureIds.ready, 8, { funding: { state: "owner_does_not_know", value: null } }, "human-review-once");
    await reviewBusinessDraft(dossierFixtureIds.ready, 8, { funding: { state: "owner_does_not_know", value: null } }, "human-review-once");
    await reviewBusinessDraft(dossierFixtureIds.ready, 9, { kind: { state: "known", value: "expense" } }, "human-review-new-intent");
    await approveBusinessDraft(dossierFixtureIds.ready, 10, "human-approval-once");
    assert.equal(calls.length, 5);
    assert.ok(calls[0].url.endsWith(`/business/drafts/${dossierFixtureIds.ready}/dossier`));
    assert.deepEqual(calls[1].body, { version: 8, facts: { funding: { state: "owner_does_not_know", value: null } } });
    assert.equal(calls[1].key, "human-review-once");
    assert.deepEqual(calls[2], calls[1]);
    assert.equal(calls[3].key, "human-review-new-intent");
    assert.deepEqual(calls[3].body, { version: 9, facts: { kind: { state: "known", value: "expense" } } });
    assert.deepEqual(calls[4].body, { version: 10, action: "record_expense" });
    assert.equal(calls[4].key, "human-approval-once");
    assert.equal(calls[4].method, "POST");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});

test("grant-scoped receipt and draft calls never create the current person's Business space", async () => {
  const fixture = createFixtureBusinessDataSource();
  let starts = 0;
  const source = withBusinessSpace({ ...fixture, ensureSpace: async () => { starts++; return { id: "wrong-own-space", name: "Own business" }; } }, () => "en");
  const record = await source.dossier(dossierFixtureIds.ready);
  const receipt = await source.receipt("rcpt-ferreteria");
  await source.receiptSource(receipt.id);
  const reviewed = await source.saveReview(receipt.id, receipt.version, { account_id: receipt.accounts[0].id });
  assert.ok(reviewed.draft_id);
  await source.dossier(reviewed.draft_id);
  assert.equal(starts, 0);
  assert.equal(record.space_name, "Taller Lucía · sample business");
});

test("unknown and owner-does-not-know funding preserve their distinct display states", async () => {
  const accounts = [{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }];
  const fixture = createDossierFixtures(accounts);
  const unknown = await fixture.dossier(dossierFixtureIds.unknownAmount);
  const labels = { unknown: "Unknown", ownerUnknown: "Owner doesn't know", ownerFunds: "Owner's money", businessAccount: "Business account" };
  assert.equal(presentBusinessFact("amount", unknown.facts, accounts, "en", labels), "Unknown");
  assert.equal(presentBusinessFact("funding", unknown.facts, accounts, "en", labels), "Unknown");
  const ownerUnknown = await fixture.reviewDraft(unknown.draft_id, unknown.version, { funding: { state: "owner_does_not_know", value: null } }, "owner-uncertainty");
  assert.equal(presentBusinessFact("funding", ownerUnknown.facts, accounts, "en", labels), "Owner doesn't know");
  assert.equal(ownerUnknown.approval_available, false);
});

test("uncertain review replays the same command once, while a new intent uses a new key", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const current = await fixture.dossier(dossierFixtureIds.saveUnknown);
  const facts = { counterparty: { state: "known" as const, value: "Reviewed merchant" } };
  await assert.rejects(fixture.reviewDraft(current.draft_id, current.version, facts, "same-command"), TypeError);
  const replay = await fixture.reviewDraft(current.draft_id, current.version, facts, "same-command");
  assert.equal(replay.version, 3);
  assert.equal(replay.history.length, 3);
  assert.equal(replay.sources.filter((source) => source.kind === "web_action").length, 2);
  await assert.rejects(fixture.reviewDraft(current.draft_id, replay.version, facts, "same-command"), { code: "idempotency_conflict" });
  const next = await fixture.reviewDraft(current.draft_id, replay.version, { counterparty: { state: "known", value: "New correction" } }, "new-command");
  assert.equal(next.version, 4);
  assert.equal(next.facts.counterparty.value, "New correction");
});

test("unknown kind becomes a sourced human expense decision on its exact revision", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const current = await fixture.dossier(dossierFixtureIds.unknownKind);
  assert.equal(current.facts.kind.state, "unknown");
  assert.equal(current.approval_available, false);
  const next = await fixture.reviewDraft(current.draft_id, current.version, { kind: { state: "known", value: "expense" } }, "kind-decision");
  assert.equal(next.facts.kind.value, "expense");
  assert.equal(next.facts.kind.origin, "member_set");
  assert.equal(next.approval_available, true);
  assert.equal(next.approval_result, null);
  const source = next.sources.find((source) => source.id === next.facts.kind.source_ids[0]);
  assert.equal(source?.kind, "web_action");
  assert.deepEqual(source && "text" in source ? JSON.parse(source.text) : null, { version: current.version, facts: { kind: { state: "known", value: "expense" } } });
  await assert.rejects(fixture.reviewDraft(current.draft_id, current.version, { kind: { state: "known", value: "expense" } }, "stale-kind-decision"), { code: "stale_version" });
});

test("fiscal values preserve unknown, exact tax and verified server states", async () => {
  const fixture = createDossierFixtures([{ id: "scoped-account", nickname: "Client cash", type: "cash", currency: "DOP" }]);
  const dossier = await fixture.dossier(dossierFixtureIds.fiscal);
  const labels = { unknown: "Unknown", ownerUnknown: "Owner doesn't know", notRecorded: "Not recorded" };
  assert.equal(presentFiscalFact("rnc", dossier.facts, "en", labels), "131999888");
  assert.equal(presentFiscalFact("ecf", dossier.facts, "en", labels), "Owner doesn't know");
  assert.equal(presentFiscalFact("itbis", dossier.facts, "en", labels), "RD$ 526.27");
  assert.equal(dossier.facts.fiscal?.itbis.verified, true);
  assert.equal(presentFiscalFact("rnc", dossier.history[0].before!, "en", labels), "Unknown");
  assert.equal(presentFiscalFact("itbis", { ...dossier.facts, currency: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } }, "en", labels), "526.27");
});

test("owner-funded expense projection preserves its null account and funding kind", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const expense: BusinessExpense = { id: "owner-funded-expense", merchant: "Supplier", amount: "3450.00", currency: "DOP", category_id: null, account_id: null, funding: "owner_funds", occurred_on: "2026-10-09", receipt_id: null };
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async () => new Response(JSON.stringify({ items: [expense] }), { headers: { "Content-Type": "application/json" } });
  try {
    assert.deepEqual(await listBusinessExpenses("2026-10-01", "2026-10-31"), [expense]);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});
