import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import type { TFunction } from "i18next";
import { activitySearchGroup } from "@/components/business-app/actividad/activity-search";
import { activityTarget } from "@/components/business-app/actividad/activity-words";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { BusinessActivityItem } from "@/lib/business-activity-api";

// One owner says where an Actividad row leads (#2107). The Actividad screen and the search window both read it.
type Subject = BusinessActivityItem["object"];
const RECEIPT: Subject = { kind: "receipt", id: "rcpt-1", label: "factura.pdf" };
const DRAFT: Subject = { kind: "draft", id: "draft-1", label: "Ferretería La Esquina" };

const row = (action: string, object: Subject): BusinessActivityItem => ({
  id: `${action}:${object?.kind ?? "none"}:${object?.purged ? "purged" : "kept"}`,
  occurred_at: "2026-11-14T15:00:00Z",
  actor: { display_name: "Lucía Peña", kind: "member" },
  action,
  object,
});

const openReceipt: BusinessPanelState = { kind: "receipt", receiptId: "rcpt-1" };
const openDraft: BusinessPanelState = { kind: "draft", draftId: "draft-1" };

const CASES: readonly (readonly [string, BusinessActivityItem, BusinessPanelState | null])[] = [
  ["an upload opens its receipt", row("receipt_upload", RECEIPT), openReceipt],
  ["a confirmed document opens its receipt", row("receipt_confirm", RECEIPT), openReceipt],
  ["a reviewed record opens its record", row("review_draft", DRAFT), openDraft],
  ["an approval opens its record", row("approve_expense", DRAFT), openDraft],
  ["an edit opens its record", row("edit_current_note", DRAFT), openDraft],
  ["an action the screen does not know yet opens the record it names", row("a_new_action", DRAFT), openDraft],
  ["a deleted document opens Eliminados", row("delete_document", RECEIPT), { kind: "inbox", view: "eliminados" }],
  ["a restored receipt opens beside the Bandeja", row("restore_document", RECEIPT), { ...openReceipt, list: "inbox" }],
  ["a restored draft opens beside the Bandeja", row("restore_document", DRAFT), { ...openDraft, list: "inbox" }],
  ["a purged receipt opens nothing", row("receipt_upload", { kind: "receipt", id: "rcpt-1", purged: true }), null],
  ["a purged record opens nothing", row("approve_expense", { kind: "draft", id: "draft-1", purged: true }), null],
  ["a purged deleted document opens nothing", row("delete_document", { kind: "receipt", id: "rcpt-1", purged: true }), null],
  ["an access change opens nothing", row("change_role", { kind: "grant", id: "grant-1", label: "Ana" }), null],
  ["an invitation opens nothing", row("invite_access", { kind: "invite", id: "invite-1" }), null],
  ["a Business setting opens nothing", row("set_business_rnc", null), null],
  ["an upload the server names no receipt for opens nothing", row("receipt_upload", null), null],
];

describe("where an Actividad row leads", () => {
  for (const [name, item, expected] of CASES) {
    test(name, () => assert.deepEqual(activityTarget(item), expected));
  }
});

test("a search result opens exactly what its Actividad row opens, and nothing when the row opens nothing", () => {
  const opened: BusinessPanelState[] = [];
  const t = ((key: string | string[]) => (Array.isArray(key) ? key[0] : key)) as unknown as TFunction;
  const items = CASES.map(([, item]) => item);
  const group = activitySearchGroup({ t, locale: "es-419", openPanel: (panel) => opened.push(panel) }, { items, next_cursor: null }, async () => ({ items: [], next_cursor: null }));
  assert.equal(group.hits.length, CASES.length);
  for (const [name, item, expected] of CASES) {
    const hit = group.hits.find((candidate) => candidate.id === item.id);
    assert.ok(hit, name);
    opened.length = 0;
    hit.open?.();
    assert.deepEqual(opened, expected ? [expected] : [], name);
    assert.equal(Boolean(hit.open), expected !== null, `${name}: a result that opens nothing is not offered as one that does`);
    assert.deepEqual(opened, [activityTarget(item)].filter(Boolean), `${name}: the row's own target`);
  }
});
