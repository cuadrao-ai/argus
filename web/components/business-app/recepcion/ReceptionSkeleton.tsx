"use client";

import { useTranslation } from "react-i18next";
import { useDelayedPending } from "../business-skeletons";
import motion from "../business-skeletons.module.css";
import type { ReceptionPreferences } from "./ReceptionControls";
import styles from "./reception.module.css";

function Bar({ width, height = 12, pill = false }: { width: number | string; height?: number; pill?: boolean }) {
  return <span className={`${motion.block} ${motion.shimmer} ${styles.skeletonBar}`} style={{ width, height, borderRadius: pill ? 999 : 4 }} />;
}
export default function ReceptionSkeleton({ preferences }: { preferences: ReceptionPreferences }) {
  const { t } = useTranslation();
  const visible = useDelayedPending(true);
  return <ul role="status" aria-label={t("business.reception_preview.loading")} aria-busy="true" data-testid="reception-skeleton" style={{ visibility: visible ? "visible" : "hidden" }}>
    {[0, 1, 2, 3, 4].map(index => <li key={index} className={`${styles.row} ${styles.skeletonRow}`} aria-hidden="true">
      <span className={styles.checkbox}><Bar width={16} height={16} /></span>
      <span className={styles.identity}><Bar width={index % 2 ? 170 : 220} height={15} /></span>
      <span className={styles.fileCell} data-file="true"><Bar width={18} height={20} /></span>
      {preferences.source || preferences.sender || preferences.arrival ? <span className={styles.source} data-info={preferences.source || preferences.sender}>
        {preferences.source ? <span className={styles.channel}><Bar width={76} /></span> : null}
        {preferences.sender ? <span className={styles.sender} data-known="true"><Bar width={index % 2 ? 110 : 150} /></span> : null}
        {preferences.arrival ? <span className={styles.mobileArrival}><Bar width={65} /></span> : null}
      </span> : null}
      {preferences.amount ? <span className={styles.amountCell}><Bar width={64} /></span> : null}
      {preferences.currency ? <span className={styles.currencyCell}><Bar width={30} /></span> : null}
      <span className={styles.state}><Bar width={112} height={21} pill /></span>
      {preferences.arrival ? <span className={styles.arrival}><Bar width={72} /></span> : null}
      <div className={styles.rowAction}><div><Bar width={86} height={28} pill /></div></div>
    </li>)}
  </ul>;
}
