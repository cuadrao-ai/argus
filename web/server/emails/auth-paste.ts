import { AUTH_TEMPLATE_HASH, AUTH_TEMPLATE_ORIGIN, AUTH_TEMPLATE_OTP } from "../../lib/auth-confirm";
import { renderAuthMail, type AuthMail } from "./auth-actions";

const SENT_AT = new Date("2026-10-17T02:05:00Z");
const linked = { recipient: "synthetic@example.test", tokenHash: AUTH_TEMPLATE_HASH, redirectTo: "" };

export type DashboardAuthPaste = {
  file: string;
  subjectField: string;
  bodyField: string;
  subject: string;
  html: string;
  text: string;
};

const specs: Array<{
  file: string;
  subjectField: string;
  bodyField: string;
  mail: AuthMail;
}> = [
  {
    file: "confirmation",
    subjectField: "mailer_subjects_confirmation",
    bodyField: "mailer_templates_confirmation_content",
    mail: { ...linked, action: "signup" },
  },
  {
    file: "magic_link",
    subjectField: "mailer_subjects_magic_link",
    bodyField: "mailer_templates_magic_link_content",
    mail: { ...linked, action: "magiclink", token: AUTH_TEMPLATE_OTP },
  },
  {
    file: "recovery",
    subjectField: "mailer_subjects_recovery",
    bodyField: "mailer_templates_recovery_content",
    mail: { ...linked, action: "recovery" },
  },
  {
    file: "invite",
    subjectField: "mailer_subjects_invite",
    bodyField: "mailer_templates_invite_content",
    mail: { ...linked, action: "invite" },
  },
  {
    file: "email_change",
    subjectField: "mailer_subjects_email_change",
    bodyField: "mailer_templates_email_change_content",
    mail: {
      ...linked,
      action: "email_change",
      audience: "new_address",
      recipient: "synthetic-new@example.test",
      newEmail: "synthetic-new@example.test",
    },
  },
  {
    file: "reauthentication",
    subjectField: "mailer_subjects_reauthentication",
    bodyField: "mailer_templates_reauthentication_content",
    mail: { action: "reauthentication", recipient: linked.recipient, token: AUTH_TEMPLATE_OTP },
  },
];

export async function buildDashboardAuthPaste(): Promise<DashboardAuthPaste[]> {
  const records: DashboardAuthPaste[] = [];
  for (const spec of specs) {
    const rendered = await renderAuthMail(spec.mail, AUTH_TEMPLATE_ORIGIN, 3600, SENT_AT);
    records.push({
      file: spec.file,
      subjectField: spec.subjectField,
      bodyField: spec.bodyField,
      subject: rendered.subject,
      html: rendered.html,
      text: rendered.text,
    });
  }
  return records;
}
