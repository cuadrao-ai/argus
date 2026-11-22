"use client";

import { BadgeCheck, Check, CircleX, History, Link2, Loader2, Pencil, ReceiptText, SquareSparkles, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { useRecordTray } from "../record-tray";
import styles from "./dossier.module.css";

/** What a row's status slot says, by shape and color alone; the words are its tooltip. */
export type RowStatusKind = "ok" | "warn" | "bad" | "link" | "calculated" | "last_choice" | "receipt" | "reading";
export type RowStatus = { kind: RowStatusKind; text: string };

const STATUS_ICON: Record<Exclude<RowStatusKind, "calculated">, LucideIcon> = { ok: BadgeCheck, warn: TriangleAlert, bad: CircleX, link: Link2, last_choice: History, receipt: ReceiptText, reading: SquareSparkles };
const STATUS_TONE: Partial<Record<RowStatusKind, "ok" | "warn" | "bad">> = { ok: "ok", warn: "warn", bad: "bad" };

export function StatusIcon({ status, testId }: { status: RowStatus; testId?: string }) {
  const Icon = status.kind === "calculated" ? null : STATUS_ICON[status.kind];
  return (
    <Tooltip content={status.text} side="top">
      <span tabIndex={0} role="img" aria-label={status.text} data-testid={testId} data-status={status.kind} data-tone={STATUS_TONE[status.kind]} className={styles.icon}>
        {Icon ? <Icon size={16} aria-hidden="true" /> : <span aria-hidden="true" className="text-[13px] leading-4">ƒ</span>}
      </span>
    </Tooltip>
  );
}

/** One group of rows on the tint: its heading, what sits beside it, and its rows. */
export function DossierCard({ title, aside, children, testId, label }: { title: string; aside?: ReactNode; children?: ReactNode; testId?: string; label?: string }) {
  return (
    <section className={styles.card} aria-label={label ?? title} data-testid={testId}>
      <div className={styles.cardHead}>
        <h3 className={styles.cardTitle}>{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function DossierRows({ children }: { children: ReactNode }) {
  return <ul className={styles.rows}>{children}</ul>;
}

/** How a row edits in place. Absent for a row nobody can edit now. */
export type RowEdit = {
  open: boolean;
  saving: boolean;
  /** An edit whose outcome is unknown cannot be dropped. */
  locked: boolean;
  /** Absent for someone who cannot edit the record now. */
  onOpen?: () => void;
  onSave: () => void;
  onCancel: () => void;
  /** The row's field while it is open. */
  editor: ReactNode;
};

export type DossierRowProps = {
  /** The row's key, as `data-fact`. */
  row: string;
  label: string;
  /** Text, or text with a second line. An empty value reads "Sin dato". */
  value: ReactNode;
  status?: RowStatus | null;
  look?: "text" | "number" | "mono";
  total?: boolean;
  /** The value wraps: it holds more than one line. */
  wrap?: boolean;
  edit?: RowEdit;
  /** Under the value: the row's save state, or an action the value offers. */
  below?: ReactNode;
  /** A problem jumped here: `n` restarts the wash on every jump. */
  flash?: number;
  attention?: boolean;
  match?: string;
  testId?: string;
  /** Facts about the row for whoever reads the page's markup. */
  data?: { [attribute: `data-${string}`]: string | undefined };
};

/**
 * One fact as a row of the grid: label, status slot, value, action slot. The
 * value opens its own field in the same box. The pencil shows on hover and on
 * focus, and always on touch. The check or Enter saves; the X or Escape cancels.
 */
export function DossierRow({ row, label, value, status, look = "text", total, wrap, edit, below, flash, attention, match, testId, data }: DossierRowProps) {
  const { t } = useTranslation();
  const item = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (!flash) return;
    item.current?.scrollIntoView?.({ block: "center" });
    item.current?.querySelector<HTMLElement>("button, input, select")?.focus({ preventScroll: true });
  }, [flash]);
  const empty = value === null || value === undefined || value === "";
  const shape = `${styles.value} ${look === "number" ? styles.num : look === "mono" ? styles.mono : ""}`;
  const shown = empty ? t("business.dossier.row.no_data") : value;
  const editing = edit?.open === true;
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // The calendar owns its keys, and the portal of a phone's sheet bubbles here too.
    if (!edit || (event.target as Element).closest('[data-testid="date-picker-month"]')) return;
    if (event.key === "Escape") {
      event.stopPropagation();
      if (!edit.locked) edit.onCancel();
    } else if (event.key === "Enter" && (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) {
      event.preventDefault();
      edit.onSave();
    }
  };
  const save = t("common.save", "Save");
  const cancel = t("common.cancel", "Cancel");
  return (
    <li ref={item} {...data} data-testid={testId} data-fact={row} data-attention={attention ? "true" : undefined} data-flash={flash ? (flash % 2 ? "a" : "b") : undefined} data-match={match} className={`${styles.row} ${total ? styles.total : ""}`}>
      <span className={styles.label}>{label}</span>
      <span className={styles.slot}>{status ? <StatusIcon status={status} testId={`row-status-${row}`} /> : null}</span>
      {editing ? <div data-row-open="" className={styles.field} onKeyDown={onKeyDown}>{edit.editor}</div>
        : edit?.onOpen ? <button type="button" data-row-value="" data-empty={empty || undefined} data-wrap={wrap || undefined} className={shape} onClick={edit.onOpen}>{shown}</button>
        : <span data-row-value="" data-empty={empty || undefined} data-wrap={wrap || undefined} className={shape}>{shown}</span>}
      <span className={styles.actions}>
        {editing ? <>
          <Tooltip content={save} side="top">
            <button type="button" aria-label={`${save} · ${label}`} aria-busy={edit.saving} disabled={edit.saving} className={`${styles.act} ${styles.actSave}`} onClick={edit.onSave}>
              {edit.saving ? <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}
            </button>
          </Tooltip>
          <Tooltip content={cancel} side="top">
            <button type="button" aria-label={`${cancel} · ${label}`} disabled={edit.saving || edit.locked} className={styles.act} onClick={edit.onCancel}><X size={16} aria-hidden="true" /></button>
          </Tooltip>
        </> : edit?.onOpen ? <button type="button" aria-label={`${t("business.dossier.edit", "Edit details")} · ${label}`} className={styles.pen} onClick={edit.onOpen}><Pencil size={15} aria-hidden="true" /></button> : null}
      </span>
      {below ? <div className={styles.below}>{below}</div> : null}
    </li>
  );
}

/** A row whose control is always in place (a select, a switch): it spans the value and the action slot. */
export function DossierControlRow({ row, label, status, children, below }: { row: string; label: string; status?: RowStatus | null; children: ReactNode; below?: ReactNode }) {
  return (
    <li data-fact={row} className={styles.row}>
      <span className={styles.label}>{label}</span>
      <span className={styles.slot}>{status ? <StatusIcon status={status} testId={`row-status-${row}`} /> : null}</span>
      <div className={styles.wide}>{children}</div>
      {below ? <div className={styles.below}>{below}</div> : null}
    </li>
  );
}

/** A state with no frame of its own (loading, a load error, the end of a run): the dossier drawer pads nothing, so this keeps it off the edges. */
export function DossierBare({ children }: { children: ReactNode }) {
  return useRecordTray() ? <div className="p-5">{children}</div> : <>{children}</>;
}
