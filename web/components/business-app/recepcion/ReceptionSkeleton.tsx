"use client";

import { Fragment, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useDelayedPending } from "../business-skeletons";
import motion from "../business-skeletons.module.css";
import type { ReceptionColumnKey, ReceptionPreferences } from "./reception-columns";
import { originPlace, receptionPlaces } from "./reception-grid";
import styles from "./reception.module.css";

function Bar({ width, height = 12, pill = false }: { width: number | string; height?: number; pill?: boolean }) {
  return <span className={`${motion.block} ${motion.shimmer} ${styles.skeletonBar} ${pill ? "rounded-full" : "rounded-mark"}`} style={{ width, height }} />;
}
export default function ReceptionSkeleton({ preferences, selectable, status }: { preferences: ReceptionPreferences; selectable: boolean; status: boolean }) {
  const { t } = useTranslation();
  const visible = useDelayedPending(true);
  const places = receptionPlaces(preferences, { status });
  const has = places.has;
  const together = originPlace(places.shown);
  const cells = (index: number): Record<ReceptionColumnKey, ReactNode> => ({
    document: <span className={styles.identity} style={places.at("document")}><Bar width={index % 2 ? 170 : 220} height={15} /></span>,
    file: <span className={styles.fileCell} style={places.at("file")} data-file="true"><Bar width={18} height={20} /></span>,
    source: null,
    sender: null,
    amount: <span className={styles.amountCell} style={places.at("amount")}><Bar width={64} /></span>,
    currency: <span className={styles.currencyCell} style={places.at("currency")}><Bar width={30} /></span>,
    status: <span className={styles.state} style={places.at("status")}><Bar width={112} height={21} pill /></span>,
    arrival: <span className={styles.arrival} style={places.at("arrival")}><Bar width={72} /></span>,
  });
  const origin = (index: number) => <span className={styles.source} style={places.shared} data-info={has("source") || has("sender")}>
    {has("source") ? <span className={styles.channel} style={places.at("source")}><Bar width={76} /></span> : null}
    {has("sender") ? <span className={styles.sender} style={places.at("sender")} data-known="true"><Bar width={index % 2 ? 110 : 150} /></span> : null}
    {has("arrival") ? <span className={styles.mobileArrival}><Bar width={65} /></span> : null}
  </span>;
  return <ul role="status" aria-label={t("business.reception_preview.loading")} aria-busy="true" data-testid="reception-skeleton" style={{ visibility: visible ? "visible" : "hidden" }}>
    {[0, 1, 2, 3, 4].map(index => <li key={index} className={`${styles.row} ${styles.skeletonRow}`} aria-hidden="true">
      {selectable ? <span className={styles.checkbox}><Bar width={16} height={16} /></span> : null}
      {places.shown.map(key => <Fragment key={key}>{key === together ? origin(index) : null}{cells(index)[key]}</Fragment>)}
      <div className={styles.rowActions} style={places.last}><div className={styles.rowAction}><div><Bar width={56} height={28} pill /></div></div><span className={styles.trashSlot} /></div>
    </li>)}
  </ul>;
}
