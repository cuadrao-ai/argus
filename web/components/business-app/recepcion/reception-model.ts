import type { BusinessCapture, ReceiptChannel, ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import { bandejaReceipts } from "../bandeja-order";
import { bandejaEmails, openNotesByDraft, type BandejaEmail, type OpenNote } from "../inbox-count";

export type ReceptionView = "all" | "review" | "processing" | "attention";
export type ReceptionSource = ReceiptChannel | "note";
export type ReceptionRow =
  | { kind: "message"; id: string; receivedAt: string; source: "whatsapp"; text: string; sender: string; preview: true }
  | { kind: "receipt"; id: string; receivedAt: string; source: ReceiptChannel; receipt: ReceiptSummary; sender: string | null; reviewNote?: string | null }
  | { kind: "note"; id: string; receivedAt: string; source: "note"; note: OpenNote }
  | { kind: "email"; id: string; receivedAt: string; source: "email"; email: BandejaEmail };

function noteText(value: string | null | undefined): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/** The server's review note for a row, or null when it sent none. */
export function bandejaReviewNote(row: ReceptionRow): string | null {
  if (row.kind === "email") return noteText(row.email.delivery.review_note);
  if (row.kind === "receipt") return noteText(row.reviewNote);
  return null;
}

export function receptionRows(receipts: readonly ReceiptSummary[], captures: readonly BusinessCapture[], emails: readonly BusinessEmailDelivery[], inbox?: readonly { id: string; items: readonly { id: string; review_note?: string | null }[] }[] | null): ReceptionRow[] {
  const fromInbox = new Map<string, string>();
  for (const item of inbox?.find((group) => group.id === "bandeja")?.items ?? []) {
    const note = noteText(item.review_note);
    if (note) fromInbox.set(item.id, note);
  }
  const noteFor = (id: string, own: string | null | undefined) => fromInbox.get(id) ?? noteText(own);
  const rows: ReceptionRow[] = [
    ...bandejaReceipts(receipts).map((receipt): ReceptionRow => ({
      kind: "receipt", id: receipt.id, receivedAt: receipt.received_at, source: receipt.channel, receipt,
      sender: emails.find(email => receipt.email_delivery_ids?.includes(email.id))?.sender ?? null,
      reviewNote: receipt.email_delivery_ids?.map((id) => noteFor(id, emails.find(email => email.id === id)?.review_note)).find((note): note is string => note !== null) ?? null,
    })),
    ...openNotesByDraft(captures).map((note): ReceptionRow => ({ kind: "note", id: note.draftId, receivedAt: note.receivedAt, source: "note", note })),
    ...bandejaEmails(emails).map((email): ReceptionRow => {
      const reviewNote = noteFor(email.delivery.id, email.delivery.review_note);
      const delivery = reviewNote && reviewNote !== email.delivery.review_note ? { ...email.delivery, review_note: reviewNote } : email.delivery;
      return { kind: "email", id: email.delivery.id, receivedAt: email.delivery.received_at, source: "email", email: delivery === email.delivery ? email : { ...email, delivery } };
    }),
  ];
  return rows.sort((a, b) => b.receivedAt.localeCompare(a.receivedAt) || a.id.localeCompare(b.id));
}

export function receptionMatches(row: ReceptionRow, view: ReceptionView): boolean {
  if (view === "all") return true;
  if (row.kind === "message") return false;
  if (row.kind === "note") return view === "review";
  if (row.kind === "email") return view === "processing" ? row.email.standing === "reading" : view === "attention" && row.email.standing === "no_receipt";
  const membership = row.receipt.bandeja;
  return view === "review" ? membership?.por_revisar === true : view === "processing" ? membership?.leyendo === true : membership?.con_problema === true;
}

export function receptionSender(row: ReceptionRow): string | null {
  return row.kind === "email" ? row.email.delivery.sender || null : row.kind === "receipt" || row.kind === "message" ? row.sender : null;
}

export function receptionSearchText(row: ReceptionRow): string {
  if (row.kind === "message") return `${row.text} ${row.sender}`;
  if (row.kind === "note") return row.note.text;
  if (row.kind === "email") return [row.email.delivery.sender, row.email.delivery.subject].filter(Boolean).join(" ");
  return [row.receipt.merchant, row.receipt.filename, row.sender].filter(Boolean).join(" ");
}

/** Actions name only a next step the existing dossier supports. */
export function receptionAction(row: ReceptionRow, canPrepare: boolean): "action_resolve" | "action_review" | "action_detail" | "action_note" {
  if (row.kind === "note" || row.kind === "message") return "action_note";
  if (!canPrepare) return "action_detail";
  if (receptionMatches(row, "attention")) {
    const actionable = row.kind === "receipt" ? row.receipt.enterable || row.receipt.preparable : row.kind === "email" && row.email.delivery.retryable && !row.email.delivery.waiting;
    return actionable ? "action_resolve" : "action_detail";
  }
  return receptionMatches(row, "review") ? "action_review" : "action_detail";
}


/** Documents use their captured identity; delivery exceptions use their own subject or filename. */
export function receptionDocumentTitle(row: ReceptionRow, labels: { untitled: string; pending: string; exception: string; text: string }): string {
  if (row.kind === "email") {
    const delivery = row.email.delivery;
    const filename = delivery.parts.length === 1 ? delivery.parts[0].filename?.trim() : null;
    return delivery.subject?.trim() || filename || (row.email.standing === "reading" ? labels.pending : labels.exception);
  }
  if (row.kind === "note" || row.kind === "message") {
    const text = (row.kind === "note" ? row.note.text : row.text).trim().split(/\r?\n/)[0].replace(/\s+/g, " ");
    return text ? text.length > 90 ? `${text.slice(0, 89).trimEnd()}…` : text : labels.text;
  }
  const receipt = row.receipt;
  if (receipt.attention === "unreadable") return receipt.filename?.trim() || labels.untitled;
  return receipt.merchant?.trim() || receipt.filename?.trim() || labels.untitled;
}

/** Explicit synthetic example, never a classifier for incoming messages. */
export function receptionNoteExample(text: string, receivedAt: string): Extract<ReceptionRow, { kind: "message" }> {
  return { kind: "message", id: "preview-whatsapp-note", receivedAt, source: "whatsapp", text, sender: "+1 809 555 0147", preview: true };
}
