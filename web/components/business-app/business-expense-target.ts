import type { BusinessExpense } from "@/lib/business-api";
import type { BusinessPanelState } from "./BusinessWorkspace";

/**
 * The record a saved expense opens: its receipt when it names exactly one,
 * else the draft that recorded it, else its own plain detail. Every row and
 * search hit opens something.
 */
export function expensePanel(expense: Pick<BusinessExpense, "id" | "receipt_id" | "draft_id">): BusinessPanelState {
  if (expense.receipt_id) return { kind: "receipt", receiptId: expense.receipt_id };
  if (expense.draft_id) return { kind: "draft", draftId: expense.draft_id };
  return { kind: "expense", expenseId: expense.id };
}
