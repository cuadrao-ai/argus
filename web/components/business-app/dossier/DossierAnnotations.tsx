"use client";

import { Check, Eye, File, Loader2, Pencil, Unlink, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import type { ReceiptLimits } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import { dueDistance } from "@/lib/business-month-close";
import { reportFailure } from "@/lib/business-reporting-wire";
import { personName } from "@/lib/person-name";
import { resolveLanguage } from "@/lib/language-features";
import type { DossierDetailsCard } from "../BusinessWorkspace";
import { formatDate, todayIso } from "../business-format";
import { NOTE_LIMIT, noteLength, withinNoteLimit } from "../NoteCount";
import { receiptFileAccept, receiptFileWithType } from "../receipt-file";
import { latestNoteChange } from "./annotation-history";
import { DossierCard } from "./DossierParts";
import styles from "./dossier.module.css";
import annotation from "./annotations.module.css";
import pointer from "@/components/sidebar/pointerAffordances.module.css";

export type DossierAnnotationsProps = {
  busy?: boolean;
  dossier?: BusinessDossier;
  detailsCard?: DossierDetailsCard;
  entryVisit?: number;
  receiptLimits?: ReceiptLimits | null;
  selectedSupportingSourceId?: string | null;
  onSaveNote?: (note: string) => Promise<void>;
  onNoteDirty?: (dirty: boolean) => void;
  onAppend?: (file: File) => Promise<void>;
  onViewFile?: (sourceId: string) => void;
  onUnlink?: (sourceId: string) => Promise<void>;
  onRestore?: (sourceId: string) => Promise<void>;
};

export function dossierFileSize(bytes: number, locale: string): string {
  const [amount, unit] = bytes >= 1_048_576 ? [bytes / 1_048_576, "megabyte"] : bytes >= 1024 ? [bytes / 1024, "kilobyte"] : [bytes, "byte"];
  return new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "short", maximumFractionDigits: unit === "megabyte" ? 1 : 0 }).format(amount);
}

/** A card Registros opened the record at: it scrolls into view. The note's text box takes the focus, and the files card marks its own edge. */
function useCardLanding(focus: boolean, entryVisit: number) {
  const target = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focus) target.current?.scrollIntoView?.({ block: "center" });
  }, [focus, entryVisit]);
  return target;
}

type NoteEditor = { text: string; state: "ready" | "saving" | "failed" | "stale" };

export function DossierNoteCard({ busy, dossier, detailsCard, entryVisit = 0, onSaveNote, onNoteDirty }: Pick<DossierAnnotationsProps, "busy" | "detailsCard" | "entryVisit" | "onSaveNote" | "onNoteDirty"> & { dossier: BusinessDossier }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const canEdit = dossier.note_edit_available === true && !!onSaveNote;
  const note = dossier.current_note ?? "";
  const fromEntry = detailsCard === "note";
  const shouldEnter = fromEntry && canEdit ? entryVisit : null;
  const [entered, setEntered] = useState(shouldEnter);
  const [editor, setEditor] = useState<NoteEditor | null>(() => shouldEnter !== null ? { text: note, state: "ready" } : null);
  if (entered !== shouldEnter) {
    setEntered(shouldEnter);
    if (shouldEnter !== null && !editor) setEditor({ text: note, state: "ready" });
  }
  if (!canEdit && editor) setEditor(null);
  const editing = canEdit ? editor : null;
  const dirty = editing !== null && editing.text !== note;
  const saving = editing?.state === "saving";
  const landing = useCardLanding(fromEntry, entryVisit);
  const field = useRef<HTMLTextAreaElement>(null);
  const pencil = useRef<HTMLButtonElement>(null);
  const count = useId();
  const open = editing !== null;
  useEffect(() => {
    if (open) field.current?.focus();
  }, [open, shouldEnter]);
  useEffect(() => { onNoteDirty?.(dirty); }, [dirty, onNoteDirty]);
  useEffect(() => () => onNoteDirty?.(false), [onNoteDirty]);
  const close = () => {
    setEditor(null);
    // The pencil remounts when the field closes.
    requestAnimationFrame(() => pencil.current?.focus({ preventScroll: true }));
  };
  const save = async () => {
    if (!editing || saving || busy || !onSaveNote) return;
    if (editing.text === note) { close(); return; }
    const text = editing.text;
    setEditor({ text, state: "saving" });
    try {
      await onSaveNote(text);
      close();
    } catch (error) {
      setEditor({ text, state: reportFailure(error, true).kind === "version" ? "stale" : "failed" });
      field.current?.focus();
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (!saving) close();
    } else if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void save();
    }
  };
  const latest = latestNoteChange(dossier.history);
  const title = t("business.dossier.note.title");
  const when = latest ? new Date(latest.created_at) : null;
  const name = latest ? personName(t, latest.actor) : "";
  const today = when?.toDateString() === new Date().toDateString();
  const date = when && !Number.isNaN(when.getTime()) ? formatDate(when, locale, { day: "numeric", month: "short", year: "numeric" }) : null;
  const meta = date && (
    <time className={styles.cardMeta} dateTime={latest?.created_at}>
      {today
        ? name ? t("business.dossier.note.edited_today_by", { name }) : t("business.dossier.note.edited_today")
        : name ? t("business.dossier.note.edited_date_by", { name, date }) : t("business.dossier.note.edited_date", { date })}
    </time>
  );
  return (
    <DossierCard title={title} aside={meta} testId="dossier-note">
      <div ref={landing} className={annotation.noteBody}>
        {editing ? (
          <div className={annotation.noteEditor} onKeyDown={onKeyDown}>
            <textarea ref={field} className={`rounded-item ${styles.focus} ${annotation.noteInput}`} rows={4} aria-label={title} aria-describedby={count} value={editing.text} readOnly={saving} onChange={(event) => setEditor({ text: withinNoteLimit(event.target.value), state: editing.state === "stale" ? "stale" : "ready" })} />
            <div className={annotation.noteActions}>
              <span id={count} className={annotation.status}>{noteLength(editing.text)} / {NOTE_LIMIT}</span>
              <button type="button" className={styles.act} aria-label={t("common.cancel")} disabled={saving} onClick={close}><X size={16} aria-hidden="true" /></button>
              <button type="button" className={`${styles.act} ${styles.actSave}`} aria-label={t("common.save")} aria-busy={saving} disabled={saving || busy} onClick={() => void save()}>
                {saving ? <Loader2 size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}
              </button>
            </div>
            {editing.state === "failed" ? <p role="alert" className={annotation.error}>{t("business.dossier.note.save_error")}</p> : null}
            {editing.state === "stale" ? <div role="alert">
              <p className={annotation.error}>{t("business.dossier.note.changed")}</p>
              <p className={annotation.noteText}>{note || t("business.dossier.note.empty")}</p>
            </div> : null}
          </div>
        ) : (
          <div className={`group ${annotation.noteRead}`}>
            <p className={note ? annotation.noteText : annotation.empty}>{note || t("business.dossier.note.empty")}</p>
            {canEdit ? <span className={pointer.rowActions}><button ref={pencil} type="button" className={styles.pen} aria-label={t("business.dossier.note.edit")} disabled={busy} onClick={() => setEditor({ text: note, state: "ready" })}><Pencil size={16} aria-hidden="true" /></button></span> : null}
          </div>
        )}
      </div>
    </DossierCard>
  );
}

type SupportFailure = { kind: "append_error"; retry?: File } | { kind: "unlink_error" | "restore_error" };

export function DossierSupportingCard({ busy, dossier, detailsCard, entryVisit = 0, receiptLimits, selectedSupportingSourceId, onAppend, onViewFile, onUnlink, onRestore }: Omit<DossierAnnotationsProps, "onSaveNote" | "onNoteDirty">) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const add = useRef<HTMLButtonElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<SupportFailure | null>(null);
  const [added, setAdded] = useState(0);
  const [clockTick, setClockTick] = useState(0);
  const fromEntry = detailsCard === "support";
  const landing = useCardLanding(fromEntry, entryVisit);
  const now = new Date();
  const today = todayIso(now);
  const files = dossier?.supporting_files?.flatMap((file) => {
    const purge = file.state === "unlinked" && file.purge_at ? new Date(file.purge_at) : null;
    return file.state === "linked" || (file.restore_available && purge && purge.getTime() > now.getTime()) ? [{ file, purge }] : [];
  }) ?? [];
  const nextPurge = files.reduce((next, { purge }) => purge ? Math.min(next, purge.getTime()) : next, Infinity);
  useEffect(() => {
    if (!Number.isFinite(nextPurge)) return;
    const refresh = () => setClockTick((tick) => tick + 1);
    const current = new Date();
    const midnight = new Date(current).setHours(24, 0, 0, 0);
    const timer = window.setTimeout(refresh, Math.max(0, Math.min(nextPurge, midnight) - current.getTime()));
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [clockTick, nextPurge]);
  const full = dossier?.supporting_limit_reached === true;
  const canAdd = dossier?.supporting_append_available === true && !full && !!onAppend;
  useEffect(() => {
    if (fromEntry && canAdd) add.current?.focus({ preventScroll: true });
  }, [fromEntry, canAdd, entryVisit]);
  const label = t("business.dossier.supporting.add");
  const limit = dossier?.supporting_file_limit;
  const mutate = async (command: () => Promise<void>, action: "append" | "unlink" | "restore", file?: File) => {
    if (pending || busy) return;
    setPending(true);
    setFailure(null);
    try {
      await command();
      if (action === "append") setAdded((count) => count + 1);
    } catch (error) {
      const kind = reportFailure(error, true).kind;
      setFailure(action === "append" ? { kind: "append_error", retry: kind === "uncertain" || kind === "version" ? file : undefined } : { kind: `${action}_error` });
    }
    finally { setPending(false); }
  };
  const pickFile = (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (file && canAdd && onAppend) {
      const selected = receiptLimits ? receiptFileWithType(file, receiptLimits) : file;
      void mutate(() => onAppend(selected), "append", selected);
    }
  };
  return (
    <DossierCard title={t("business.dossier.supporting.title")} testId="dossier-supporting" data={{ "data-landing": fromEntry ? "true" : undefined }} aside={
      canAdd ? <button ref={add} type="button" className={`${styles.link} ${annotation.link}`} disabled={pending || busy} aria-busy={pending} onClick={() => picker.current?.click()}>{label}</button> : null
    }>
      <div ref={landing} className={`rounded-item ${annotation.supportBody}`} data-landing={added ? (added % 2 ? "a" : "b") : undefined}>
        {canAdd ? <input ref={picker} type="file" hidden accept={receiptLimits ? receiptFileAccept(receiptLimits) : undefined} disabled={pending || busy} onChange={pickFile} /> : null}
        {files.length ? <ul className={styles.rows}>{files.map(({ file, purge }) => {
          const name = file.filename ?? t("business.dossier.row.no_data");
          const selected = !purge && selectedSupportingSourceId === file.source_id;
          const action = purge ? "restore" : "unlink";
          const linkChange = purge ? onRestore : file.unlink_available ? onUnlink : undefined;
          const days = purge ? dueDistance(todayIso(purge), today)?.days : undefined;
          const deadline = days === 0 ? t("business.dossier.supporting.purge_today")
            : days === 1 ? t("business.dossier.supporting.purge_tomorrow")
            : days !== undefined ? t("business.dossier.supporting.purge_in", { count: days }) : null;
          return (
            <li key={file.source_id} className={`group rounded-item ${annotation.supportFile}`} data-selected={selected || undefined} data-pending-purge={Boolean(purge) || undefined}>
              <File size={16} className={styles.icon} aria-hidden="true" />
              <span className={annotation.filename} title={name}>{name}</span>
              {file.size_bytes != null ? <span className={annotation.status}>{dossierFileSize(file.size_bytes, locale)}</span> : null}
              <span className={purge ? annotation.fileActions : `${annotation.fileActions} ${pointer.rowActions}`}>
                {!purge && onViewFile ? <button type="button" className={styles.pen} title={t("business.dossier.supporting.view")} aria-label={t("business.dossier.supporting.view_named", { name })} aria-pressed={selected} onClick={() => onViewFile(file.source_id)}><Eye size={16} aria-hidden="true" /></button> : null}
                {linkChange ? <Tooltip content={t(`business.dossier.supporting.${action}`)} side="top">
                  <button type="button" className={styles.pen} aria-label={t(`business.dossier.supporting.${action}_named`, { name })} aria-disabled={pending || busy} onClick={() => {
                    if (purge && purge.getTime() <= Date.now()) {
                      setClockTick((tick) => tick + 1);
                      return;
                    }
                    void mutate(() => linkChange(file.source_id), action);
                  }}><Unlink size={16} aria-hidden="true" /></button>
                </Tooltip> : null}
              </span>
              {deadline ? <time className={`${annotation.status} ${annotation.purgeCountdown}`} dateTime={file.purge_at ?? undefined}>{deadline}</time> : null}
            </li>
          );
        })}</ul> : <p className={annotation.empty}>{t("business.dossier.supporting.empty")}</p>}
        {full ? <p className={annotation.status}>{limit != null ? t("business.dossier.supporting.limit", { count: limit }) : t("business.dossier.supporting.limit_reached")}</p> : null}
        {failure ? <div className={annotation.restoreRow}>
          <p role="alert" className={annotation.error}>{t(`business.dossier.supporting.${failure.kind}`)}</p>
          {failure.kind === "append_error" && failure.retry && canAdd && onAppend ? (
            <button type="button" className={styles.link} disabled={busy} onClick={() => {
              const file = failure.retry;
              if (file) void mutate(() => onAppend(file), "append", file);
            }}>{t("common.retry")}</button>
          ) : null}
        </div> : null}
      </div>
    </DossierCard>
  );
}
