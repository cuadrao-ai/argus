import { readFileSync, writeFileSync } from "node:fs";
import { renderBusinessClosedEmail, renderBusinessLifecycleEmail } from "../../marketing/lib/email/business-closed";

const tokens = {
  businessName: "__CUADRAO_BUSINESS_NAME__",
  ownerName: "__CUADRAO_OWNER_NAME__",
  closedDate: "__CUADRAO_CLOSED_DATE__",
  purgeDate: "__CUADRAO_PURGE_DATE__",
  purgeTime: "__CUADRAO_PURGE_TIME__",
  actionUrl: "https://cuadrao-email-action.invalid/biz?lifecycle=manage&business=00000000-0000-0000-0000-000000000000",
  businessUrl: "https://cuadrao-email-business.invalid/biz",
  postalAddress: "Cuadrao LLC, __CUADRAO_POSTAL_ADDRESS__",
  assetOrigin: "https://cuadrao-email-assets.invalid",
} as const;
const {assetOrigin, postalAddress, actionUrl, businessUrl, ...data} = tokens;
const templates = Object.fromEntries((["es-419", "en"] as const).map(locale => [locale,
  Object.fromEntries((["owner_closed", "purge_reminder", "member_reopened"] as const).map(kind => [kind,
    renderBusinessLifecycleEmail({kind, ...data, actionUrl: kind === "member_reopened" ? businessUrl : actionUrl}, {assetOrigin, locale}),
  ])),
]));
const output = JSON.stringify({ schemaVersion: 1, tokens, ...renderBusinessClosedEmail(data, {assetOrigin, postalAddress}), templates }, null, 2) + "\n";
const destination = new URL("../../src/argus/domain/business/business_closed_email.generated.json", import.meta.url);
if (process.argv.includes("--check")) {
  if (readFileSync(destination, "utf8") !== output) throw new Error("Business close email artifact is stale");
} else writeFileSync(destination, output);
