"use client";

import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { BandejaLabel } from "@/lib/business-api";
import { StatusPill, type StatusChipTone } from "../foundation/StatusChip";
import { rowLabel, type ReceptionRow } from "./reception-model";
import styles from "./reception.module.css";

const TONE: Record<BandejaLabel, StatusChipTone> = { reading: "neutral", cant_read: "attention", needs_attention: "caution", ready: "toAccept", accepted: "approved" };

/** Estado: the label the server gave the row, as a pill. A row with no label shows none. */
export default function ReceptionStatus({ row, style }: { row: ReceptionRow; style?: CSSProperties }) {
  const { t } = useTranslation();
  const label = rowLabel(row);
  return <span className={styles.state} style={style}>{label ? <StatusPill tone={TONE[label]} data-testid="status-pill" data-label={label}>{t(`business.bandeja.label.${label}`)}</StatusPill> : null}</span>;
}
