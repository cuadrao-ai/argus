import { readFileSync, writeFileSync } from "node:fs";
import { renderExistingAccountEmail } from "../../marketing/lib/email/existing-account";

const tokens = {
  signInUrl: "https://cuadrao-existing-account.invalid/?auth=login",
  assetOrigin: "https://cuadrao-email-assets.invalid",
} as const;
const templates = Object.fromEntries((["es-419", "en"] as const).map(locale => [locale,
  renderExistingAccountEmail({ signInUrl: tokens.signInUrl }, { assetOrigin: tokens.assetOrigin, locale }),
]));
const output = JSON.stringify({ schemaVersion: 1, tokens, templates }, null, 2) + "\n";
const destination = new URL("../../src/argus/domain/existing_account_email.generated.json", import.meta.url);
if (process.argv.includes("--check")) {
  if (readFileSync(destination, "utf8") !== output) throw new Error("Existing account email artifact is stale");
} else writeFileSync(destination, output);
