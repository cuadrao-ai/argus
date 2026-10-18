import { mkdir, writeFile } from "node:fs/promises";
import { renderAuthMail, type AuthMail } from "../../web/server/emails/auth-actions";

const destination = new URL("../../temp/staging-auth-email/", import.meta.url);
await mkdir(destination, { recursive: true });
const linked = { recipient: "synthetic@example.test", tokenHash: "a".repeat(64), redirectTo: "https://app.example.test/" };
const actions: Array<{ field: string; mail: AuthMail }> = [
  {field: "confirmation", mail: {...linked, action: "signup", token: "55070219"}},
  {field: "magic_link", mail: {...linked, action: "magiclink", token: "55070219"}},
  {field: "recovery", mail: {...linked, action: "recovery"}},
  {field: "email_change_old", mail: {...linked, action: "email_change", audience: "old_address", newEmail: "synthetic-new@example.test"}},
  {field: "email_change_new", mail: {...linked, action: "email_change", audience: "new_address", recipient: "synthetic-new@example.test", newEmail: "synthetic-new@example.test"}},
  {field: "reauthentication", mail: {action: "reauthentication", recipient: linked.recipient, token: "55070219"}},
  {field: "password_changed", mail: {action: "password_changed_notification", recipient: linked.recipient}},
  {field: "email_changed", mail: {action: "email_changed_notification", recipient: linked.recipient, newEmail: "synthetic-new@example.test"}},
];
for (const {field, mail} of actions) {
  const rendered = await renderAuthMail(mail, "https://auth.example.test", 3600, new Date("2026-10-17T02:05:00Z"));
  await writeFile(new URL(`${field}-preview.html`, destination), rendered.html);
  await writeFile(new URL(`${field}-preview.txt`, destination), rendered.text);
}
console.log("Rendered eight synthetic Auth previews locally. No config was applied and no email was sent.");
