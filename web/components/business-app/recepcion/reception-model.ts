import type { BusinessCapture, ListoItem, ReceiptChannel, ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import { bandejaReceipts } from "../bandeja-order";
import { bandejaEmails, openNotesByDraft, type BandejaEmail, type OpenNote } from "../inbox-count";

export type ReceptionView = "all" | "attention" | "listos";
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
    ...openNotesByDraft(captures).map((note): ReceptionRow => ({ kind: "note", id: note.draftId, receivedAt: note.receivedAt, source: "note", note })),
    ...bandejaEmails(emails).map((email): ReceptionRow => ({ kind: "email", id: email.delivery.id, receivedAt: email.delivery.received_at, source: "email", email })),
  ];
  return rows.sort((a, b) => b.receivedAt.localeCompare(a.receivedAt) || a.id.localeCompare(b.id));
}

/** The server's two groups. A note and an email a row of its own are never Listos, so they sit with what needs attention, as the counts do. */
export function receptionMatches(row: ReceptionRow, view: ReceptionView): boolean {
  if (view === "all") return true;
  const group = row.kind === "receipt" ? row.receipt.bandeja_group?.group : "attention";
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

/** Actions name only a next step the existing dossier supports. */
export function receptionAction(row: ReceptionRow, canPrepare: boolean): "action_resolve" | "action_review" | "action_detail" | "action_note" {
  if (row.kind === "note") return "action_note";
  if (!canPrepare) return "action_detail";
  if (row.kind === "email") return row.email.standing === "no_receipt" && row.email.delivery.retryable && !row.email.delivery.waiting ? "action_resolve" : "action_detail";
  const { con_problema, por_revisar } = row.receipt.bandeja ?? {};
  if (con_problema) return row.receipt.enterable || row.receipt.preparable ? "action_resolve" : "action_detail";
  return por_revisar ? "action_review" : "action_detail";
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
