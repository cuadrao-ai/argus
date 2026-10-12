/** Received emails for a Business, as the API reports them. */

export type BusinessEmailIntake = { enabled: boolean; receiving_address: string | null };

export type BusinessEmailPart = {
  id: string;
  filename: string | null;
  media_type: string;
  state: "pending" | "captured" | "rejected";
  document_id: string | null;
  error_code: string | null;
};

export type BusinessEmailDelivery = {
  id: string;
  state: "received" | "processing" | "partial" | "captured" | "rejected";
  received_at: string;
  updated_at: string;
  original_document_id: string | null;
  retryable: boolean;
  subject: string | null;
  sender: string | null;
  sent_at: string | null;
  error_code: string | null;
  parts: BusinessEmailPart[];
};

export type BusinessEmailDetail = BusinessEmailDelivery & { text_body: string | null };

export function businessReceivingAddress(intake: BusinessEmailIntake): string | null {
  return intake.enabled ? intake.receiving_address : null;
}

/** A delivery still moving on the server is worth a short poll. */
export function emailDeliveriesNeedRefresh(items: readonly BusinessEmailDelivery[]): boolean {
  return items.some((item) => item.state === "received" || item.state === "processing" || item.state === "partial");
}

/**
 * Receipt ids that belong to an email and already have a captured attachment.
 * The Inbox shows those emails as one row with their attachments, not as a
 * separate ".eml" receipt beside its own attachments.
 */
export function receiptsGroupedUnderEmails(items: readonly BusinessEmailDelivery[]): ReadonlySet<string> {
  const grouped = new Set<string>();
  for (const delivery of items) {
    const captured = delivery.parts.some((part) => part.state === "captured" && part.document_id);
    if (captured && delivery.original_document_id) grouped.add(delivery.original_document_id);
  }
  return grouped;
}
