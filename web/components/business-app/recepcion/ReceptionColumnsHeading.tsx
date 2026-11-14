"use client";

import { Fragment, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { statusColumnWord, type ReceptionColumnKey, type ReceptionPreferences } from "./reception-columns";
import { originPlace, receptionPlaces } from "./reception-grid";
import type { ReceptionView } from "./reception-model";
import styles from "./reception.module.css";

const HEADING_CLASS: Partial<Record<ReceptionColumnKey, string>> = { document: styles.contentHeading, source: styles.channelHeading, sender: styles.senderHeading, amount: styles.amountHeading, currency: styles.currencyHeading };

/** The column titles, in the person's order. `children` is the box column, which stays first; the action title stays last. */
export default function ReceptionColumnsHeading({ preferences, view, status, children }: { preferences: ReceptionPreferences; view: ReceptionView; status: boolean; children: ReactNode }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const places = receptionPlaces(preferences, { status });
  const together = originPlace(places.shown);
  const title = (key: ReceptionColumnKey) => key === "currency" ? t("business.transactions.columns.moneda") : word(key === "status" ? statusColumnWord(view) : key);
  const shared = places.has("source") && places.has("sender") ? "sender_source" : places.has("source") ? "source" : "sender";
  return <div className={styles.columns}>
    {children}
    {places.shown.map(key => <Fragment key={key}>
      {key === together && key !== "arrival" ? <span className={styles.combinedHeading} style={places.shared}>{word(shared)}</span> : null}
      <span className={HEADING_CLASS[key]} style={places.at(key)} data-column={key}>{title(key)}</span>
    </Fragment>)}
    <span className="sr-only" style={places.last}>{word("next_action")}</span>
  </div>;
}
