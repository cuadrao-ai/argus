import { createHash } from "node:crypto";
import { LOCALES, type BusinessLocale } from "../site-routes.ts";

export const LIMITS = {
  name: 120,
  email: 254,
  description: 1000,
  bodyBytes: 8 * 1024,
} as const;

export type InquiryInput = {
  name: string;
  email: string;
  description: string;
  locale: BusinessLocale;
  submissionId: string;
};

export type SignupInput = {
  email: string;
  locale: BusinessLocale;
};

export type Validated<T> =
  | { ok: true; value: T }
  | { ok: false; fields: string[] };

const EMAIL = /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
// Line breaks are the only way a one-line field could reshape a mail header.
const LINE_BREAK = /[\r\n\u2028\u2029]/;
const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function emailDigest(normalized: string): string {
  return createHash("sha256").update(normalized).digest("hex");
}

// One bare address. A list, a display name or a line break is refused so a
// configured mailbox can never become several recipients.
export function parseMailbox(value: string | undefined): string | null {
  const address = value?.trim().toLowerCase() ?? "";
  return validEmail(address) ? address : null;
}

export function parseWaitlistSender(value: string | undefined): string | null {
  const from = value?.trim() ?? "";
  const mailbox = parseMailbox(/^(?:Cuadrao|"Cuadrao") <([^<>\r\n]+)>$/.exec(from)?.[1]);
  return mailbox?.endsWith("@cuadrao.ai") || mailbox === "no-responder@mail.cuadrao.ai" ? from : null;
}

function validEmail(value: string): boolean {
  return value.length <= LIMITS.email && EMAIL.test(value) && !LINE_BREAK.test(value);
}

function asRecord(body: unknown): Record<string, unknown> | null {
  return typeof body === "object" && body !== null && !Array.isArray(body)
    ? (body as Record<string, unknown>)
    : null;
}

function locale(value: unknown): BusinessLocale | null {
  return LOCALES.find((candidate) => candidate === value) ?? null;
}

// A filled hidden field means a script, not a person. The route answers it like
// a success so the script learns nothing, and sends or stores nothing.
export function isHoneypotFilled(body: unknown): boolean {
  const record = asRecord(body);
  return typeof record?.website === "string" && record.website.trim() !== "";
}

export function validateInquiry(body: unknown): Validated<InquiryInput> {
  const record = asRecord(body);
  if (!record) return { ok: false, fields: ["body"] };
  const fields: string[] = [];
  const name = typeof record.name === "string" ? record.name.trim() : "";
  const email = typeof record.email === "string" ? normalizeEmail(record.email) : "";
  const description =
    typeof record.description === "string"
      ? record.description.replace(CONTROL, "").trim()
      : "";
  const submissionId = typeof record.submissionId === "string" ? record.submissionId : "";
  const language = locale(record.locale);
  if (!name || name.length > LIMITS.name || LINE_BREAK.test(name)) fields.push("name");
  if (!validEmail(email)) fields.push("email");
  if (description.length > LIMITS.description) fields.push("description");
  if (!UUID.test(submissionId)) fields.push("submissionId");
  if (!language) fields.push("locale");
  if (fields.length || !language) return { ok: false, fields };
  return {
    ok: true,
    value: { name: name.replace(CONTROL, ""), email, description, locale: language, submissionId },
  };
}

export function validateSignup(body: unknown): Validated<SignupInput> {
  const record = asRecord(body);
  if (!record) return { ok: false, fields: ["body"] };
  const email = typeof record.email === "string" ? normalizeEmail(record.email) : "";
  const language = locale(record.locale);
  const fields: string[] = [];
  if (!validEmail(email)) fields.push("email");
  if (!language) fields.push("locale");
  if (fields.length || !language) return { ok: false, fields };
  return { ok: true, value: { email, locale: language } };
}
