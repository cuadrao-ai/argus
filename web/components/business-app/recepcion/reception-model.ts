import type { BusinessCapture, ListoItem, ReceiptChannel, ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { bandejaReceipts } from "../bandeja-order";
import { bandejaEmails, openNotesByDraft, type BandejaEmail, type OpenNote } from "../inbox-count";

export type ReceptionView = "all" | "attention" | "listos" | "eliminados";
export type ReceptionSource = ReceiptChannel | "note";
export type ReceptionRow =
  | { kind: "receipt"; id: string; receivedAt: string; source: ReceiptChannel; receipt: ReceiptSummary; sender: string | null }
  | { kind: "note"; id: string; receivedAt: string; source: "note"; note: OpenNote }
  | { kind: "email"; id: string; receivedAt: string; source: "email"; email: BandejaEmail };

export function receptionRows(receipts: readonly ReceiptSummary[], captures: readonly BusinessCapture[], emails: readonly BusinessEmailDelivery[]): ReceptionRow[] {
  const rows: ReceptionRow[] = [
    ...bandejaReceipts(receipts).map((receipt): ReceptionRow => ({
      kind: "receipt", id: receipt.id, receivedAt: receipt.received_at, source: receipt.channel, receipt,
      sender: emails.find(email => receipt.email_delivery_ids?.includes(email.id))?.sender ?? null,
    })),
    ...openNotesByDraft(captures, true).map((note): ReceptionRow => ({ kind: "note", id: note.draftId, receivedAt: note.receivedAt, source: "note", note })),
    ...bandejaEmails(emails).map((email): ReceptionRow => ({ kind: "email", id: email.delivery.id, receivedAt: email.delivery.received_at, source: "email", email })),
  ];
  return rows.sort((a, b) => b.receivedAt.localeCompare(a.receivedAt) || a.id.localeCompare(b.id));
}

/** The server's groups. A note is never Listos, and an email waits with what needs attention until it is read, as the counts do. A row still being read shows only on Todos. */
export function receptionMatches(row: ReceptionRow, view: ReceptionView): boolean {
  const deleted = row.kind === "receipt" ? row.receipt.bandeja_group?.group === "eliminados" : row.kind === "note" && row.note.bandeja_group?.group === "eliminados";
  if (view === "eliminados") return deleted;
  if (deleted) return false;
  if (view === "all") return true;
  const group = row.kind === "receipt" ? row.receipt.bandeja_group?.group : row.kind === "email" && row.email.standing === "reading" ? "reading" : "attention";
  return group === (view === "listos" ? "listo" : "attention");
}

export function receptionSender(row: ReceptionRow): string | null {
  return row.kind === "email" ? row.email.delivery.sender || null : row.kind === "receipt" ? row.sender : null;
}

export function receptionSearchText(row: ReceptionRow): string {
  if (row.kind === "note") return row.note.text;
  if (row.kind === "email") return [row.email.delivery.sender, row.email.delivery.subject].filter(Boolean).join(" ");
  return [row.receipt.merchant, row.receipt.filename, row.sender].filter(Boolean).join(" ");
}

/** What a Listos row names to approval, or null for any other row. */
export function listoItem(row: ReceptionRow): ListoItem | null {
  if (row.kind !== "receipt") return null;
  const { group, draft_id, version } = row.receipt.bandeja_group ?? {};
  return group === "listo" && draft_id && version != null ? { draft_id, version } : null;
}

/** The one thing every row does: it opens its own record. */
export function receptionTarget(row: ReceptionRow): BusinessPanelState {
  if (row.kind === "receipt") return row.receipt.expense_id ? { kind: "expense", expenseId: row.receipt.expense_id } : { kind: "receipt", receiptId: row.id, list: "inbox" };
  if (row.kind === "note") return { kind: "draft", draftId: row.id, list: "inbox" };
  return { kind: "email", emailId: row.id };
}

/** Documents use their captured identity; delivery exceptions use their own subject or filename. */
export function receptionDocumentTitle(row: ReceptionRow, labels: { untitled: string; pending: string; exception: string; text: string }): string {
  if (row.kind === "email") {
    const delivery = row.email.delivery;
    const filename = delivery.parts.length === 1 ? delivery.parts[0].filename?.trim() : null;
    return delivery.subject?.trim() || filename || (row.email.standing === "reading" ? labels.pending : labels.exception);
  }
  if (row.kind === "note") {
    const text = row.note.text.trim().split(/\r?\n/)[0].replace(/\s+/g, " ");
    return text ? text.length > 90 ? `${text.slice(0, 89).trimEnd()}…` : text : labels.text;
  }
  const receipt = row.receipt;
  if (receipt.attention === "unreadable") return receipt.filename?.trim() || labels.untitled;
  return receipt.merchant?.trim() || receipt.filename?.trim() || labels.untitled;
}
