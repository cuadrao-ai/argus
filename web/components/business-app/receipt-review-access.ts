import type { BusinessAccount, ReceiptDetail } from "@/lib/business-api";

/** What the signed-in person may do with a receipt that has no prepared record, read from the API's nested record context. Absent context means read-only. */
export function receiptReviewAccess(detail: Pick<ReceiptDetail, "record_context">): { accounts: BusinessAccount[]; canPrepare: boolean; canApprove: boolean } {
  const context = detail.record_context;
  const capabilities = context?.capabilities ?? [];
  return { accounts: context?.accounts ?? [], canPrepare: capabilities.includes("prepare"), canApprove: capabilities.includes("approve") };
}
