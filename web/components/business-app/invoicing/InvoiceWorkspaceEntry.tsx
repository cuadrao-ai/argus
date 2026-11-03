"use client";

import { useTranslation } from "react-i18next";
import type { InvoiceScope } from "@/lib/business-invoices-api";
import ConnectedInvoicingWorkspace, { type InvoiceCapabilities } from "./ConnectedInvoicingWorkspace";
import type { BusinessDirectoryStatus } from "../BusinessWorkspace";
import { quietButtonClass } from "../business-ui";
import InvoicingPreview from "./InvoicingPreview";

/** The Facturación screen, mounted only while the workspace offers it (`invoicingShown`); `sample` is the design sample. */
export default function InvoiceWorkspaceEntry({ scope, business, capabilities, sample, directoryStatus, onRetry }: {
  directoryStatus?: BusinessDirectoryStatus;
  onRetry?: () => void;
  scope: InvoiceScope | null;
  business: string;
  capabilities: InvoiceCapabilities;
  sample: boolean;
}) {
  const { t } = useTranslation();
  if (sample) return <InvoicingPreview />;
  const failed = <div role="alert"><p>{t("business.invoicing.load_failed")}</p><button type="button" className={quietButtonClass} onClick={onRetry}>{t("common.retry")}</button></div>;
  if (!scope && directoryStatus === "loading") return <p role="status">{t("common.loading")}</p>;
  if (!scope) return directoryStatus === "failed" ? failed : <p role="alert">{t("business.invoicing.access")}</p>;
  return <>{directoryStatus === "failed" ? failed : null}<ConnectedInvoicingWorkspace scope={scope} business={business} capabilities={capabilities} /></>;
}
