import assert from "node:assert/strict";
import { test } from "bun:test";

import { expensePanel } from "../components/business-app/business-expense-target";

test("a saved expense always opens something: its receipt, else the draft that recorded it, else its own detail", () => {
  assert.deepEqual(expensePanel({ id: "e1", receipt_id: "r1", draft_id: "d1" }), { kind: "receipt", receiptId: "r1", list: "expenses" });
  assert.deepEqual(expensePanel({ id: "e1", receipt_id: null, draft_id: "d1" }), { kind: "draft", draftId: "d1", list: "expenses" });
  assert.deepEqual(expensePanel({ id: "e1", receipt_id: null, draft_id: null }), { kind: "expense", expenseId: "e1" });
});
