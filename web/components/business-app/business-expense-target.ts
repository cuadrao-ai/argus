import type { BusinessExpense } from "@/lib/business-api";
import type { RecordTarget } from "./transacciones/transacciones-model";

/**
 * The record a saved expense opens: its receipt when it names exactly one,
 * else the draft that recorded it, else its own id, which asks the server for
 * the receipt or draft behind it. Each opens the one dossier.
 */
export function expensePanel(expense: Pick<BusinessExpense, "id" | "receipt_id" | "draft_id">): RecordTarget {
  if (expense.receipt_id) return { kind: "receipt", receiptId: expense.receipt_id, list: "transactions" };
  if (expense.draft_id) return { kind: "draft", draftId: expense.draft_id, list: "transactions" };
  return { kind: "expense", expenseId: expense.id };
}
