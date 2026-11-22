"use client";

import type { DragEvent, KeyboardEvent, ReactNode } from "react";
import { Upload } from "lucide-react";
import { useTranslation } from "react-i18next";
import { intakeLinkClass } from "./ReceiptUploadRow";
import styles from "./receipt-intake.module.css";

/** What a file dragged over the drop zone would do: nothing yet, upload, or be refused. */
export type DragState = "idle" | "accept" | "reject";

const PAGE = "M8 2h34l20 20v50a6 6 0 0 1-6 6H8a6 6 0 0 1-6-6V8a6 6 0 0 1 6-6z";
const FOLD = "M42 2v14a6 6 0 0 0 6 6h14";

function Page({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span className={`${styles.page} ${className}`}>
      <svg width="64" height="80" viewBox="0 0 64 80" aria-hidden="true">
        <path d={PAGE} fill="#FFFFFF" stroke="#7d8a84" strokeWidth="1.5" />
        <path d={FOLD} fill="#F0EEE7" stroke="#7d8a84" strokeWidth="1.5" strokeLinejoin="round" />
        {children}
      </svg>
    </span>
  );
}

/** A photo page in front; a PDF and a spreadsheet page wait behind it as faded ghosts. */
function PageFan() {
  return (
    <span className={styles.fan} aria-hidden="true">
      <Page className={styles.pageLeft}>
        <rect x="12" y="44" width="32" height="16" rx="4" fill="#f6dfe0" />
        <text x="28" y="56" textAnchor="middle" fontSize="10" fontWeight="600" fill="#9e2f39">PDF</text>
      </Page>
      <Page className={styles.pageRight}>
        <rect x="13" y="34" width="38" height="30" rx="3" fill="none" stroke="#9AA49F" strokeWidth="1.6" />
        <path d="M13 44h38M13 54h38M26 34v30M38 34v30" stroke="#9AA49F" strokeWidth="1.6" />
      </Page>
      <Page className={styles.pageFront}>
        <rect x="12" y="33" width="40" height="31" rx="4" fill="#EEF3EF" stroke="#7d8a84" strokeWidth="1.5" />
        <circle cx="23" cy="42" r="3.5" fill="#9AA49F" />
        <path d="M13 60l11-10 8 7 6-5 13 10" fill="none" stroke="#2f5a49" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      </Page>
    </span>
  );
}

/**
 * Where files come in. With no file yet the whole zone is the picker; once the list has a file it is one line
 * that still takes a drop. `title` is the zone's live line: what to do, or what a dragged file would do.
 */
export default function ReceiptDropZone({ compact, drag, title, formats, canDrag, onPick, onDragEnter, onDragOver, onDragLeave, onDrop }: {
  compact: boolean;
  drag: DragState;
  title: string;
  formats: string;
  canDrag: boolean;
  onPick: () => void;
  onDragEnter: (event: DragEvent) => void;
  onDragOver: (event: DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (event: DragEvent) => void;
}) {
  const { t } = useTranslation();
  const dragging = { onDragEnter, onDragOver, onDragLeave, onDrop };
  if (compact) {
    return (
      <div data-testid="intake-drop-zone" data-drag={drag} data-compact="true" className={`${styles.mini} rounded-item`} {...dragging}>
        <Upload className="h-4 w-4 shrink-0 text-[#2f5a49] dark:text-[#8fcbb0]" aria-hidden="true" />
        <span role="status" aria-live="polite" className={`min-w-0 flex-1 text-[14px] ${drag === "reject" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#3d4a45] dark:text-white/70"}`}>{title}</span>
        <button type="button" data-testid="intake-choose" className={intakeLinkClass} onClick={onPick}>{t("business.intake.choose_multiple")}</button>
      </div>
    );
  }
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onPick();
  };
  return (
    <div data-testid="intake-drop-zone" data-drag={drag} data-compact="false" role="button" tabIndex={0} aria-label={t("business.intake.choose_label")} className={`${styles.drop} rounded-surface`} onClick={onPick} onKeyDown={onKeyDown} {...dragging}>
      <span className={styles.ring} aria-hidden="true" />
      <span className={`${styles.ring} ${styles.ringLate}`} aria-hidden="true" />
      <PageFan />
      <h3 role="status" aria-live="polite" className={`mb-1 font-display text-[19px] font-semibold leading-6 ${drag === "reject" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#172b26] dark:text-white"}`}>{title}</h3>
      {drag === "idle" ? <>
        <p className="text-[14px] font-semibold leading-[21px] text-[#245040] dark:text-[#8fcbb0]">{t("business.intake.drop_click")}</p>
        {canDrag ? <p className="text-[14px] leading-[21px] text-[#3d4a45] dark:text-white/70">{t("business.intake.drop_or_drag")}</p> : null}
        <p className="mt-2 text-[13px] leading-[19px] text-[#56635e] dark:text-white/70">{formats}</p>
      </> : null}
    </div>
  );
}
