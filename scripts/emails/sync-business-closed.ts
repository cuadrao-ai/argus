import { readFileSync, writeFileSync } from "node:fs";
import { renderBusinessClosedEmail } from "../../marketing/lib/email/business-closed";

const tokens = {
  businessName: "__CUADRAO_BUSINESS_NAME__",
  ownerName: "__CUADRAO_OWNER_NAME__",
  closedDate: "__CUADRAO_CLOSED_DATE__",
  purgeDate: "__CUADRAO_PURGE_DATE__",
  postalAddress: "Cuadrao LLC, __CUADRAO_POSTAL_ADDRESS__",
  assetOrigin: "https://cuadrao-email-assets.invalid",
} as const;
const {assetOrigin, postalAddress, ...data} = tokens;
const output = JSON.stringify({ schemaVersion: 1, tokens, ...renderBusinessClosedEmail(data, {assetOrigin, postalAddress}) }, null, 2) + "\n";
const destination = new URL("../../src/argus/domain/business/business_closed_email.generated.json", import.meta.url);
if (process.argv.includes("--check")) {
  if (readFileSync(destination, "utf8") !== output) throw new Error("Business close email artifact is stale");
} else writeFileSync(destination, output);
