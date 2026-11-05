import assert from "node:assert/strict";
import { afterAll, test } from "bun:test";
import { requestBusinessTransfer, respondToBusinessTransfer } from "@/lib/business-transfer-api";
const original = { fetch: globalThis.fetch, auth: process.env.NEXT_PUBLIC_MOCK_AUTH };
const spaceId = "c9ee4f5a-71a4-4617-b370-c46d0ac7aefd";
const transferId = "38c5385b-d7d0-45c7-942c-fb027eeb5536";
const grantId = "7d8e2d48-c728-49ae-a020-e5d044da70c2";
process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
afterAll(() => { globalThis.fetch = original.fetch; if (original.auth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = original.auth; });

test("transfer request and retry keep the actual member, exact name and original key", async () => {
  const calls: unknown[] = [];
  globalThis.fetch = async (url, init) => {
    calls.push([new URL(String(url)).pathname, JSON.parse(String(init?.body)), new Headers(init?.headers).get("Idempotency-Key")]);
    return Response.json({ id: transferId, space_id: spaceId, status: "pending" });
  };
  const command = { spaceId, targetGrantId: grantId, confirmation: "Taller Luna ", idempotencyKey: "transfer-original" };
  await requestBusinessTransfer(command);
  await requestBusinessTransfer(command);
  assert.deepEqual(calls, Array(2).fill([`/api/v1/business/spaces/${spaceId}/ownership-transfers`, { target_grant_id: grantId, confirmation: "Taller Luna " }, "transfer-original"]));
});

for (const action of ["accept", "decline", "withdraw"] as const) test(`${action} addresses the same pending command without inventing a person`, async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(new URL(String(url)).pathname, `/api/v1/business/ownership-transfers/${transferId}/${action}`);
    assert.equal(init?.body, undefined);
    return Response.json({ id: transferId, space_id: spaceId, status: action === "accept" ? "accepted" : action === "decline" ? "declined" : "cancelled" });
  };
  assert.equal((await respondToBusinessTransfer({ transferId, action })).id, transferId);
});

test("unrecognized transfer states are refused at the boundary", async () => {
  globalThis.fetch = async () => Response.json({ id: transferId, space_id: spaceId, status: "owner_changed_in_browser" });
  await assert.rejects(respondToBusinessTransfer({ transferId, action: "accept" }));
});

test("a response for another command or Business is refused", async () => {
  globalThis.fetch = async () => Response.json({ id: grantId, space_id: spaceId, status: "accepted" });
  await assert.rejects(respondToBusinessTransfer({ transferId, action: "accept" }));
  globalThis.fetch = async () => Response.json({ id: transferId, space_id: grantId, status: "pending" });
  await assert.rejects(requestBusinessTransfer({ spaceId, targetGrantId: grantId, confirmation: "Taller Luna", idempotencyKey: "request" }));
});
