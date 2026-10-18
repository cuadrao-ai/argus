import { AUTH_TEMPLATE_HASH, AUTH_TEMPLATE_ORIGIN } from "../../lib/auth-confirm";
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
    file: "recovery",
    subjectField: "mailer_subjects_recovery",
    bodyField: "mailer_templates_recovery_content",
    mail: { ...linked, action: "recovery" },
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
