import { readFileSync, writeFileSync } from "node:fs";
import { renderBusinessTransferEmail, type TransferEmailVariant } from "../../marketing/lib/email/business-transfer";

const tokens = {
  businessName: "__CUADRAO_BUSINESS_NAME__", ownerName: "__CUADRAO_OWNER_NAME__", targetName: "__CUADRAO_TARGET_NAME__",
  eventDate: "__CUADRAO_EVENT_DATE__", eventTime: "__CUADRAO_EVENT_TIME__", expiresDate: "__CUADRAO_EXPIRES_DATE__",
  transferUrl: "https://cuadrao-transfer.invalid/transfer", businessUrl: "https://cuadrao-business.invalid/business",
  assetOrigin: "https://cuadrao-email-assets.invalid",
  postalAddress: "Cuadrao LLC, __CUADRAO_POSTAL_ADDRESS__",
};
const variants: TransferEmailVariant[] = ["requested", "declined", "acceptedOwner", "acceptedTarget", "withdrawn"];
const { assetOrigin, postalAddress, ...data } = tokens;
const output = JSON.stringify({ schemaVersion: 1, tokens, templates: Object.fromEntries(variants.map(variant => [variant, renderBusinessTransferEmail(variant, data, { assetOrigin, postalAddress })])) }, null, 2) + "\n";
const destination = new URL("../../src/argus/domain/business/business_transfer_email.generated.json", import.meta.url);
if (process.argv.includes("--check")) {
  if (readFileSync(destination, "utf8") !== output) throw new Error("Business transfer email artifact is stale");
} else writeFileSync(destination, output);
