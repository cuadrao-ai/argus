"use client";

import { Download } from "lucide-react";
import { secondaryButtonClass } from "../business-ui";
import { useBusiness } from "../BusinessWorkspace";
import { useTransaccionesWords } from "./transacciones-words";

/**
 * Registros' export, on its own toolbar button once Agregar moves to the top bar. Shown only with the `export`
 * permission, as the add menu's item was. While an export cannot start it stays in place and keeps its focus:
 * aria-disabled, not disabled, as the add menu's trigger does.
 */
export function RecordsExportButton({ onExport, enabled = true }: { onExport: () => void; enabled?: boolean }) {
  const { t } = useTransaccionesWords();
  const { chosen } = useBusiness();
  if (chosen?.permissions?.includes("export") !== true) return null;
  return (
    <button type="button" data-testid="records-export" className={`${secondaryButtonClass} aria-disabled:cursor-not-allowed aria-disabled:opacity-60`} aria-disabled={!enabled || undefined} onClick={enabled ? onExport : undefined}>
      <Download size={18} aria-hidden="true" />
      {t("business.overview.export_records")}
    </button>
  );
}
