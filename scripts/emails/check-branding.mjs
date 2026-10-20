import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, relative } from "node:path";

const root = fileURLToPath(new URL("../../", import.meta.url));
function files(directory) {
  return readdirSync(resolve(root, directory), {withFileTypes: true}).flatMap(entry => entry.isDirectory()
    ? files(`${directory}/${entry.name}`) : [`${directory}/${entry.name}`]);
}
export function brandingViolations(value) {
  return [...value.matchAll(/\bargus(?:chat)?\b|get-argus|(?:[\w-]+\.)*[\w-]*staging[\w-]*(?:\.[\w-]+)+|(?:[\w-]+\.)*onrender\.com/gi)].map(match => match[0]);
}
export function checkEmailBranding() {
  const candidates = [
    ...files("marketing/lib/email"), ...files("marketing/lib/waitlist").filter(path => path.endsWith("email-content.ts")),
    ...files("web/server/emails").filter(path => /renderAccountEmail|<!doctype|<html/i.test(readFileSync(resolve(root, path), "utf8")) && !path.endsWith("auth-hook.ts")),
    ...files("src/argus/domain").filter(path => /email[^/]*\.(?:py|json)$/.test(path) && /<html|<!doctype/i.test(readFileSync(resolve(root, path), "utf8"))),
    ...files("web/__tests__/__snapshots__").filter(path => /email.*\.snap$/.test(path)),
  ];
  const violations = [];
  for (const path of candidates.sort()) {
    const source = readFileSync(resolve(root, path), "utf8").replace(/^(?:from |import ).*$/gm, "");
    for (const match of brandingViolations(source)) violations.push(`${path}: ${match}`);
  }
  return {files: candidates.length, violations};
}
if (process.argv[1] && relative(root, resolve(process.argv[1])) === "scripts/emails/check-branding.mjs") {
  const result = checkEmailBranding();
  for (const violation of result.violations) console.error(violation);
  console.log(`Checked ${result.files} email template and snapshot files; ${result.violations.length} branding violations.`);
  if (result.violations.length) process.exitCode = 1;
}
