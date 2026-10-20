import { readFileSync, writeFileSync } from "node:fs";
import { renderBusinessInviteEmail } from "../../marketing/lib/email/business-invite";

const tokens = {
  ownerName: "__CUADRAO_OWNER_NAME__",
  businessName: "__CUADRAO_BUSINESS_NAME__",
  expiresDate: "__CUADRAO_EXPIRES_DATE__",
  signInUrl: "https://cuadrao-invite-signin.invalid/",
  assetOrigin: "https://cuadrao-email-assets.invalid",
} as const;
const { assetOrigin, ...data } = tokens;
const output = JSON.stringify({ schemaVersion: 1, tokens, ...renderBusinessInviteEmail(data, { assetOrigin }) }, null, 2) + "\n";
const destination = new URL("../../src/argus/domain/business/business_invite_email.generated.json", import.meta.url);
if (process.argv.includes("--check")) {
  if (readFileSync(destination, "utf8") !== output) throw new Error("Business invite email artifact is stale");
} else writeFileSync(destination, output);
