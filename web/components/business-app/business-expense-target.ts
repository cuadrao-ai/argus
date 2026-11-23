import type { BusinessExpense } from "@/lib/business-api";
import type { RecordTarget } from "./transacciones/transacciones-model";

/**
 * The record a saved expense opens: its receipt when it names exactly one,
 * else the draft that recorded it, else itself. All three open the one
 * dossier; a record with neither shows there read only.
 */
export function expensePanel(expense: Pick<BusinessExpense, "id" | "receipt_id" | "draft_id">): RecordTarget {
  if (expense.receipt_id) return { kind: "receipt", receiptId: expense.receipt_id, list: "transactions" };
  if (expense.draft_id) return { kind: "draft", draftId: expense.draft_id, list: "transactions" };
  return { kind: "expense", expenseId: expense.id };
}
