import assert from "node:assert/strict";
import { afterEach, test } from "bun:test";

import {
  EmailSenderRequestError,
  createEmailSenderStub,
  emailSendersUseStub,
  groupSenders,
  listEmailSenders,
  liveEmailSenderClient,
  parseEmailSenderList,
  pendingSenderCount,
  senderCheckFailed,
  senderForView,
  senderMoves,
} from "@/lib/business-email";

const previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
const previousNode = process.env.NODE_ENV;
const originalFetch = globalThis.fetch;

afterEach(() => {
  const restore = { NODE_ENV: previousNode, NEXT_PUBLIC_MOCK_AUTH: previousMock };
  for (const [key, value] of Object.entries(restore)) {
    if (value === undefined) delete process.env[key];
    else Object.assign(process.env, { [key]: value });
  }
  globalThis.fetch = originalFetch;
});

const oldServer = { id: "old", kind: "address", value: "old@negocio.example", status: "authorized", last_auth_result: "aligned" };
const handAdded = { id: "hand", kind: "domain", value: "proveedor.example", status: "pending", tag: null, last_auth_result: null, last_seen_at: null };

test("only a failed check is flagged, whatever the auth result says", () => {
  const passed = { id: "yes", kind: "address", value: "ok@negocio.example", status: "authorized", tag: "verified", last_auth_result: "failed" };
  const failed = { id: "no", kind: "address", value: "avisos@correo.example", status: "pending", tag: "unverified", last_auth_result: "aligned" };
  const [older, hand, yes, no] = parseEmailSenderList({ items: [oldServer, handAdded, passed, failed] });
  assert.deepEqual([older, hand, yes, no].map((item) => senderCheckFailed(senderForView(item!).tag)), [false, false, false, true]);
  assert.equal("last_auth_result" in senderForView(older!), false);
  assert.equal(older!.last_auth_result, "aligned");
});

test.each([
  ["pending", false, ["authorized", "blocked"]],
  ["authorized", false, ["blocked"]],
  ["blocked", false, ["authorized"]],
  ["pending", true, ["authorized"]],
  ["authorized", true, []],
  ["blocked", true, ["authorized"]],
] as const)("%s with default_approved %j moves to %j", (status, default_approved, moves) => {
  assert.deepEqual(senderMoves({ status, default_approved }), moves);
});

test("default_approved is optional on the wire, and a missing one reads as false", () => {
  const items = parseEmailSenderList({ items: [oldServer, { ...oldServer, id: "owner", default_approved: true }, { ...oldServer, id: "member", default_approved: false }] });
  const views = items.map(senderForView);
  assert.deepEqual(views.map((view) => view.default_approved), [false, true, false]);
  assert.deepEqual(views.map(senderMoves), [["blocked"], [], ["blocked"]]);
});

test("senders group by status and keep the order they arrived in", () => {
  const items = parseEmailSenderList({
    items: [
      { id: "b", kind: "address", value: "blocked@negocio.example", status: "blocked", tag: "unverified" },
      { id: "p2", kind: "address", value: "second@negocio.example", status: "pending", tag: "unverified" },
      { id: "a", kind: "address", value: "owner@negocio.example", status: "authorized", tag: "verified" },
      { id: "p1", kind: "address", value: "first@negocio.example", status: "pending", tag: "verified" },
    ],
  });
  const grouped = groupSenders(items.map(senderForView));
  assert.deepEqual(grouped.pending.map((item) => item.value), ["second@negocio.example", "first@negocio.example"]);
  assert.deepEqual(grouped.authorized.map((item) => item.value), ["owner@negocio.example"]);
  assert.deepEqual(grouped.blocked.map((item) => item.value), ["blocked@negocio.example"]);
  assert.equal(pendingSenderCount(items), 2);
  assert.equal(pendingSenderCount([{ ...items[2] }]), 0);
});

test("a list without the sender envelope is refused", () => {
  assert.throws(() => parseEmailSenderList([]), EmailSenderRequestError);
  assert.throws(() => parseEmailSenderList({ items: [{ id: "x", kind: "address", value: "a@b.example", status: "pending", tag: "gray" }] }), EmailSenderRequestError);
});

test("the stub stays off outside the dev mock preview", () => {
  Object.assign(process.env, { NODE_ENV: "production", NEXT_PUBLIC_MOCK_AUTH: "true" });
  assert.equal(emailSendersUseStub(), false);
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "false" });
  assert.equal(emailSendersUseStub(), false);
  Object.assign(process.env, { NEXT_PUBLIC_MOCK_AUTH: "true" });
  assert.equal(emailSendersUseStub(), true);
});

test("the dev stub can fail a status change and can return an empty list", async () => {
  const failing = createEmailSenderStub("fail");
  const pending = await failing.list();
  assert.equal(pending[0]?.status, "pending");
  await assert.rejects(failing.update({ kind: "address", value: pending[0]!.value, status: "authorized" }), (error: EmailSenderRequestError) => error.status === 422 && error.code === "email_sender_invalid");
  assert.deepEqual(await createEmailSenderStub("empty").list(), []);
  const settled = await createEmailSenderStub("settled").list();
  assert.equal(settled.some((item) => item.status === "pending"), false);
  assert.ok(settled.some((item) => item.status === "authorized"));
  assert.ok(settled.some((item) => item.status === "blocked"));
});

test("200 and 201 both return the sender item with or without default_approved, and the post never sends pending", async () => {
  Object.assign(process.env, { NEXT_PUBLIC_MOCK_AUTH: "true" });
  const calls: { method: string; body: unknown }[] = [];
  const item = { id: "s1", kind: "address", value: "nueva@negocio.example", status: "authorized", tag: "unverified", last_auth_result: "none", last_seen_at: "2026-10-30T00:00:00Z" };
  let posts = 0;
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (method === "GET") return Response.json({ items: [{ id: "old", kind: "address", value: "old@negocio.example", status: "blocked" }] });
    posts += 1;
    return posts === 1 ? Response.json(item, { status: 200 }) : Response.json({ ...item, default_approved: true }, { status: 201 });
  }) as typeof fetch;
  const listed = await listEmailSenders();
  assert.deepEqual(listed, [{ id: "old", kind: "address", value: "old@negocio.example", status: "blocked", default_approved: false }]);
  const updated = await liveEmailSenderClient.update({ kind: "address", value: "nueva@negocio.example", status: "authorized" });
  const created = await liveEmailSenderClient.update({ kind: "address", value: "nueva@negocio.example", status: "blocked" });
  assert.deepEqual(updated, { ...item, default_approved: false });
  assert.deepEqual(created, { ...item, default_approved: true });
  assert.deepEqual(calls.map((call) => call.body), [
    null,
    { kind: "address", value: "nueva@negocio.example", status: "authorized" },
    { kind: "address", value: "nueva@negocio.example", status: "blocked" },
  ]);
  globalThis.fetch = (async () => Response.json({ code: "email_sender_domain_refused" }, { status: 422 })) as typeof fetch;
  await assert.rejects(liveEmailSenderClient.update({ kind: "domain", value: "proveedor.example", status: "blocked" }), (error: EmailSenderRequestError) => error.status === 422);
});
