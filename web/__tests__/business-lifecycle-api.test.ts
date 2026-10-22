import assert from "node:assert/strict";
import { afterAll, test } from "bun:test";
import { closeBusinessSpace, reopenBusinessSpace, getClosedBusinessSpaces, getOwnedBusinessSpaces } from "@/lib/business-lifecycle-api";

const original = { fetch: globalThis.fetch, auth: process.env.NEXT_PUBLIC_MOCK_AUTH };
const spaceId = "c9ee4f5a-71a4-4617-b370-c46d0ac7aefd";
const result = { space_id: spaceId, name: "Taller Luna", closed_at: "2026-10-18T00:00:00Z", reopen_until: "2026-11-17T00:00:00Z" };
process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
afterAll(() => {
  globalThis.fetch = original.fetch;
  if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth;
});

test("close and retry preserve the explicit command key and exact typed name", async () => {
  const calls: { path: string; body: unknown; key: string | null }[] = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ path: new URL(String(url)).pathname, body: JSON.parse(String(init?.body)), key: new Headers(init?.headers).get("Idempotency-Key") });
    return Response.json(result);
  };
  const command = { spaceId, confirmation: "Taller Luna ", idempotencyKey: "close-original" };
  assert.deepEqual(await closeBusinessSpace(command), result);
  await closeBusinessSpace(command);
  assert.deepEqual(calls, Array(2).fill({ path: `/api/v1/business/spaces/${spaceId}/close`, body: { confirmation: "Taller Luna " }, key: "close-original" }));
});

test("reopen sends the same owner command transport with no new grant or invite payload", async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(new URL(String(url)).pathname, `/api/v1/business/spaces/${spaceId}/reopen`);
    assert.equal(new Headers(init?.headers).get("Idempotency-Key"), "reopen-original");
    assert.equal(init?.body, undefined);
    return Response.json({ ...result, closed_at: null, reopen_until: null });
  };
  assert.equal((await reopenBusinessSpace({ spaceId, idempotencyKey: "reopen-original" })).closed_at, null);
});

test("closed spaces are server facts and malformed payloads are refused", async () => {
  globalThis.fetch = async () => Response.json({ spaces: [result] });
  assert.deepEqual(await getClosedBusinessSpaces(), [result]);
  globalThis.fetch = async () => Response.json({ spaces: [{ ...result, reopen_until: "not-a-date" }] });
  await assert.rejects(getClosedBusinessSpaces());
});


test("owned preview preserves server counts, deadline, export windows and every eligibility reason", async () => {
  const reasons = [null, "account_unavailable", "not_editor", "email_unconfirmed", "owns_open_business"];
  const business = {
    space_id: spaceId, name: "Taller Luna", grant_id: "ee9c4550-1fe4-4e95-8fc2-8984d11e50f2",
    member_count: 5, reopen_until: "2026-11-20T17:45:00Z",
    export_windows: [{ start: "2024-01-01", end: "2024-12-31" }, { start: "2025-01-01", end: "2025-12-31" }],
    members: reasons.map((reason) => ({ grant_id: crypto.randomUUID(), name: "Rosa", eligible: reason === null, reason })),
  };
  globalThis.fetch = async () => Response.json({ spaces: [business] });
  assert.deepEqual(await getOwnedBusinessSpaces(), [business]);
  for (const changed of [
    { member_count: -1 }, { reopen_until: "not-a-date" },
    { export_windows: [{ start: "2025-02-30", end: "2025-03-01" }] },
    { members: [{ ...business.members[0], eligible: false, reason: null }] },
  ]) {
    globalThis.fetch = async () => Response.json({ spaces: [{ ...business, ...changed }] });
    await assert.rejects(getOwnedBusinessSpaces());
  }
});
