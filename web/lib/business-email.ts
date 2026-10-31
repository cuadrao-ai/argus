/** Received emails for a Business, as the API reports them. */

export type BusinessEmailIntake = { enabled: boolean; receiving_address: string | null };

export type BusinessEmailPart = {
  id: string;
  filename: string | null;
  media_type: string;
  state: "pending" | "captured" | "rejected";
  document_id: string | null;
  error_code: string | null;
  /** The earlier delivery that brought the same file; this part added no receipt. */
  repeat_of_delivery_id?: string | null;
  /** The file was already saved another way (a web upload) before this email arrived. */
  repeat_of_upload?: boolean;
};

export type BusinessEmailDelivery = {
  id: string;
  state: "received" | "processing" | "partial" | "captured" | "rejected";
  received_at: string;
  updated_at: string;
  original_document_id: string | null;
  retryable: boolean;
  waiting?: { reason: "daily_budget"; retry_at: string } | null;
  subject: string | null;
  sender: string | null;
  sent_at: string | null;
  error_code: string | null;
  parts: BusinessEmailPart[];
  /** Where the server says the email stands: being read, brought no receipt, or no Bandeja row of its own (null). */
  standing: EmailStanding | null;
  /** Files this email saved as receipts, repeats included. Absent from servers older than #1353. */
  saved_receipt_count?: number;
  /** Why it brought no receipt, as a code; null unless `standing` is `no_receipt`. Absent from servers older than #1353. */
  no_receipt_reason?: string | null;
  /** Copy the server attaches to this delivery. Missing on older answers, and null when there is nothing to say. */
  review_note?: string | null;
  /** Copy the inbox adds, such as a first scan. The deliveries list does not send it. */
  notice?: string | null;
};

/** One inbox group, in the order the server listed it. */
export type BusinessEmailInboxGroup = {
  id: string;
  items: BusinessEmailDelivery[];
};

export type BusinessEmailDetail = BusinessEmailDelivery & { text_body: string | null };

export function businessReceivingAddress(intake: BusinessEmailIntake): string | null {
  return intake.enabled ? intake.receiving_address : null;
}

/** Reading: still moving with nothing saved yet. No receipt: finished without saving a new file. */
export type EmailStanding = "reading" | "no_receipt";

/** A delivery still moving on the server is worth a short poll. */
export function emailDeliveriesNeedRefresh(items: readonly BusinessEmailDelivery[]): boolean {
  return items.some((item) => !item.waiting && (item.state === "received" || item.state === "processing" || item.state === "partial"));
}
