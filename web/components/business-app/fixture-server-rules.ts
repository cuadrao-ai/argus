import type { BandejaMembership, ReceiptActivity, ReceiptActivityCounts, ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery, BusinessEmailPart, EmailStanding } from "@/lib/business-email";

/**
 * The preview's copy of the server's Bandeja rules (`receipt_activity.py` and
 * `email_intake/standing.py`), so the sample answers in the server's shape.
 * Only the fixtures import it; the screens render what a source sends.
 */

const READ_FAILED = new Set(["unreadable", "ai_unavailable", "interrupted", "outcome_unknown", "source_unavailable", "other"]);

const closed = (view: ReceiptSummary) => view.status === "confirmed" || view.status === "dismissed";
const awaitingOwner = (view: ReceiptSummary) => !view.email_original && !closed(view);

/** The server projects activity from the row. The sample keeps its seeded "new" mark on a settled row until it is opened. */
export function projectActivity(view: ReceiptSummary): ReceiptActivity {
  if (view.email_original || closed(view)) return { state: "inactive", unread: false, completion_cursor: null };
  if (view.read_pending) return { state: "reading", unread: false, completion_cursor: null };
  if (view.status === "saved" || view.status === "queued") return { state: "saved_unread", unread: true, completion_cursor: null };
  if (view.status === "needs_attention" && (view.preparable || READ_FAILED.has(view.attention ?? ""))) return { state: "read_failed", unread: view.activity?.unread ?? false, completion_cursor: null };
  return { state: "ready", unread: view.activity?.unread ?? false, completion_cursor: view.activity?.completion_cursor ?? null };
}

function membership(view: ReceiptSummary, activity: ReceiptActivity): BandejaMembership {
  const leyendo = awaitingOwner(view) && activity.state === "reading";
  return {
    por_revisar: awaitingOwner(view) && view.status !== "queued" && view.status !== "preparing" && !view.read_pending && !leyendo && view.attention !== "unreadable",
    con_problema: awaitingOwner(view) && view.status === "needs_attention",
    leyendo,
  };
}

/** A receipt as the server lists it: its projected activity and its Bandeja flags. */
export function served<T extends ReceiptSummary>(view: T): T {
  const activity = projectActivity(view);
  return { ...view, activity, bandeja: membership(view, activity) };
}

/** The counts as the server sums them over every receipt, the notes no receipt carries and each email's standing. */
export function servedCounts(views: readonly ReceiptSummary[], notes: number, standings: readonly (EmailStanding | null)[]): ReceiptActivityCounts {
  const rows = views.map(served);
  const emails = standings.filter((standing) => standing !== null);
  const flagged = (bucket: keyof BandejaMembership) => rows.filter((row) => row.bandeja?.[bucket]).length;
  const reading = flagged("leyendo") + emails.filter((standing) => standing === "reading").length;
  const unread = rows.filter((row) => row.activity?.unread).length;
  return {
    reading_count: reading,
    unread_count: unread,
    presentation: reading ? "working" : unread ? "unread" : "none",
    pending_review_count: rows.filter(awaitingOwner).length + notes + emails.length,
    ready_to_review_count: flagged("por_revisar") + notes,
    needs_attention_count: flagged("con_problema") + emails.filter((standing) => standing === "no_receipt").length,
    confirmed_count: rows.filter((row) => !row.email_original && row.status === "confirmed").length,
    dismissed_count: rows.filter((row) => !row.email_original && row.status === "dismissed").length,
  };
}

type EmailInput = Omit<BusinessEmailDelivery, "standing" | "saved_receipt_count" | "no_receipt_reason">;

const repeat = (part: BusinessEmailPart) => Boolean(part.repeat_of_delivery_id || part.repeat_of_upload);

function standingOf(delivery: EmailInput, captured: readonly BusinessEmailPart[]): EmailStanding | null {
  const { parts, state } = delivery;
  if (delivery.original_document_id && !captured.length) return null;
  let outcome: EmailStanding;
  if (state === "rejected") outcome = "no_receipt";
  else if (state === "received" || state === "processing" || parts.some((part) => part.state === "pending")) outcome = "reading";
  else if (!parts.length || parts.some((part) => part.state === "rejected")) outcome = "no_receipt";
  else return null;
  return captured.some((part) => !repeat(part)) ? null : outcome;
}

function noReceiptReason(delivery: EmailInput): string {
  if (delivery.error_code && delivery.error_code !== "email_parts_rejected") return delivery.error_code;
  const refused = delivery.parts.find((part) => part.state === "rejected");
  if (refused?.error_code) return refused.error_code;
  return delivery.parts.length ? "email_parts_rejected" : "email_no_attachment";
}

/** An email delivery as the server serves it: where it stands, what it saved and why it brought nothing. */
export function servedEmail<T extends EmailInput>(delivery: T): T & Pick<BusinessEmailDelivery, "standing" | "saved_receipt_count" | "no_receipt_reason"> {
  const captured = delivery.parts.filter((part) => part.state === "captured" && part.document_id);
  const standing = standingOf(delivery, captured);
  return { ...delivery, standing, saved_receipt_count: captured.length, no_receipt_reason: standing === "no_receipt" ? noReceiptReason(delivery) : null };
}
