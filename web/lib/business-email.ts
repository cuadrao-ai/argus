import { z } from "zod";

import { apiFetch } from "./argus-api-transport";

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

const senderAuthResult = z.enum(["aligned", "failed", "none", "ambiguous", "no_result", "unknown"]);

const emailSenderSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(["address", "domain"]),
  value: z.string().min(1),
  status: z.enum(["pending", "authorized", "blocked"]),
  tag: z.enum(["verified", "unverified"]).nullable().optional(),
  last_auth_result: senderAuthResult.nullable().optional(),
  last_seen_at: z.string().nullable().optional(),
});

/** One sender row from GET /business/email/senders. `tag` may be absent on an older server. */
export type EmailSender = z.infer<typeof emailSenderSchema>;

/** The row the screen may render. `last_auth_result` stays on the wire type and never crosses into the view. */
export type EmailSenderView = Omit<EmailSender, "last_auth_result">;

export type EmailSenderUpdate = {
  kind: EmailSender["kind"];
  value: string;
  status: Exclude<EmailSender["status"], "pending">;
};

export class EmailSenderRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "EmailSenderRequestError";
    this.status = status;
    this.code = code;
  }
}

export type EmailSenderClient = {
  list: (signal?: AbortSignal) => Promise<EmailSender[]>;
  update: (body: EmailSenderUpdate, signal?: AbortSignal) => Promise<EmailSender>;
};

const SENDER_PREVIEWS = ["mixed", "settled", "empty", "error", "loading", "fail"] as const;
export type EmailSenderPreview = (typeof SENDER_PREVIEWS)[number];

/** Only a failed check is shown. A passed check, a hand-added row (`null`) and an older server without `tag` show nothing. */
export function senderCheckFailed(tag: EmailSender["tag"]): boolean {
  return tag === "unverified";
}

const SETTLED_STATUSES = ["authorized", "blocked"] as const satisfies readonly EmailSenderUpdate["status"][];

/** Where a sender can go from where it stands: a pending one either way, a settled one only to the other side. */
export function senderMoves(status: EmailSender["status"]): EmailSenderUpdate["status"][] {
  return SETTLED_STATUSES.filter((next) => next !== status);
}

export function senderForView(sender: EmailSender): EmailSenderView {
  return {
    id: sender.id,
    kind: sender.kind,
    value: sender.value,
    status: sender.status,
    tag: sender.tag,
    last_seen_at: sender.last_seen_at,
  };
}

/** Group by status and keep the order each status arrived in. */
export function groupSenders(items: readonly EmailSenderView[]): Record<EmailSender["status"], EmailSenderView[]> {
  const groups: Record<EmailSender["status"], EmailSenderView[]> = { pending: [], authorized: [], blocked: [] };
  for (const item of items) groups[item.status].push(item);
  return groups;
}

export function pendingSenderCount(items: readonly EmailSender[]): number {
  return items.filter((item) => item.status === "pending").length;
}

/** Dev preview only. Production never takes this path. */
export function emailSendersUseStub(): boolean {
  return process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
}

export function emailSenderPreview(search: string): EmailSenderPreview | null {
  const value = new URLSearchParams(search).get("senders");
  return SENDER_PREVIEWS.find((item) => item === value) ?? null;
}

function parseSender(body: unknown): EmailSender {
  const parsed = emailSenderSchema.safeParse(body);
  if (!parsed.success) throw new EmailSenderRequestError(0, "email_sender_invalid_response");
  return parsed.data;
}

export function parseEmailSenderList(body: unknown): EmailSender[] {
  const parsed = z.object({ items: z.array(emailSenderSchema) }).safeParse(body);
  if (!parsed.success) throw new EmailSenderRequestError(0, "email_sender_invalid_response");
  return parsed.data.items;
}

function asSenderError(error: unknown): EmailSenderRequestError {
  if (error instanceof EmailSenderRequestError) return error;
  if (typeof error === "object" && error !== null) {
    const status = "status" in error && typeof error.status === "number" ? error.status : 0;
    const code = "code" in error && typeof error.code === "string" ? error.code : "unknown";
    return new EmailSenderRequestError(status, code);
  }
  return new EmailSenderRequestError(0, "unknown");
}

export const liveEmailSenderClient: EmailSenderClient = {
  async list(signal) {
    try {
      return parseEmailSenderList(await apiFetch<unknown>("/business/email/senders", { signal }));
    } catch (error) {
      throw asSenderError(error);
    }
  },
  async update(body, signal) {
    try {
      return parseSender(await apiFetch<unknown>("/business/email/senders", {
        method: "POST",
        body: JSON.stringify(body),
        signal,
      }));
    } catch (error) {
      throw asSenderError(error);
    }
  },
};

export async function listEmailSenders(signal?: AbortSignal): Promise<EmailSender[]> {
  return liveEmailSenderClient.list(signal);
}

const STUB_SENDERS: readonly EmailSender[] = [
  { id: "sender-pending-verified", kind: "address", value: "facturas@ferreteria.example", status: "pending", tag: "verified", last_auth_result: "aligned", last_seen_at: "2026-10-30T15:00:00Z" },
  { id: "sender-pending-unverified", kind: "address", value: "avisos@correo.example", status: "pending", tag: "unverified", last_auth_result: "no_result", last_seen_at: "2026-10-29T15:00:00Z" },
  { id: "sender-pending-hand", kind: "address", value: "manual@dueno.example", status: "pending", tag: null, last_auth_result: null, last_seen_at: null },
  { id: "sender-owner", kind: "address", value: "dueno@negocio.example", status: "authorized", tag: "verified", last_auth_result: "aligned", last_seen_at: "2026-10-28T12:00:00Z" },
  { id: "sender-team", kind: "address", value: "equipo@negocio.example", status: "authorized", last_seen_at: "2026-10-20T12:00:00Z" },
  { id: "sender-domain", kind: "domain", value: "proveedor.example", status: "authorized", tag: null, last_auth_result: null, last_seen_at: null },
  { id: "sender-blocked", kind: "address", value: "spam@lista.example", status: "blocked", tag: "unverified", last_auth_result: "failed", last_seen_at: "2026-10-01T12:00:00Z" },
];

function stubItems(mode: EmailSenderPreview): EmailSender[] {
  if (mode === "empty") return [];
  const source = mode === "settled" ? STUB_SENDERS.filter((item) => item.status !== "pending") : STUB_SENDERS;
  return source.map((item) => ({ ...item }));
}

export function createEmailSenderStub(preview: EmailSenderPreview | null): EmailSenderClient {
  const mode = preview ?? "mixed";
  let items = stubItems(mode);
  return {
    async list() {
      if (mode === "error") throw new EmailSenderRequestError(503, "unavailable");
      if (mode === "loading") return new Promise(() => undefined);
      return items.map((item) => ({ ...item }));
    },
    async update(body) {
      if (mode === "fail") throw new EmailSenderRequestError(422, "email_sender_invalid");
      const index = items.findIndex((item) => item.kind === body.kind && item.value === body.value);
      const next: EmailSender = index >= 0
        ? { ...items[index], status: body.status }
        : { id: "sender-new", kind: body.kind, value: body.value, status: body.status, tag: null, last_auth_result: null, last_seen_at: null };
      if (index >= 0) items = items.map((item, itemIndex) => itemIndex === index ? next : item);
      else items = [...items, next];
      return { ...next };
    },
  };
}
