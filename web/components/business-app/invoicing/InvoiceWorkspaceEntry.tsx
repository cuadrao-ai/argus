"use client";

import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { businessInvoicingEnabled } from "@/lib/private-alpha-flags";
import type { InvoiceScope } from "@/lib/business-invoices-api";
import ConnectedInvoicingWorkspace, { type InvoiceCapabilities } from "./ConnectedInvoicingWorkspace";
import InvoicingPreview from "./InvoicingPreview";

const subscribeLocation = (notify: () => void) => {
  window.addEventListener("popstate", notify);
  return () => window.removeEventListener("popstate", notify);
};
const locationSnapshot = () => new URLSearchParams(window.location.search).has("invoicePreview");

export default function InvoiceWorkspaceEntry({ scope, business, capabilities, previewEnabled }: {
  scope: InvoiceScope | null;
  business: string;
  capabilities: InvoiceCapabilities;
  previewEnabled: boolean;
}) {
  const { t } = useTranslation();
  const explicitPreview = useSyncExternalStore(subscribeLocation, locationSnapshot, () => false);
  if (previewEnabled && (!businessInvoicingEnabled || explicitPreview)) return <InvoicingPreview />;
  if (!businessInvoicingEnabled) return null;
  if (!scope) return <p role="alert">{t("business.invoicing.access")}</p>;
  return <ConnectedInvoicingWorkspace scope={scope} business={business} capabilities={capabilities} />;
}
