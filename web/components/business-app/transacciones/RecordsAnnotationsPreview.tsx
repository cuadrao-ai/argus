"use client";

import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { FileText, Pencil, Plus, StickyNote, X } from "lucide-react";
import Image from "next/image";
import type { ReceiptLimits } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import BottomSheet from "@/components/ui/BottomSheet";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import { UNKNOWN_VALUE } from "../business-format";
import { canAddRecords, primaryButtonClass, quietButtonClass } from "../business-ui";
import { receiptFormatLabel } from "../receipt-file";
import { AccountLabel, PlainAmount, Unknown } from "./transacciones-parts";
import RecordsEvidenceDropZone from "./RecordsEvidenceDropZone";
import { addLocalEvidence, type LocalEvidence } from "./records-evidence-preview";
import { formatRecordActivityDate, recordRowKey } from "./records-row-preview";
import { RecordEvidenceContext } from "./RecordGlanceContext";
import type { RecordRow } from "./transacciones-model";
import { useTransaccionesWords } from "./transacciones-words";
import cells from "./transacciones-cells.module.css";
import styles from "./records-annotations-preview.module.css";

const NOTE_LIMIT = 500;

type RecordAnnotation = { note: string; attachments: readonly LocalEvidence[] };
type EditorSelection = { scope: string; row: RecordRow; opener: HTMLElement | null } & ({ kind: "note" } | { kind: "attachment" });
type AnnotationContextValue = {
  read: (row: RecordRow) => RecordAnnotation;
  edit: (row: RecordRow, kind: EditorSelection["kind"]) => void;
  canRead: boolean;
  canEdit: boolean;
  canAttach: boolean;
};
const EMPTY_ANNOTATION: RecordAnnotation = { note: "", attachments: [] };
const AnnotationContext = createContext<AnnotationContextValue | null>(null);
const annotationKey = (scope: string, row: RecordRow) => JSON.stringify([scope, recordRowKey(row)]);

export function RecordsAnnotationsPreview({ children }: { children: ReactNode }) {
  const { chosen, records } = useBusiness();
  const scope = chosen?.space_id ?? "own";
  const canRead = Boolean(chosen?.capabilities.includes("read"));
  const canEdit = canRead && canAddRecords(chosen);
  const limits = records.workspace?.receipt_limits ?? null;
  const attachmentPreviewEnabled = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const [annotations, setAnnotations] = useState<ReadonlyMap<string, RecordAnnotation>>(() => new Map());
  const [selected, setSelected] = useState<EditorSelection | null>(null);
  const read = (row: RecordRow) => canRead ? annotations.get(annotationKey(scope, row)) ?? EMPTY_ANNOTATION : EMPTY_ANNOTATION;
  const edit = (row: RecordRow, kind: EditorSelection["kind"]) => {
    if (kind === "attachment" && !attachmentPreviewEnabled) return;
    setSelected({ scope, row, kind, opener: document.activeElement instanceof HTMLElement ? document.activeElement : null });
  };
  const active = canRead && selected?.scope === scope && (selected.kind === "note" || attachmentPreviewEnabled) ? selected : null;
  const save = (value: RecordAnnotation) => {
    if (!active || !canEdit) return;
    setAnnotations((current) => new Map(current).set(annotationKey(scope, active.row), value));
    setSelected(null);
  };
  return <AnnotationContext.Provider value={{ read, edit, canRead, canEdit, canAttach: attachmentPreviewEnabled && canEdit && limits !== null }}>
    {children}
    {active ? <AnnotationEditor key={`${scope}:${recordRowKey(active.row)}:${active.kind}`} selected={active} initial={read(active.row)} limits={limits} canEdit={canEdit} close={() => setSelected(null)} save={save} /> : null}
  </AnnotationContext.Provider>;
}

export function RecordNotePreview({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { t } = useTransaccionesWords();
  const note = annotations?.read(row).note ?? "";
  if (!annotations?.canEdit) return note ? <span className={cells.noteButton} title={note}>{note}</span> : <Unknown />;
  return <Tooltip content={note || t("business.transactions.layout.annotations.add_note")} side="top"><button type="button" data-record-note={recordRowKey(row)} className={note ? cells.noteButton : styles.icon} aria-label={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => { event.stopPropagation(); annotations.edit(row, "note"); }}>{note || <span className={cells.emptyAction} aria-hidden="true"><span className={cells.emptyActionDash}>{UNKNOWN_VALUE}</span><Pencil size={16} className={cells.emptyActionIcon} /></span>}</button></Tooltip>;
}

export function RecordAttachmentPreview({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { openPanel } = useBusiness();
  const openEvidence = useContext(RecordEvidenceContext);
  const { t } = useTransaccionesWords();
  const attachments = annotations?.read(row).attachments ?? [];
  const localCount = attachments.length;
  const label = localCount ? t("business.transactions.layout.annotations.local_files", { count: localCount }) : t(`business.transactions.layout.annotations.${row.hasProof ? "open_attachment" : "add_attachment"}`);
  if (annotations && !annotations.canRead || !localCount && row.hasProof === null) return <Unknown />;
  if (!localCount && !row.hasProof && !annotations?.canAttach) return <Unknown meaning={t("business.transactions.layout.annotations.no_attachment")} />;
  if (!localCount && row.hasProof && !row.opens && !annotations?.canAttach) return <Tooltip content={t("business.transactions.layout.annotations.linked_unavailable")} side="top"><span className={styles.icon} role="img" aria-label={t("business.transactions.layout.annotations.linked_unavailable")}><FileText size={16} aria-hidden="true" /></span></Tooltip>;
  return <Tooltip content={label} side="top"><button type="button" data-record-attachment={recordRowKey(row)} data-local-attachment-count={localCount || undefined} className={styles.icon} aria-label={t("business.transactions.layout.annotations.attachment_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => {
    event.stopPropagation();
    if (annotations && (localCount || annotations.canAttach)) annotations.edit(row, "attachment");
    else if (row.opens) { if (openEvidence) openEvidence(row); else openPanel(row.opens); }
  }}>{localCount || row.hasProof ? <><FileText size={16} aria-hidden="true" />{localCount ? <span className="ml-1 text-[14px] tabular-nums" aria-hidden="true">{localCount}</span> : null}</> : <span className={cells.emptyAction} aria-hidden="true"><span className={cells.emptyActionDash}>{UNKNOWN_VALUE}</span><Plus size={16} className={cells.emptyActionIcon} /></span>}</button></Tooltip>;
}

export function RecordAnnotationActions({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { t } = useTransaccionesWords();
  if (!annotations?.canRead) return null;
  const saved = annotations.read(row);
  const NoteIcon = saved.note ? StickyNote : Pencil;
  const note = annotations.canEdit || saved.note;
  const attachment = saved.attachments.length || row.hasProof || row.hasProof === false && annotations.canAttach;
  if (!note && !attachment) return null;
  return <div className={cells.touchActions}>
    {note ? <Tooltip content={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} side="top"><button type="button" className={styles.icon} data-record-note={recordRowKey(row)} aria-label={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => { event.stopPropagation(); annotations.edit(row, "note"); }}><NoteIcon size={16} aria-hidden="true" /></button></Tooltip> : null}
    {attachment ? <RecordAttachmentPreview row={row} /> : null}
  </div>;
}

type EditorProps = { selected: EditorSelection; initial: RecordAnnotation; limits: ReceiptLimits | null; canEdit: boolean; close: () => void; save: (value: RecordAnnotation) => void };
type FileSelectionState = { kind: "idle" } | { kind: "preparing" } | { kind: "error"; message: string } | { kind: "duplicates"; count: number };
function AnnotationEditor({ selected, initial, limits, canEdit, close, save }: EditorProps) {
  const { t, locale } = useTransaccionesWords();
  const { openPanel } = useBusiness();
  const openEvidence = useContext(RecordEvidenceContext);
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const word = (key: string) => t(`business.transactions.layout.annotations.${key}`);
  const [note, setNote] = useState(initial.note);
  const [attachments, setAttachments] = useState(initial.attachments);
  const [selection, setSelection] = useState<FileSelectionState>({ kind: "idle" });
  const pendingSelection = useRef(0);
  useEffect(() => () => { pendingSelection.current++; }, []);
  const field = useRef<HTMLTextAreaElement>(null);
  const opener = useRef(selected.opener);
  const fieldId = useId();
  const title = selected.kind === "note" ? t("business.transactions.columns.notas") : t("business.transactions.layout.column_attachment");
  const selectFiles = async (files: File[]) => {
    if (!canEdit || !limits || !files.length) return;
    const request = ++pendingSelection.current;
    setSelection({ kind: "preparing" });
    try {
      const result = await addLocalEvidence(attachments, files, limits);
      if (pendingSelection.current !== request) return;
      if (result.kind === "invalid") { setSelection({ kind: "error", message: `${result.filename} · ${word(result.reason)}` }); return; }
      setAttachments(result.attachments);
      setSelection(result.duplicates ? { kind: "duplicates", count: result.duplicates } : { kind: "idle" });
    } catch {
      if (pendingSelection.current === request) setSelection({ kind: "error", message: word("preview_failed") });
    }
  };
  const openOriginal = () => {
    if (!selected.row.opens) return;
    close();
    if (openEvidence) openEvidence(selected.row); else openPanel(selected.row.opens);
  };
  const body = <div className={styles.content}>
    <div className={styles.recordContext}>
      <div><p className={styles.counterparty}>{selected.row.counterparty ?? t("business.transactions.unknown")}</p><p className={styles.recordKind}>{t(`business.transactions.records.detail.${selected.row.kind}`)}{selected.kind === "attachment" ? <> · {formatRecordActivityDate(selected.row.occurredOn, locale)}</> : null}</p></div>
      {selected.kind === "attachment" ? <div className={styles.amount}><PlainAmount money={selected.row.money} /></div> : null}
      {selected.kind === "attachment" && selected.row.account ? <p className={styles.account}>{t("business.transactions.columns.cuenta")} · <AccountLabel account={selected.row.account} /></p> : null}
    </div>
    {selected.kind === "note" ? <><label htmlFor={fieldId} className={styles.label}>{word("current_note")}</label><textarea ref={field} id={fieldId} className={styles.textarea} rows={4} maxLength={NOTE_LIMIT} value={note} readOnly={!canEdit} aria-describedby={`${fieldId}-count`} onChange={(event) => setNote(event.target.value.slice(0, NOTE_LIMIT))} /><div id={`${fieldId}-count`} className="mt-1 text-right text-[13px] tabular-nums text-[#56635e] dark:text-white/55">{note.length}/{NOTE_LIMIT}</div></> : <>
      <section aria-label={word("linked_evidence")} className={styles.linkedEvidence}>
        <h3 className={styles.label}>{word("linked_evidence")}</h3>
        {selected.row.hasProof ? selected.row.opens ? <button type="button" className={quietButtonClass} onClick={openOriginal}><FileText size={16} aria-hidden="true" />{word("open_linked_attachment")}</button> : <p className={styles.hint}>{word("linked_unavailable")}</p> : <p className={styles.hint}>{word(selected.row.hasProof === null ? "linked_unknown" : "no_linked_attachment")}</p>}
        {canEdit ? <p className={styles.hint}>{word("received_unavailable")}</p> : null}
      </section>
      <ul className={styles.fileList} aria-label={word("local_preview")} data-local-files="">{attachments.map(({ digest, file }) => <li key={digest}><LocalFilePreview file={file} /></li>)}</ul>
      {canEdit && limits ? <RecordsEvidenceDropZone limits={limits} busy={selection.kind === "preparing"} onFiles={(files) => { void selectFiles(files); }} /> : null}
      {selection.kind === "error" ? <p id={`${fieldId}-error`} role="alert" className={styles.error}>{selection.message}</p> : null}
      {selection.kind === "preparing" ? <p role="status" className={styles.hint}>{word("preparing_preview")}</p> : null}
      {selection.kind === "duplicates" ? <p role="status" className={styles.hint}>{t("business.transactions.layout.annotations.duplicates", { count: selection.count })}</p> : null}
      <p className={styles.disclosure}>{word("local_only")}</p>
    </>}
  </div>;
  const footer = canEdit ? <div className={styles.footer}><button type="button" className={`${primaryButtonClass} w-full`} disabled={selected.kind === "note" ? note.length > NOTE_LIMIT : !attachments.length || selection.kind === "preparing" || selection.kind === "error"} onClick={() => save(selected.kind === "note" ? { ...initial, note: note.trim() } : { ...initial, attachments })}>{selected.kind === "note" ? t("common.save") : word("keep_local_preview")}</button></div> : null;
  return phone ? <BottomSheet isOpen onClose={close} title={title} closeLabel={t("common.close")} backLabel={t("common.back")} snaps={["half", "full"]} initialSnap={selected.kind === "attachment" ? "full" : "half"} footer={footer}>{body}</BottomSheet> : <DesktopEditor title={title} close={close} footer={footer} initialFocusRef={selected.kind === "note" ? field : undefined} returnFocusRef={opener}>{body}</DesktopEditor>;
}

function LocalFilePreview({ file }: { file: File }) {
  const { t } = useTransaccionesWords();
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return <div className={styles.filePreview}>
    {url && file.type.startsWith("image/") ? <Image src={url} alt="" width={40} height={40} unoptimized className={styles.image} /> : <FileText size={20} className="shrink-0" aria-hidden="true" />}
    <div className={styles.fileDetails}><p className={styles.filename}>{file.name}</p><p className={styles.hint}>{receiptFormatLabel(file.type)} · {Math.ceil(file.size / 1024)} KB</p></div>
    {url ? <a className={styles.fileLink} href={url} target="_blank" rel="noopener noreferrer">{t("business.transactions.layout.annotations.preview_file")}</a> : null}
  </div>;
}

type DesktopEditorProps = { title: string; close: () => void; footer: ReactNode; children: ReactNode; initialFocusRef?: RefObject<HTMLElement | null>; returnFocusRef: RefObject<HTMLElement | null> };
const DesktopEditor = withViewportPortal(function DesktopEditor({ title, close, footer, children, initialFocusRef, returnFocusRef }: DesktopEditorProps) {
  const { t } = useTransaccionesWords();
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  useModalSurface({ isOpen: true, overlayId: id, containerRef: panel, onDismiss: close, onOutsidePointerDown: close, initialFocusRef, returnFocusRef });
  return <div className={styles.overlay}><div ref={panel} role="dialog" aria-modal="true" aria-labelledby={id} className={styles.dialog}><header className={styles.header}><h2 id={id}>{title}</h2><button type="button" className={styles.icon} onClick={close} aria-label={t("common.close")}><X size={18} aria-hidden="true" /></button></header>{children}{footer}</div></div>;
});
