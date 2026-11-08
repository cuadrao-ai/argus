"use client";

import BusinessListTabs from "../foundation/BusinessListTabs";
import type { RecordKind } from "./transacciones-model";
import { useTransaccionesWords } from "./transacciones-words";

export default function RecordsTypeTabs({ value, onChange }: { value: RecordKind; onChange: (value: RecordKind) => void }) {
  const { t } = useTransaccionesWords();
  return <div className="mb-4 border-b border-[color-mix(in_srgb,var(--fg)_11%,transparent)] pb-3">
    <BusinessListTabs label={t("business.transactions.layout.filters.record")} idPrefix="records-type" value={value} onChange={onChange} items={([
      { value: "gasto", label: t("business.transactions.layout.overview.purchases") },
      { value: "venta", label: t("business.transactions.layout.overview.sales") },
    ] as const)} />
  </div>;
}
