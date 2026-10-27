"use client";

import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { businessInvoicingEnabled } from "@/lib/private-alpha-flags";
import type { InvoiceScope } from "@/lib/business-invoices-api";
import ConnectedInvoicingWorkspace, { type InvoiceCapabilities } from "./ConnectedInvoicingWorkspace";
import type { BusinessDirectoryStatus } from "../BusinessWorkspace";
import { quietButtonClass } from "../business-ui";
import InvoicingPreview from "./InvoicingPreview";

const subscribeLocation = (notify: () => void) => {
  window.addEventListener("popstate", notify);
  return () => window.removeEventListener("popstate", notify);
};
const locationSnapshot = () => new URLSearchParams(window.location.search).has("invoicePreview");

export default function InvoiceWorkspaceEntry({ scope, business, capabilities, previewEnabled, directoryStatus, onRetry }: {
  directoryStatus?: BusinessDirectoryStatus;
  onRetry?: () => void;
  scope: InvoiceScope | null;
  business: string;
  capabilities: InvoiceCapabilities;
  previewEnabled: boolean;
}) {
  const { t } = useTranslation();
  const explicitPreview = useSyncExternalStore(subscribeLocation, locationSnapshot, () => false);
  if (previewEnabled && (!businessInvoicingEnabled || explicitPreview)) return <InvoicingPreview />;
  if (!businessInvoicingEnabled) return null;
  const failed = <div role="alert"><p>{t("business.invoicing.load_failed")}</p><button type="button" className={quietButtonClass} onClick={onRetry}>{t("common.retry")}</button></div>;
  if (!scope && directoryStatus === "loading") return <p role="status">{t("common.loading")}</p>;
  if (!scope) return directoryStatus === "failed" ? failed : <p role="alert">{t("business.invoicing.access")}</p>;
  return <>{directoryStatus === "failed" ? failed : null}<ConnectedInvoicingWorkspace scope={scope} business={business} capabilities={capabilities} /></>;
}
