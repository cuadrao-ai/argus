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
  /** Where the server says the email stands; absent from servers older than #1341. */
  standing?: EmailStanding | null;
};

export type BusinessEmailDetail = BusinessEmailDelivery & { text_body: string | null };

export function businessReceivingAddress(intake: BusinessEmailIntake): string | null {
  return intake.enabled ? intake.receiving_address : null;
}

/** Reading: still moving with nothing saved yet. No receipt: finished without saving a new file. */
export type EmailStanding = "reading" | "no_receipt";

const isRepeat = (part: BusinessEmailPart) => Boolean(part.repeat_of_delivery_id || part.repeat_of_upload);

/**
 * Where an email stands in the Bandeja. An email is only how a receipt
 * arrived: once it saved a new file, that receipt is the row and the email is
 * none (null). A repeat of a file already saved is not a problem either.
 */
export function emailStanding(delivery: BusinessEmailDelivery): EmailStanding | null {
  // The server owns the answer; the rule below only serves a server that does not send one yet.
  if (delivery.standing !== undefined) return delivery.standing;
  const { parts, state } = delivery;
  if (parts.some((part) => part.state === "captured" && part.document_id && !isRepeat(part))) return null;
  if (state === "rejected") return "no_receipt";
  if (delivery.waiting || state === "received" || state === "processing" || parts.some((part) => part.state === "pending")) return "reading";
  if (!parts.length || parts.some((part) => part.state === "rejected")) return "no_receipt";
  return null;
}

/** A delivery still moving on the server is worth a short poll. */
export function emailDeliveriesNeedRefresh(items: readonly BusinessEmailDelivery[]): boolean {
  return items.some((item) => !item.waiting && (item.state === "received" || item.state === "processing" || item.state === "partial"));
}
