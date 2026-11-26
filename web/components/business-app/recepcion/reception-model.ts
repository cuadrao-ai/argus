import type { BandejaGroup, BandejaLabel, BusinessCapture, ListoItem, ReceiptChannel, ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import type { SentBy } from "@/lib/sent-by";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { receiptDeleteTarget, type DeleteDocumentTarget } from "../DocumentDeleteControls";
import { bandejaReceipts } from "../bandeja-order";
import { bandejaEmails, openNotesByDraft, type BandejaEmail, type OpenNote } from "../inbox-count";

export type ReceptionView = "all" | "attention" | "listos" | "eliminados";
export type ReceptionSource = ReceiptChannel | "note";
export function receptionChannelKey(channel: string): string {
  return channel === "web" ? "business.dossier.web" : `business.reception_preview.source_${channel}`;
}

export type ReceptionRow =
  | { kind: "receipt"; id: string; receivedAt: string; source: ReceiptChannel; receipt: ReceiptSummary }
  | { kind: "note"; id: string; receivedAt: string; source: "note"; note: OpenNote }
  | { kind: "email"; id: string; receivedAt: string; source: "email"; email: BandejaEmail };

export function receptionRows(receipts: readonly ReceiptSummary[], captures: readonly BusinessCapture[], emails: readonly BusinessEmailDelivery[]): ReceptionRow[] {
  const rows: ReceptionRow[] = [
    ...bandejaReceipts(receipts).map((receipt): ReceptionRow => ({ kind: "receipt", id: receipt.id, receivedAt: receipt.received_at, source: receipt.channel, receipt })),
    ...openNotesByDraft(captures, true).map((note): ReceptionRow => ({ kind: "note", id: note.draftId, receivedAt: note.receivedAt, source: "note", note })),
    ...bandejaEmails(emails).map((email): ReceptionRow => ({ kind: "email", id: email.delivery.id, receivedAt: email.delivery.received_at, source: "email", email })),
  ];
  return rows.sort((a, b) => b.receivedAt.localeCompare(a.receivedAt) || a.id.localeCompare(b.id));
}

/** What the server said of this row's place in the Bandeja: its group and its label. */
function rowBandeja(row: ReceptionRow): BandejaGroup | null | undefined {
  if (row.kind === "receipt") return row.receipt.bandeja_group;
  if (row.kind === "note") return row.note.bandeja_group;
  return row.email.delivery.bandeja_group;
}

/** The one word the list shows for this row, as the server chose it. */
export function rowLabel(row: ReceptionRow): BandejaLabel | null {
  return rowBandeja(row)?.label ?? null;
}

/** Every row sits in the tab its server group names, as the counts do. A row still being read shows only on Todos. */
export function receptionMatches(row: ReceptionRow, view: ReceptionView): boolean {
  const group = rowBandeja(row)?.group;
  if (view === "eliminados") return group === "eliminados";
  if (group === "eliminados") return false;
  if (view === "all") return true;
  return group === (view === "listos" ? "listo" : "attention");
}

/** Who the server says brought this row in; the web works out no sender of its own. */
export function receptionSentBy(row: ReceptionRow): SentBy | null {
  return (row.kind === "receipt" ? row.receipt.sent_by : row.kind === "note" ? row.note.sent_by : row.email.delivery.sent_by) ?? null;
}

export function receptionSearchText(row: ReceptionRow): string {
  if (row.kind === "note") return row.note.text;
  if (row.kind === "email") return [row.email.delivery.sender, row.email.delivery.subject].filter(Boolean).join(" ");
  const sender = row.receipt.sent_by;
  return [row.receipt.merchant, row.receipt.filename, sender?.person?.display_name, sender?.person?.email, sender?.address, sender?.phone_last4].filter(Boolean).join(" ");
}

/** What a Listos row names to approval, or null for any other row. */
export function listoItem(row: ReceptionRow): ListoItem | null {
  if (row.kind !== "receipt") return null;
  const { group, draft_id, version } = row.receipt.bandeja_group ?? {};
  return group === "listo" && draft_id && version != null ? { draft_id, version } : null;
}

/** The one thing every row does: it opens its own record. */
export function receptionTarget(row: ReceptionRow): BusinessPanelState {
  if (row.kind === "receipt") return { kind: "receipt", receiptId: row.id, list: "inbox" };
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

/** What the delete and purge dialogs show of a receipt or a note row. */
export function rowDeleteTarget(row: Exclude<ReceptionRow, { kind: "email" }>, state: string | null, unnamed: string): DeleteDocumentTarget {
  return row.kind === "receipt"
    ? receiptDeleteTarget(row.receipt, state, unnamed)
    : { id: row.id, name: row.note.text, merchant: null, family: null, date: null, amount: null, currency: null, filename: null, state };
}
