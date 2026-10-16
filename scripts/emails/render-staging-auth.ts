import { mkdir, writeFile } from "node:fs/promises";
import { renderAuthMail, type AuthMail } from "../../web/server/emails/auth-actions";

const destination = new URL("../../temp/staging-auth-email/", import.meta.url);
await mkdir(destination, { recursive: true });
const code = "55070219";
const hash = "a".repeat(64);
const linked = { recipient: "synthetic@example.test", tokenHash: hash, redirectTo: "" };
const actions: Array<{ field: string; mail: AuthMail }> = [
  {field: "confirmation", mail: {...linked, action: "signup", token: code}},
  {field: "invite", mail: {...linked, action: "invite"}},
  {field: "magic_link", mail: {...linked, action: "magiclink"}},
  {field: "recovery", mail: {...linked, action: "recovery"}},
  {field: "email_change", mail: {...linked, action: "email_change", newEmail: "synthetic-new@example.test"}},
  {field: "reauthentication", mail: {action: "reauthentication", recipient: linked.recipient, token: code}},
];
const config: Record<string, string> = {};
for (const {field, mail} of actions) {
  const rendered = await renderAuthMail(mail, "https://skedzwocnmrhfigiwyzi.supabase.co");
  const url = `https://skedzwocnmrhfigiwyzi.supabase.co/auth/v1/verify?token=${hash}&type=${mail.action}&redirect_to=`;
  const html = rendered.html.replaceAll(url.replaceAll("&", "&amp;"), "{{ .ConfirmationURL }}").replaceAll(code, "{{ .Token }}");
  config[`mailer_subjects_${field}`] = rendered.subject.replaceAll(code, "{{ .Token }}");
  config[`mailer_templates_${field}_content`] = html;
  await writeFile(new URL(`${field}-preview.html`, destination), rendered.html);
}
await writeFile(new URL("templates.json", destination), JSON.stringify(config, null, 2) + "\n");
console.log("Rendered six synthetic staging templates locally. No config was applied and no email was sent.");
