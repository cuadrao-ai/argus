"use client";

import { Download } from "lucide-react";
import { secondaryButtonClass } from "../business-ui";
import { useBusiness } from "../BusinessWorkspace";
import { useTransaccionesWords } from "./transacciones-words";
import { RecordsLoadingBar } from "./RecordsLoadingPreview";
import loading from "./records-loading-preview.module.css";

/**
 * Registros' export, on its own toolbar button once Agregar moves to the top bar. Shown only with the `export`
 * permission, as the add menu's item was. While an export cannot start it stays in place and keeps its focus:
 * aria-disabled, not disabled, as the add menu's trigger does. Pending, it holds its slot with a placeholder.
 */
export function RecordsExportButton(props: { onExport: () => void; enabled?: boolean } | { pending: true }) {
  const { t } = useTransaccionesWords();
  const { chosen } = useBusiness();
  if (chosen?.permissions?.includes("export") !== true) return null;
  if ("pending" in props) return <RecordsLoadingBar className={`${loading.control} ${loading.export} !rounded-full`} />;
  const { onExport, enabled = true } = props;
  return (
    <button type="button" data-testid="records-export" className={`${secondaryButtonClass} aria-disabled:cursor-not-allowed aria-disabled:opacity-60`} aria-disabled={!enabled || undefined} onClick={enabled ? onExport : undefined}>
      <Download size={18} aria-hidden="true" />
      {t("business.overview.export_records")}
    </button>
  );
}
