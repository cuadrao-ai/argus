"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { SURFACE_CARD } from "./foundation/surfaces";
import styles from "./receipt-reading.module.css";

/** The receipt while the AI reads it: one soft green band sweeps down the source, top to bottom. */
export function ReadingSheen({ children }: { children: ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-[20px]" data-testid="receipt-reading-sheen">
      {children}
      <span aria-hidden="true" data-testid="receipt-reading-band" className={styles.sheen} />
    </div>
  );
}

/**
 * The fields a read fills, held as empty bars until the read returns: no
 * value, no amount and no zero is shown before the backend has one.
 */
export default function ReceiptReadingState({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  const fields = [
    ["supplier", t("business.reading.supplier", "Supplier")],
    ["ncf", t("business.dossier.field.ncf", "NCF")],
    ["itbis", t("business.dossier.field.itbis", "ITBIS")],
    ["total", t("business.reading.total", "Total")],
  ];
  return (
    <section aria-busy="true" className={`${SURFACE_CARD} space-y-4`} data-testid="receipt-reading-state">
      <p role="status" aria-live="polite" className="text-[15px] font-medium leading-[22px] text-[#2f5a49] dark:text-[#8fcbb0]">{t("business.reading.line", "Reading your receipt…")}</p>
      <dl aria-hidden="true" className="space-y-4">
        {fields.map(([key, label]) => (
          <div key={key} data-reading-field={key} className="space-y-2">
            <dt className="text-[13px] font-medium leading-[18px] text-[#172b26] dark:text-white">{label}</dt>
            <dd className="h-11 rounded-[12px] bg-[#e3ebe1] dark:bg-white/10" />
          </div>
        ))}
      </dl>
      {children}
    </section>
  );
}
