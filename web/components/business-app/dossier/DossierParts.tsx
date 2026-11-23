"use client";

import { BadgeCheck, Check, ChevronDown, CircleX, History, Link2, Loader2, Pencil, ReceiptText, RotateCcw, SquareSparkles, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
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

/**
 * The dossier's one way back to a value the server gives: a field held apart
 * from its source, or a Subtotal typed over the calculated one. It sits in the
 * status slot and names the value it puts back, as the server states it.
 */
export function RestoreButton({ field, value, onRestore }: { field: string; value: string; onRestore: () => void }) {
  const { t } = useTranslation();
  const label = t("business.dossier.placeholder.restore_inherited", { value });
  return <Tooltip content={label} side="top"><button type="button" aria-label={label} data-restore-inherited={field} className={styles.pen} style={{ opacity: 1, width: 24, height: 24 }} onClick={onRestore}><RotateCcw size={14} aria-hidden="true" /></button></Tooltip>;
}

/** Closes a popover on a press outside it and on Escape, which it claims so the tray stays open. */
export function usePopover(host: RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  const onClose = useRef(close);
  useEffect(() => { onClose.current = close; });
  useEffect(() => {
    if (!open) return undefined;
    const outside = (event: PointerEvent) => { if (!host.current?.contains(event.target as Node)) onClose.current(); };
    const escape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose.current();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape, true);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape, true); };
  }, [host, open]);
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
  disabled?: boolean;
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
  statusAction?: ReactNode;
  look?: "text" | "number" | "mono";
  total?: boolean;
  /** The value wraps: it holds more than one line. */
  wrap?: boolean;
  edit?: RowEdit;
  /** Under the value: a save that failed, or an action the value offers. */
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
 * A save that lands closes the field on the new value and says nothing more.
 */
export function DossierRow({ row, label, value, status, statusAction, look = "text", total, wrap, edit, below, flash, attention, match, testId, data }: DossierRowProps) {
  const { t } = useTranslation();
  const item = useRef<HTMLLIElement>(null);
  const editing = edit?.open === true;
  useEffect(() => {
    if (editing) item.current?.querySelector<HTMLElement>("[data-row-open] :is(input, select)")?.focus();
  }, [editing]);
  useEffect(() => {
    if (!flash) return;
    item.current?.scrollIntoView?.({ block: "center" });
    item.current?.querySelector<HTMLElement>("button, input, select")?.focus({ preventScroll: true });
  }, [flash]);
  const empty = value === null || value === undefined || value === "";
  // An amount carries the mark Ocultar montos blurs.
  const shape = `${styles.value} ${look === "number" ? `${styles.num} cuadrao-amount` : look === "mono" ? styles.mono : ""}`;
  const shown = empty ? t("business.dossier.row.no_data") : value;
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // The calendar owns its keys, and the portal of a phone's sheet bubbles here too.
    if (!edit || (event.target as Element).closest('[data-testid="date-picker-month"]')) return;
    if (event.key === "Escape") {
      event.stopPropagation();
      if (!edit.locked && !edit.saving) edit.onCancel();
    } else if (event.key === "Enter" && (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) {
      event.preventDefault();
      if (!edit.disabled && !edit.saving) edit.onSave();
    }
  };
  const save = t("common.save", "Save");
  const cancel = t("common.cancel", "Cancel");
  const pencil = edit?.onOpen ? <button type="button" aria-label={`${t("business.dossier.edit", "Edit details")} · ${label}`} className={styles.pen} onClick={edit.onOpen}><Pencil size={15} aria-hidden="true" /></button> : null;
  return (
    <li ref={item} {...data} data-testid={testId} data-fact={row} data-attention={attention ? "true" : undefined} data-flash={flash ? (flash % 2 ? "a" : "b") : undefined} data-match={match} className={`${styles.row} ${total ? styles.total : ""}`}>
      <span className={styles.label}>{label}</span>
      <span className={styles.slot}>{status ? <StatusIcon status={status} testId={`row-status-${row}`} /> : statusAction}</span>
      {editing ? <div data-row-open="" className={styles.field} onKeyDown={onKeyDown}>{edit.editor}</div>
        : edit?.onOpen ? <button type="button" data-row-value="" data-empty={empty || undefined} data-wrap={wrap || undefined} className={shape} onClick={edit.onOpen}>{shown}</button>
        : <span data-row-value="" data-empty={empty || undefined} data-wrap={wrap || undefined} className={shape}>{shown}</span>}
      <span className={styles.actions}>
        {editing ? <>
          <Tooltip content={save} side="top">
            <button type="button" aria-label={`${save} · ${label}`} aria-busy={edit.saving} disabled={edit.saving || edit.disabled} className={`${styles.act} ${styles.actSave}`} onClick={edit.onSave}>
              {edit.saving ? <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}
            </button>
          </Tooltip>
          <Tooltip content={cancel} side="top">
            <button type="button" aria-label={`${cancel} · ${label}`} disabled={edit.saving || edit.locked} className={styles.act} onClick={edit.onCancel}><X size={16} aria-hidden="true" /></button>
          </Tooltip>
        </> : pencil}
      </span>
      {below ? <div className={styles.below}>{below}</div> : null}
    </li>
  );
}

/** One choice of a pick row: its stored value, its words, and the mark a suggested one carries. */
export type PickOption = { value: string; label: string; status?: RowStatus | null };
/** How a row picks from a list. A pick saves at once: the row has no field, no check and no X. */
export type RowPick = {
  /** The stored value the row shows; empty when it shows none. */
  value: string;
  options: readonly PickOption[];
  onPick: (value: string) => void;
  saving: boolean;
  disabled: boolean;
};

// The list's size in dossier.module.css: what it needs decides whether it opens above the row or below it.
const LIST_MAX = 300;
const OPTION_HEIGHT = 40;

/**
 * One fact picked from a list, in the row grid: label, status slot, then the
 * value and its chevron as one button over the value and action slots. The
 * list opens over the form, above the row when there is room, and moves nothing.
 */
export function DossierPickRow({ row, label, value, status, pick, below, data }: Pick<DossierRowProps, "row" | "label" | "status" | "below" | "data"> & { value: string; pick: RowPick }) {
  const { t } = useTranslation();
  const item = useRef<HTMLLIElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [side, setSide] = useState<"up" | "down" | null>(null);
  const open = side !== null;
  usePopover(item, open, () => setSide(null));
  useEffect(() => {
    if (!open) return;
    (list.current?.querySelector<HTMLElement>('[aria-selected="true"]') ?? list.current?.querySelector<HTMLElement>('[role="option"]'))?.focus();
  }, [open]);
  const toggle = () => {
    if (open) { setSide(null); return; }
    const box = trigger.current?.getBoundingClientRect();
    const panel = trigger.current?.closest('[role="tabpanel"]')?.getBoundingClientRect();
    const need = Math.min(LIST_MAX, pick.options.length * OPTION_HEIGHT + 14);
    const roomAbove = box && panel ? box.top - panel.top : 0;
    const roomBelow = box && panel ? panel.bottom - box.bottom : 0;
    setSide(roomAbove >= need || (roomBelow < need && roomAbove > roomBelow) ? "up" : "down");
  };
  const walk = (event: KeyboardEvent<HTMLUListElement>) => {
    const options = [...event.currentTarget.querySelectorAll<HTMLElement>('[role="option"]')];
    const at = options.indexOf(document.activeElement as HTMLElement);
    const moves: Record<string, number | undefined> = { ArrowDown: Math.min(options.length - 1, at + 1), ArrowUp: Math.max(0, at - 1), Home: 0, End: options.length - 1 };
    const next = moves[event.key];
    if (next !== undefined) { event.preventDefault(); options[next]?.focus(); }
    // Escape and Tab close the list; Escape hands the focus back to the row.
    else if (event.key === "Escape") trigger.current?.focus();
    else if (event.key === "Tab") setSide(null);
  };
  const choose = (next: string) => {
    setSide(null);
    trigger.current?.focus();
    if (next !== pick.value) pick.onPick(next);
  };
  const chevron = <ChevronDown size={16} aria-hidden="true" />;
  return (
    <li ref={item} {...data} data-fact={row} className={styles.row}>
      <span className={styles.label}>{label}</span>
      <span className={styles.slot}>{status ? <StatusIcon status={status} testId={`row-status-${row}`} /> : null}</span>
      <button ref={trigger} type="button" className={styles.pick} aria-label={`${label}: ${value || t("business.dossier.row.no_data")}`} aria-haspopup="listbox" aria-expanded={open} aria-busy={pick.saving || undefined} disabled={pick.disabled} onClick={pick.saving ? undefined : toggle}>
        <span data-row-value="" data-empty={!value || undefined} className={styles.pickText}>{value || t("business.dossier.row.no_data")}</span>
        <span className={styles.pickAction}>
          {pick.saving ? <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : chevron}
        </span>
      </button>
      {open ? <ul ref={list} role="listbox" aria-label={label} data-side={side} className={styles.list} onKeyDown={walk}>
        {pick.options.map((option) => (
          <li key={option.value} role="presentation">
            <button type="button" role="option" aria-selected={option.value === pick.value} data-value={option.value} className={styles.option} onClick={() => choose(option.value)}>
              <span className={styles.optionCheck}>{option.value === pick.value ? <Check size={16} aria-hidden="true" /> : null}</span>
              <span className="min-w-0">{option.label}</span>
              {option.status ? <OptionMark status={option.status} /> : null}
            </button>
          </li>
        ))}
      </ul> : null}
      {below ? <div className={styles.below}>{below}</div> : null}
    </li>
  );
}

/** The mark of a suggested option: the status slot's icon, named, with no tooltip of its own inside the option. */
function OptionMark({ status }: { status: RowStatus }) {
  const Icon = status.kind === "calculated" ? null : STATUS_ICON[status.kind];
  return <span role="img" aria-label={status.text} data-status={status.kind} className={styles.icon}>{Icon ? <Icon size={16} aria-hidden="true" /> : null}</span>;
}

/** A state with no frame of its own (loading, a load error, the end of a run): the dossier drawer pads nothing, so this keeps it off the edges. */
export function DossierBare({ children }: { children: ReactNode }) {
  return useRecordTray() ? <div className="p-5">{children}</div> : <>{children}</>;
}
