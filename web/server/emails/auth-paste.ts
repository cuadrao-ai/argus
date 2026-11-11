import { AUTH_TEMPLATE_EMAIL, AUTH_TEMPLATE_HASH, AUTH_TEMPLATE_ORIGIN, AUTH_TEMPLATE_OTP } from "../../lib/auth-confirm";
import { renderAuthMail, type AuthMail } from "./auth-actions";
import { emailExpiry } from "./expiry";

type AuthTemplateSlot = "confirmation" | "magic_link" | "recovery" | "invite" | "email_change" | "reauthentication" | "password_changed_notification" | "email_changed_notification";
type AuthTemplateSpec<Slot extends AuthTemplateSlot> = {
  subjectField: `mailer_subjects_${Slot}`;
  bodyField: `mailer_templates_${Slot}_content`;
  mail: AuthMail;
};

const linked = { recipient: AUTH_TEMPLATE_EMAIL, tokenHash: AUTH_TEMPLATE_HASH, redirectTo: "" };

export const AUTH_TEMPLATE_SLOTS = {
  confirmation: {
    subjectField: "mailer_subjects_confirmation",
    bodyField: "mailer_templates_confirmation_content",
    mail: { ...linked, action: "signup", token: AUTH_TEMPLATE_OTP },
  },
  magic_link: {
    subjectField: "mailer_subjects_magic_link",
    bodyField: "mailer_templates_magic_link_content",
    mail: { ...linked, action: "magiclink", token: AUTH_TEMPLATE_OTP },
  },
  recovery: {
    subjectField: "mailer_subjects_recovery",
    bodyField: "mailer_templates_recovery_content",
    mail: { ...linked, action: "recovery" },
  },
  invite: {
    subjectField: "mailer_subjects_invite",
    bodyField: "mailer_templates_invite_content",
    mail: { ...linked, action: "invite" },
  },
  email_change: {
    subjectField: "mailer_subjects_email_change",
    bodyField: "mailer_templates_email_change_content",
    mail: { ...linked, action: "email_change", audience: "new_address", newEmail: AUTH_TEMPLATE_EMAIL },
  },
  reauthentication: {
    subjectField: "mailer_subjects_reauthentication",
    bodyField: "mailer_templates_reauthentication_content",
    mail: { action: "reauthentication", recipient: AUTH_TEMPLATE_EMAIL, token: AUTH_TEMPLATE_OTP },
  },
  password_changed_notification: {
    subjectField: "mailer_subjects_password_changed_notification",
    bodyField: "mailer_templates_password_changed_notification_content",
    mail: { action: "password_changed_notification", recipient: AUTH_TEMPLATE_EMAIL },
  },
  email_changed_notification: {
    subjectField: "mailer_subjects_email_changed_notification",
    bodyField: "mailer_templates_email_changed_notification_content",
    mail: { action: "email_changed_notification", recipient: "{{ .OldEmail }}", newEmail: AUTH_TEMPLATE_EMAIL },
  },
} satisfies { [Slot in AuthTemplateSlot]: AuthTemplateSpec<Slot> };

export type DashboardAuthPaste = {
  file: AuthTemplateSlot;
  subjectField: string;
  bodyField: string;
  subject: string;
  html: string;
  text: string;
};

export async function buildDashboardAuthPaste(expirySeconds = 3600): Promise<DashboardAuthPaste[]> {
  emailExpiry(expirySeconds);
  return Promise.all(Object.entries(AUTH_TEMPLATE_SLOTS).map(async ([file, spec]) => ({
    file: file as AuthTemplateSlot,
    subjectField: spec.subjectField,
    bodyField: spec.bodyField,
    ...await renderAuthMail(spec.mail, AUTH_TEMPLATE_ORIGIN, expirySeconds, undefined, { assetOrigin: "https://cuadrao.ai" }),
  })));
}
