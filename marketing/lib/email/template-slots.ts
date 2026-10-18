import { renderAccountEmail, type EmailLayoutOptions } from "./account-layout";

const empty = { status: "awaiting_copy", subject: "", title: "", paragraphs: [] } as const;

export const EMAIL_TEMPLATE_SLOTS = {
  phone_changed_notification: empty,
  identity_linked_notification: empty,
  identity_unlinked_notification: empty,
  mfa_factor_enrolled_notification: empty,
  mfa_factor_unenrolled_notification: empty,
} as const;

export type EmailTemplateSlot = keyof typeof EMAIL_TEMPLATE_SLOTS;

export function renderTemplateSlot(slot: EmailTemplateSlot, options: EmailLayoutOptions & { preview?: boolean } = {}) {
  if (!options.preview) throw new Error(`Email template ${slot} is awaiting approved copy`);
  const content = EMAIL_TEMPLATE_SLOTS[slot];
  return { subject: content.subject, sendable: false as const, ...renderAccountEmail(content, options) };
}
