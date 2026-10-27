import assert from "node:assert/strict";
import { test } from "bun:test";
import { applyOrganizationPreview, emptyOrganizationPreview, undoOrganizationPreview } from "@/components/business-app/recepcion/reception-organization-preview";
import { emptyReceptionFilters, receptionFilterMatches, receptionSenderIdentity, receptionArrivedInPeriod } from "@/components/business-app/recepcion/reception-filters";
import { receptionRows } from "@/components/business-app/recepcion/reception-model";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";

test("archive and seen are independent, reversible and idempotent organization facts", () => {
  const initial = emptyOrganizationPreview();
  const unseen = applyOrganizationPreview(initial, ["receipt:1", "email:1"], "unseen");
  const archived = applyOrganizationPreview(unseen, ["receipt:1"], "archive");
  assert.deepEqual(archived, { archived: ["receipt:1"], unseen: ["receipt:1", "email:1"] });
  assert.deepEqual(applyOrganizationPreview(archived, ["receipt:1"], "archive"), archived);
  const restored = applyOrganizationPreview(archived, ["receipt:1"], "restore");
  assert.deepEqual(restored, unseen);
  assert.deepEqual(applyOrganizationPreview(archived, ["receipt:1"], "seen"), { archived: ["receipt:1"], unseen: ["email:1"] });
  assert.deepEqual(initial, emptyOrganizationPreview());
});

test("filters use OR within groups and AND between groups without changing receipts", async () => {
  const source = createFixtureBusinessDataSource({ chatAvailable: true });
  const receipts = await source.receipts("all");
  const rows = receptionRows(receipts, [], await source.emailDeliveries());
  const before = structuredClone(rows);
  const known = rows.find(row => receptionSenderIdentity(row));
  assert.ok(known);
  const sender = receptionSenderIdentity(known)!;
  const filters = { channels: ["whatsapp", "email"] as const, senders: [sender.id], states: [] };
  const selected = rows.filter(row => receptionFilterMatches(row, { ...filters, channels: [...filters.channels] }));
  assert(selected.length > 0);
  assert(selected.every(row => receptionSenderIdentity(row)?.id === sender.id && ["email", "whatsapp"].includes(row.source)));
  const combined = rows.filter(row => receptionFilterMatches(row, { ...emptyReceptionFilters(), states: ["processing", "attention"] }));
  const single = ["processing", "attention"].flatMap(state => rows.filter(row => receptionFilterMatches(row, { ...emptyReceptionFilters(), states: [state as "processing" | "attention"] })));
  assert.deepEqual(new Set(combined.map(row => `${row.kind}:${row.id}`)), new Set(single.map(row => `${row.kind}:${row.id}`)));
  assert(rows.every(row => receptionFilterMatches(row, emptyReceptionFilters())));
  assert.deepEqual(rows, before);
  const merchant = rows.find(row => row.kind === "receipt" && row.receipt.merchant && !row.sender);
  assert.ok(merchant);
  assert.equal(receptionSenderIdentity(merchant), null);
});


test("arrival dates are inclusive and all dates keeps older unresolved arrivals", async () => {
  const source = createFixtureBusinessDataSource({ chatAvailable: true });
  const row = receptionRows(await source.receipts("all"), [], [])[0];
  const period = { key: "custom" as const, from: "2026-10-01", to: "2026-10-03" };
  for (const day of ["2026-10-01", "2026-10-03"]) assert(receptionArrivedInPeriod({ ...row, receivedAt: day + "T12:00:00" }, period));
  assert.equal(receptionArrivedInPeriod({ ...row, receivedAt: "2026-09-30T12:00:00" }, period), false);
  assert.equal(receptionArrivedInPeriod({ ...row, receivedAt: "2026-10-04T12:00:00" }, period), false);
  assert(receptionArrivedInPeriod({ ...row, receivedAt: "2020-01-01T12:00:00" }, { key: "all", from: "", to: null }));
});


test("undo restores mixed prior values only for the affected organization field and selected arrivals", () => {
  const before = { archived: ["receipt:a"], unseen: ["receipt:b"] };
  const seen = applyOrganizationPreview(before, ["receipt:a", "receipt:b"], "seen");
  const later = applyOrganizationPreview(applyOrganizationPreview(seen, ["receipt:c"], "archive"), ["receipt:c"], "unseen");
  const undone = undoOrganizationPreview(later, before, ["receipt:a", "receipt:b"], "seen");
  assert.deepEqual(undone.archived, ["receipt:a", "receipt:c"]);
  assert.deepEqual(new Set(undone.unseen), new Set(["receipt:b", "receipt:c"]));
  assert.deepEqual(undoOrganizationPreview(undone, before, ["receipt:a", "receipt:b"], "seen"), undone);
  for (const action of ["archive", "restore", "seen", "unseen"] as const) {
    assert.deepEqual(undoOrganizationPreview(applyOrganizationPreview(before, ["receipt:a", "receipt:b"], action), before, ["receipt:a", "receipt:b"], action), before);
  }
});
