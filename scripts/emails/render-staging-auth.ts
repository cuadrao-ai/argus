import { mkdir, writeFile } from "node:fs/promises";
import { buildDashboardAuthPaste } from "../../web/server/emails/auth-paste";

const destination = new URL("../../temp/staging-auth-email/", import.meta.url);
await mkdir(destination, { recursive: true });
const records = await buildDashboardAuthPaste();
for (const record of records) {
  await writeFile(new URL(`${record.file}.html`, destination), record.html);
  await writeFile(new URL(`${record.file}.txt`, destination), record.text);
  await writeFile(new URL(`${record.file}.subject.txt`, destination), `${record.subject}\n`);
}
console.log("Rendered Auth template paste files locally. No config was applied and no email was sent.");
