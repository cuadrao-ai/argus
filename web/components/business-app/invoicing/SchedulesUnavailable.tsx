import { useTranslation } from "react-i18next";
import { useInvoiceWords } from "./InvoiceDocument";
import WorkspaceEmptyState from "./WorkspaceEmptyState";

export default function SchedulesUnavailable() {
  const { t } = useTranslation();
  const { word } = useInvoiceWords();
  return <div data-testid="schedules-unavailable"><WorkspaceEmptyState art="schedule" title={word("schedules_empty")} description={t("business.invoicing.schedules_unavailable")} /></div>;
}
