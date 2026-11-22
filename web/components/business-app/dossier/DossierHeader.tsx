"use client";

import { ChevronDown, ChevronUp, List, Maximize2, Minimize2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import type { BandejaLabel } from "@/lib/business-api";
import type { DossierProblem } from "../dossier-attention";
import { StatusPill } from "../foundation/StatusChip";
import { useRecordTray } from "../record-tray";
import { BANDEJA_LABEL_TONE } from "../recepcion/ReceptionStatus";
import styles from "./dossier.module.css";

/** Closes a popover on a press outside it and on Escape, which it claims so the tray stays open. */
function usePopover(host: React.RefObject<HTMLElement | null>, open: boolean, close: () => void) {
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

/** The Bandeja label as the list draws it. */
export function BandejaLabelPill({ label, small = false }: { label: BandejaLabel; small?: boolean }) {
  const { t } = useTranslation();
  return <StatusPill tone={BANDEJA_LABEL_TONE[label]} data-testid={small ? "jump-pill" : "status-pill"} data-label={label}>{t(`business.bandeja.label.${label}`)}</StatusPill>;
}

/**
 * Line two of the header: the server's Bandeja label, and why the record is not
 * Listos. One reason sits beside the pill and jumps to its field. Several open
 * the list of problems. An accepted record has no pill: "Aceptado" lives in
 * Historial. A deleted record has no label, so the line says only that.
 */
export function DossierStatus({ label, deleted = false, problems = [], onProblem, children }: {
  label: BandejaLabel | null | undefined;
  deleted?: boolean;
  problems?: readonly DossierProblem[];
  onProblem?: (problem: DossierProblem) => void;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  usePopover(host, open, () => setOpen(false));
  const pill = label && label !== "accepted" ? <BandejaLabelPill label={label} /> : null;
  if (!pill && !deleted && !children) return null;
  const pick = (problem: DossierProblem) => { setOpen(false); onProblem?.(problem); };
  return (
    <div ref={host} className={`${styles.scope} ${styles.status}`} data-testid="dossier-status">
      {pill}
      {deleted && !pill ? <span className={styles.deleted} data-testid="dossier-deleted">{t("business.document_delete.deleted_state")}</span> : null}
      {pill && problems.length === 1 ? <button type="button" className={styles.why} data-testid="dossier-reason" data-compare={problems[0].compare} onClick={() => pick(problems[0])}>{problems[0].title}</button> : null}
      {pill && problems.length > 1 ? <>
        <button type="button" className={styles.why} data-testid="dossier-problems" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {t("business.dossier.problems.count", { count: problems.length })}
          <ChevronDown size={14} aria-hidden="true" />
        </button>
        {open ? <div role="listbox" aria-label={t("business.dossier.problems.list")} className={`${styles.pop} ${styles.issues}`} data-testid="dossier-problem-list">
          {problems.map((problem) => (
            <button key={problem.key} type="button" role="option" aria-selected={false} data-reason={problem.reason} data-compare={problem.compare} className={styles.issue} onClick={() => pick(problem)}>
              <span className={styles.issueIcon}><TriangleAlert size={16} aria-hidden="true" /></span>
              <span><span className={styles.issueTitle}>{problem.title}</span><span className={styles.issueWhere}>{problem.where}</span></span>
            </button>
          ))}
        </div> : null}
      </> : null}
      {children}
    </div>
  );
}

/** One document in the jump card: what the list already says of it, in the list's order. */
export type JumpRow = { id: string; name: string; label: BandejaLabel | null; unopened: boolean; wait: string; total: string };
export type DossierPlace = { index: number; total: number; previous?: () => void; next?: () => void };

/** "N de M" with the moves the list allows now. With the list's rows, "N de M" opens the jump card under it. */
export function DossierPlaceNav({ place, jump }: { place: DossierPlace; jump?: { title: string; rows: readonly JumpRow[] | null; current: string; onOpen: () => void; onPick: (id: string) => void } | null }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const host = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  usePopover(host, open, () => setOpen(false));
  useEffect(() => { if (open) card.current?.focus(); }, [open]);
  const listed = jump?.rows;
  const currentId = jump?.current;
  // The card opens on the document in view, once the list has answered.
  useEffect(() => { if (open && listed) setActive(Math.max(0, listed.findIndex((row) => row.id === currentId))); }, [open, listed, currentId]);
  const words = t("business.dossier.place", { index: place.index, total: place.total, defaultValue: "{{index}} of {{total}}" });
  const rows = jump?.rows ?? [];
  const pick = (id: string) => { setOpen(false); if (id !== jump?.current) jump?.onPick(id); };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const move: Record<string, number | undefined> = { ArrowDown: Math.min(rows.length - 1, active + 1), ArrowUp: Math.max(0, active - 1), Home: 0, End: rows.length - 1 };
    const next = move[event.key];
    if (next !== undefined) { event.preventDefault(); setActive(next); }
    else if (event.key === "Enter" && rows[active]) { event.preventDefault(); pick(rows[active].id); }
  };
  return (
    <div ref={host} className={`${styles.scope} ${styles.controls}`}>
      <div role="group" aria-label={t("business.dossier.nav.group")} data-testid="receipt-place" className={styles.navGroup}>
        {jump ? (
          <Tooltip content={t("business.dossier.nav.list")} side="bottom">
            <button type="button" data-testid="dossier-jump" className={`${styles.place} ${styles.jumpButton}`} aria-label={t("business.dossier.nav.list_place", { place: words })} aria-haspopup="listbox" aria-expanded={open} onClick={() => { if (!open) jump.onOpen(); setOpen((value) => !value); }}>
              <List size={16} aria-hidden="true" />{words}
            </button>
          </Tooltip>
        ) : <span className={styles.place}>{words}</span>}
        <Tooltip content={`${t("business.dossier.nav.previous")} · ⌘⇧↑`} side="bottom">
          <button type="button" className={styles.navButton} disabled={!place.previous} onClick={place.previous} aria-label={t("business.shortcuts.previous_receipt", "Previous receipt")} aria-keyshortcuts="Meta+Shift+ArrowUp Control+Shift+ArrowUp"><ChevronUp size={18} aria-hidden="true" /></button>
        </Tooltip>
        <Tooltip content={`${t("business.dossier.nav.next")} · ⌘⇧↓`} side="bottom">
          <button type="button" className={styles.navButton} disabled={!place.next} onClick={place.next} aria-label={t("business.shortcuts.next_receipt", "Next receipt")} aria-keyshortcuts="Meta+Shift+ArrowDown Control+Shift+ArrowDown"><ChevronDown size={18} aria-hidden="true" /></button>
        </Tooltip>
      </div>
      {open && jump ? (
        <div ref={card} role="listbox" tabIndex={0} aria-label={jump.title} data-testid="dossier-jump-card" className={`${styles.pop} ${styles.jump}`} onKeyDown={onKeyDown}>
          <div className={styles.jumpHead}><span>{jump.title}</span><span>{jump.rows ? rows.length : null}</span></div>
          {jump.rows ? null : <p role="status" className={styles.emptyLine} style={{ padding: "10px" }}>{t("common.loading", "Loading…")}</p>}
          {rows.map((row, index) => (
            <button key={row.id} type="button" role="option" aria-selected={row.id === jump.current} data-active={index === active || undefined} data-receipt={row.id} className={styles.jumpRow} onClick={() => pick(row.id)}>
              {row.unopened && row.id !== jump.current ? <span className={styles.unopened} role="img" aria-label={t("business.dossier.nav.unopened")} /> : <span />}
              <span className="min-w-0">
                <span className={styles.jumpName}>{row.name}</span>
                <span className={styles.jumpMeta}>{row.label ? <BandejaLabelPill label={row.label} small /> : null}<span>{row.wait}</span></span>
              </span>
              <span className={styles.jumpTotal}>{row.total}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** The panel's two sizes. The button is always enabled; outside the tray there is one size and no button. */
export function DossierSizeButton() {
  const { t } = useTranslation();
  const tray = useRecordTray();
  if (!tray?.toggleNarrow) return null;
  const label = tray.narrow ? t("business.dossier.size.wide") : t("business.dossier.size.narrow");
  return (
    <span className={styles.scope}>
      <Tooltip content={label} side="bottom">
        <button type="button" data-testid="dossier-size" className={styles.sizeButton} aria-label={label} aria-pressed={tray.narrow} onClick={tray.toggleNarrow}>
          {tray.narrow ? <Maximize2 size={18} aria-hidden="true" /> : <Minimize2 size={18} aria-hidden="true" />}
        </button>
      </Tooltip>
    </span>
  );
}
