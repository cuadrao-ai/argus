"use client";

import { Fragment, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ReceptionColumnKey, ReceptionPreferences } from "./reception-columns";
import { originPlace, receptionPlaces } from "./reception-grid";
import styles from "./reception.module.css";

const HEADING_CLASS: Partial<Record<ReceptionColumnKey, string>> = { source: styles.channelHeading, sender: styles.senderHeading, amount: styles.amountHeading };

/** The column titles, in the person's order. `children` is the box column; it and Contenido stay first, the action title last. */
export default function ReceptionColumnsHeading({ preferences, status, children }: { preferences: ReceptionPreferences; status: boolean; children: ReactNode }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const places = receptionPlaces(preferences, { status });
  const together = originPlace(places.shown);
  const title = (key: ReceptionColumnKey) => key === "currency" ? t("business.transactions.columns.moneda") : word(key);
  const shared = places.has("source") && places.has("sender") ? "sender_source" : places.has("source") ? "source" : "sender";
  return <div className={styles.columns}>
    {children}
    <span className={styles.contentHeading} data-column="document">{word("document")}</span>
    {places.shown.map(key => <Fragment key={key}>
      {key === together && key !== "arrival" ? <span className={styles.combinedHeading} style={places.shared}>{word(shared)}</span> : null}
      <span className={HEADING_CLASS[key]} style={places.at(key)} data-column={key}>{title(key)}</span>
    </Fragment>)}
    <span className="sr-only" style={places.last}>{word("next_action")}</span>
  </div>;
}
