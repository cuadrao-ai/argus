import { test } from "bun:test";
import assert from "node:assert/strict";
import { captureOutcomeUnknown, validCaptureText } from "@/components/business-app/ManualCaptureDialog";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { withBusinessSpace } from "@/components/business-app/business-data";
import { captureBusinessNote, listBusinessCaptures } from "@/lib/business-api";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const fixture = () => createDossierFixtures([{ id: "cash", nickname: "Caja", type: "cash", currency: "DOP" }]);

test("verbatim notes reject blanks/NUL and count Unicode characters like the server", () => {
  assert.equal(validCaptureText(" \n "), false);
  assert.equal(validCaptureText("hola\0"), false);
  assert.equal(validCaptureText("á".repeat(20001)), false);
  assert.equal(validCaptureText("🧾".repeat(20000)), true);
  assert.equal(validCaptureText("  ayer pagué pintura\nno sé cuánto  "), true);
});

test("capture transport preserves body and exact retry key, and list encodes literal search", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  const calls: { url: string; method: string; body: unknown; key: string | null }[] = [];
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null, key: new Headers(init?.headers).get("Idempotency-Key") });
    return new Response(JSON.stringify(init?.method === "POST" ? { draft_id: "canonical-draft" } : { items: [] }), { headers: { "Content-Type": "application/json" } });
  };
  try {
    const input = { text: "  pintura\nsin recibo  ", draft: { draft_id: "canonical-draft", version: 4 } };
    await captureBusinessNote(input, "intent-once");
    await captureBusinessNote(input, "intent-once");
    await captureBusinessNote({ text: "otra nota" }, "new-intent");
    await listBusinessCaptures("%_ á", 20);
    assert.deepEqual(calls[0].body, input);
    assert.equal(calls[0].key, "intent-once");
    assert.deepEqual(calls[1], calls[0]);
    assert.deepEqual(calls[2].body, { text: "otra nota" });
    assert.equal(calls[2].key, "new-intent");
    assert.ok((calls[0].url).endsWith("/business/captures"));
    assert.equal(new URL(calls[3].url).searchParams.get("q"), "%_ á");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});

test("raw capture and list adapters never bootstrap a Business", async () => {
  let starts = 0;
  const source = withBusinessSpace({ ...createFixtureBusinessDataSource(), ensureSpace: async () => { starts++; throw new Error("must not bootstrap"); } }, () => "es-419");
  const note = await source.captureNote({ text: "nota original" }, "note-once");
  assert.equal((await source.captures("original"))[0].draft_id, note.draft_id);
  assert.equal(starts, 0);
});

test("synthetic notes keep sparse facts, immutable sources, version-bound append and current replay", async () => {
  const source = fixture();
  const input = { text: "  pintura sin recibo\n  " };
  const first = await source.captureNote(input, "one");
  assert.equal(first.facts.amount.state, "unknown");
  assert.equal(first.facts.kind.state, "unknown");
  assert.ok(Object.entries({ origin: "default", verified: false, value: "DOP" }).every(([key, expected]) => (first.facts.currency as unknown as Record<string, unknown>)[key] === expected));
  assert.ok(Object.entries({ kind: "message", channel: "web", text: input.text }).every(([key, expected]) => (first.sources[0] as unknown as Record<string, unknown>)[key] === expected));
  assert.equal(first.history[0].actor.actor_kind, "member");
  assert.equal(first.approval_result, null);
  const appended = await source.captureNote({ text: "  mi dinero %_  ", draft: { draft_id: first.draft_id, version: first.version } }, "two");
  assert.deepEqual(appended.facts, first.facts);
  assert.equal(appended.version, 2);
  assert.deepEqual(appended.sources[0], first.sources[0]);
  assert.equal((await source.captureNote(input, "one")).version, 2);
  const hits = await source.captures();
  assert.equal(new Set(hits.map((hit) => hit.source_id)).size, 2);
  assert.deepEqual(hits.map((hit) => hit.draft_id), [first.draft_id, first.draft_id]);
  assert.equal((await source.captures("%_"))[0].text, "  mi dinero %_  ");
  await assert.rejects(source.captureNote({ text: "changed" }, "one"), { code: "idempotency_conflict" });
  await assert.rejects(source.captureNote({ text: "stale", draft: { draft_id: first.draft_id, version: 1 } }, "three"), { code: "stale_version" });
});

test("synthetic read-only and accepted dossiers reject append without changing their original sources", async () => {
  const source = fixture();
  const readOnly = await source.dossier(dossierFixtureIds.readOnly);
  await assert.rejects(source.captureNote({ text: "no", draft: { draft_id: readOnly.draft_id, version: readOnly.version } }, "denied"), { code: "permission_denied" });
  assert.deepEqual((await source.dossier(readOnly.draft_id)).sources, readOnly.sources);
  const accepted = await source.approveDraft(dossierFixtureIds.ready, 2);
  await assert.rejects(source.captureNote({ text: "no", draft: { draft_id: accepted.draft_id, version: accepted.version } }, "closed"), { code: "business_draft_not_open" });
  assert.deepEqual((await source.dossier(accepted.draft_id)).sources, accepted.sources);
});


test("actual nested Problem codes distinguish uncertain capture outcomes from rejected conflicts", async () => {
  const originalFetch = globalThis.fetch;
  const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  try {
    for (const code of ["business_action_unsettled", "outcome_unknown", "stale_version", "idempotency_conflict", "unknown"]) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail: { type: `https://api.argus.app/problems/${code.replaceAll("_", "-")}`, title: "Capture problem", status: 409, detail: code, code, request_id: "test-request" } }), { status: 409, headers: { "Content-Type": "application/json" } });
      await assert.rejects(captureBusinessNote({ text: "same original" }, "same-key"), { status: 409, code });
      assert.equal(captureOutcomeUnknown(409, code), code === "business_action_unsettled" || code === "outcome_unknown");
    }
    assert.equal(captureOutcomeUnknown(409, undefined), false);
    assert.equal(captureOutcomeUnknown(403, "outcome_unknown"), false);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  }
});
