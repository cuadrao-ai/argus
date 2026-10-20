"use client";

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { currentMonthKey, windowForMonth } from "@/lib/business-month-close";
import { useBusiness } from "./BusinessWorkspace";
import { MonthSwitcher } from "./BusinessMonthClosePanel";
import { ReceiptPeriodExport } from "./ReceiptDossierReview";

/** The Business export, opened from Inicio on the month Inicio shows. */
export default function ExportRecordsPanel({ month: startMonth, onClose }: { month: string; onClose: () => void }) {
  const { t } = useTranslation();
  const { chosen, source } = useBusiness();
  const [month, setMonth] = useState(startMonth);
  const headingId = useId();
  const period = windowForMonth(month);
  return (
    <AdaptivePanel title={t("business.overview.export_records", "Export records")} closeLabel={t("common.close", "Close")} onClose={onClose} width="md">
      <div className="px-4 pb-6" data-testid="export-records-panel">
        {chosen && period.to ? (
          <ReceiptPeriodExport
            bare
            key={chosen.grant_id}
            scope={{ name: chosen.name, capabilities: chosen.capabilities, grantId: chosen.role === "owner" ? null : chosen.grant_id }}
            start={period.from}
            end={period.to}
            available={source.mode === "live"}
            monthSwitcher={<MonthSwitcher month={month} current={currentMonthKey()} earliest={null} onMonth={setMonth} headingId={headingId} />}
          />
        ) : null}
      </div>
    </AdaptivePanel>
  );
}
