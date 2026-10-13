/** Received emails for a Business, as the API reports them. */

/** Where the owner's permission to read emailed receipts with AI stands, as the server tells this person. */
export type BusinessEmailAIReading = {
  /** on: reads happen; off: the owner turned it off or declined; unseen: the owner has not answered yet. */
  state: "on" | "off" | "unseen";
  /** Whether this person may act on it now (the owner, with a live grant and a configured model). */
  available: boolean;
  reason: string | null;
  /** Whether this person is the Business owner: only the owner answers. */
  owner: boolean;
  scope_version: number;
  purpose: string;
  /** The disclosure the owner reads before agreeing, verbatim from the server. */
  disclosure: string;
  route: { gateway: string; interpretation: { model: string }[]; reply: { model: string }[] } | null;
  /** Binds the agreement to the exact text and model shown. */
  disclosure_token: string | null;
  consented_at: string | null;
  consented_by: string | null;
  revoked_at: string | null;
};

export type BusinessEmailIntake = {
  enabled: boolean;
  receiving_address: string | null;
  /** Absent in sample data and where no permission store exists. */
  ai_reading?: BusinessEmailAIReading | null;
};

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
