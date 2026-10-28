"use client";

import { RefreshCw } from "lucide-react";
import { quietButtonClass } from "../business-ui";
import { useTransaccionesWords } from "./transacciones-words";

export function RecordsRefreshButton({ busy, onRefresh }: { busy: boolean; onRefresh: () => void }) {
  const { t } = useTransaccionesWords();
  const label = t("business.transactions.reporting.refresh_records");
  return <button type="button" data-testid="records-refresh" className={`${quietButtonClass} min-w-11 justify-center`} disabled={busy} aria-busy={busy} aria-label={label} title={label} onClick={onRefresh}>
    <RefreshCw size={18} aria-hidden="true" className={busy ? "motion-safe:animate-spin" : undefined} />
  </button>;
}
