import type { BusinessAccount, BusinessWorkspaceInfo } from "@/lib/business-api";

/**
 * The currencies a receipt's picker offers: the ones the Business works in, plus
 * the receipt's own when it is another. The loaded workspace owns the list; a record
 * opened before the workspace loaded falls back to its own accounts' currencies.
 */
export function receiptCurrencyOptions(
  workspace: Pick<BusinessWorkspaceInfo, "currencies"> | null,
  accounts: readonly BusinessAccount[],
  own: string | null,
): string[] {
  const worked = workspace ? workspace.currencies : accounts.map((account) => account.currency);
  return [...new Set([...worked, ...(own ? [own] : [])])];
}
