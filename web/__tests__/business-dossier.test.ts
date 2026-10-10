import { test } from "bun:test";
import assert from "node:assert/strict";
import { approveBusinessDraft, getBusinessDossier, reviewBusinessDraft } from "@/lib/business-api";
import { withBusinessSpace } from "@/components/business-app/business-data";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { presentBusinessFact } from "@/components/business-app/receipt-fact-presentation";

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
    await reviewBusinessDraft(dossierFixtureIds.ready, 8, { funding: { state: "owner_does_not_know", value: null } });
    await approveBusinessDraft(dossierFixtureIds.ready, 9, "human-approval-once");
    assert.equal(calls.length, 3);
    assert.ok(calls[0].url.endsWith(`/business/drafts/${dossierFixtureIds.ready}/dossier`));
    assert.deepEqual(calls[1].body, { version: 8, facts: { funding: { state: "owner_does_not_know", value: null } } });
    assert.deepEqual(calls[2].body, { version: 9, action: "record_expense" });
    assert.equal(calls[2].key, "human-approval-once");
    assert.equal(calls[2].method, "POST");
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
  const ownerUnknown = await fixture.reviewDraft(unknown.draft_id, unknown.version, { funding: { state: "owner_does_not_know", value: null } });
  assert.equal(presentBusinessFact("funding", ownerUnknown.facts, accounts, "en", labels), "Owner doesn't know");
  assert.equal(ownerUnknown.approval_available, false);
});
