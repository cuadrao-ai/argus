"use client";

import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { FileText, MoreHorizontal, Plus, StickyNote, X } from "lucide-react";
import Image from "next/image";
import type { ReceiptLimits } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import BottomSheet from "@/components/ui/BottomSheet";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import { UNKNOWN_VALUE } from "../business-format";
import { canAddRecords, primaryButtonClass, secondaryButtonClass } from "../business-ui";
import ActionMenu from "../ActionMenu";
import { receiptFileAccept, receiptFileWithType, receiptFormatLabel } from "../receipt-file";
import { Unknown } from "./transacciones-parts";
import { recordRowKey } from "./records-row-preview";
import { RecordEvidenceContext } from "./RecordGlanceContext";
import type { RecordRow } from "./transacciones-model";
import { useTransaccionesWords } from "./transacciones-words";
import cells from "./transacciones-cells.module.css";
import styles from "./records-annotations-preview.module.css";

type RecordAnnotation = { note: string; attachment: File | null };
type EditorSelection = { scope: string; row: RecordRow; opener: HTMLElement | null } & ({ kind: "note" } | { kind: "attachment" });
type AnnotationContextValue = {
  read: (row: RecordRow) => RecordAnnotation;
  edit: (row: RecordRow, kind: EditorSelection["kind"]) => void;
  canEdit: boolean;
  canAttach: boolean;
};
const EMPTY_ANNOTATION: RecordAnnotation = { note: "", attachment: null };
const AnnotationContext = createContext<AnnotationContextValue | null>(null);
const annotationKey = (scope: string, row: RecordRow) => JSON.stringify([scope, recordRowKey(row)]);

export function RecordsAnnotationsPreview({ children }: { children: ReactNode }) {
  const { chosen, records } = useBusiness();
  const scope = chosen?.space_id ?? "own";
  const canEdit = canAddRecords(chosen);
  const limits = records.workspace?.receipt_limits ?? null;
  const [annotations, setAnnotations] = useState<ReadonlyMap<string, RecordAnnotation>>(() => new Map());
  const [selected, setSelected] = useState<EditorSelection | null>(null);
  const read = (row: RecordRow) => annotations.get(annotationKey(scope, row)) ?? EMPTY_ANNOTATION;
  const edit = (row: RecordRow, kind: EditorSelection["kind"]) => setSelected({ scope, row, kind, opener: document.activeElement instanceof HTMLElement ? document.activeElement : null });
  const active = selected?.scope === scope ? selected : null;
  const save = (value: RecordAnnotation) => {
    if (!active || !canEdit) return;
    setAnnotations((current) => new Map(current).set(annotationKey(scope, active.row), value));
    setSelected(null);
  };
  return <AnnotationContext.Provider value={{ read, edit, canEdit, canAttach: canEdit && limits !== null }}>
    {children}
    {active ? <AnnotationEditor key={`${scope}:${recordRowKey(active.row)}:${active.kind}`} selected={active} initial={read(active.row)} limits={limits} canEdit={canEdit} close={() => setSelected(null)} save={save} /> : null}
  </AnnotationContext.Provider>;
}

export function RecordNotePreview({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { t } = useTransaccionesWords();
  const note = annotations?.read(row).note ?? "";
  if (!annotations?.canEdit) return note ? <span className={cells.noteButton} title={note}>{note}</span> : <Unknown />;
  return <Tooltip content={note || t("business.transactions.layout.annotations.add_note")} side="top"><button type="button" data-record-note={recordRowKey(row)} className={`${cells.noteButton} ${!note ? cells.emptyNote : ""}`} aria-label={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => { event.stopPropagation(); annotations.edit(row, "note"); }}>{note || UNKNOWN_VALUE}</button></Tooltip>;
}

export function RecordAttachmentPreview({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { openPanel } = useBusiness();
  const openEvidence = useContext(RecordEvidenceContext);
  const { t } = useTransaccionesWords();
  const file = annotations?.read(row).attachment;
  const label = file ? file.name : t(`business.transactions.layout.annotations.${row.hasProof ? "open_attachment" : "add_attachment"}`);
  if (!file && row.hasProof === null) return <Unknown />;
  if (!file && !row.hasProof && !annotations?.canAttach) return <Unknown meaning={t("business.transactions.layout.annotations.no_attachment")} />;
  if (!file && row.hasProof && !row.opens) return <span className={styles.icon} role="img" aria-label={label}><FileText size={16} aria-hidden="true" /></span>;
  return <Tooltip content={label} side="top"><button type="button" data-record-attachment={recordRowKey(row)} className={styles.icon} aria-label={t("business.transactions.layout.annotations.attachment_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => { event.stopPropagation(); if (file || !row.hasProof) annotations?.edit(row, "attachment"); else if (row.opens) { if (openEvidence) openEvidence(row); else openPanel(row.opens); } }}>{file || row.hasProof ? <FileText size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}</button></Tooltip>;
}

export function RecordAnnotationMenu({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { openPanel } = useBusiness();
  const openEvidence = useContext(RecordEvidenceContext);
  const { t } = useTransaccionesWords();
  if (!annotations) return null;
  const saved = annotations.read(row);
  const word = (key: string) => t(`business.transactions.layout.annotations.${key}`);
  const actions = [
    ...(annotations.canEdit || saved.note ? [{ id: "note", label: t("business.transactions.columns.notas"), icon: StickyNote, run: () => annotations.edit(row, "note") }] : []),
    ...(saved.attachment || row.hasProof && row.opens || row.hasProof === false && annotations.canAttach ? [{ id: "attachment", label: word(saved.attachment || row.hasProof ? "open_attachment" : "add_attachment"), icon: FileText, run: () => { if (!saved.attachment && row.hasProof && row.opens) { if (openEvidence) openEvidence(row); else openPanel(row.opens); } else annotations.edit(row, "attachment"); } }] : []),
  ];
  if (!actions.length) return null;
  const label = word("record_actions");
  return <ActionMenu actions={actions} label={label} placement="below-end" portal renderTrigger={({ ref, open, toggle, menuId }) => <button ref={ref} type="button" className={styles.icon} aria-label={t("business.transactions.layout.annotations.actions_for", { name: row.counterparty ?? t("business.transactions.unknown") })} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} onClick={(event) => { event.stopPropagation(); toggle(); }}><MoreHorizontal size={18} aria-hidden="true" /></button>} />;
}

type EditorProps = { selected: EditorSelection; initial: RecordAnnotation; limits: ReceiptLimits | null; canEdit: boolean; close: () => void; save: (value: RecordAnnotation) => void };
function AnnotationEditor({ selected, initial, limits, canEdit, close, save }: EditorProps) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const word = (key: string) => t(`business.transactions.layout.annotations.${key}`);
  const [note, setNote] = useState(initial.note);
  const [file, setFile] = useState(initial.attachment);
  const [error, setError] = useState<string | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const opener = useRef(selected.opener);
  const fieldId = useId();
  const title = selected.kind === "note" ? t("business.transactions.columns.notas") : t("business.transactions.layout.column_attachment");
  const body = <div className={styles.content}>
    <p className={styles.counterparty}>{selected.row.counterparty ?? t("business.transactions.unknown")}<span className={styles.recordKind}>{t(`business.transactions.records.detail.${selected.row.kind}`)}</span></p>
    {selected.kind === "note" ? <><label htmlFor={fieldId} className={styles.label}>{word("current_note")}</label><textarea ref={field} id={fieldId} className={styles.textarea} rows={4} maxLength={2000} value={note} readOnly={!canEdit} onChange={(event) => setNote(event.target.value)} /></> : <>
      {canEdit && limits ? <><label htmlFor={fieldId} className={styles.chooseFile}><Plus size={16} aria-hidden="true" />{word("choose_file")}</label><input id={fieldId} type="file" className={styles.fileInput} accept={receiptFileAccept(limits)} aria-describedby={error ? `${fieldId}-error` : undefined} aria-invalid={error ? true : undefined} onChange={(event) => {
        const chosen = event.target.files?.[0];
        if (!chosen) return;
        const candidate = receiptFileWithType(chosen, limits);
        const invalid = !candidate.name.trim() || candidate.name.length > 255 || /[\u0000-\u001f\\/]/.test(candidate.name) ? "invalid_name" : !limits.media_types.includes(candidate.type) ? "unsupported" : candidate.size === 0 ? "empty_file" : candidate.size > limits.max_bytes ? "too_large" : null;
        setError(invalid);
        if (!invalid) setFile(candidate);
        event.target.value = "";
      }} /></> : null}
      {error ? <p id={`${fieldId}-error`} role="alert" className={styles.error}>{word(error)}</p> : null}
      {file ? <LocalFilePreview file={file} /> : null}
    </>}
  </div>;
  const footer = <div className={styles.footer}><button type="button" className={secondaryButtonClass} onClick={close}>{t("common.cancel")}</button>{canEdit ? <button type="button" className={primaryButtonClass} disabled={selected.kind === "attachment" && (!file || Boolean(error))} onClick={() => save(selected.kind === "note" ? { ...initial, note: note.trim() } : { ...initial, attachment: file })}>{t("common.save")}</button> : null}</div>;
  return phone ? <BottomSheet isOpen onClose={close} title={title} closeLabel={t("common.close")} snaps="fit" footer={footer}>{body}</BottomSheet> : <DesktopEditor title={title} close={close} footer={footer} initialFocusRef={selected.kind === "note" ? field : undefined} returnFocusRef={opener}>{body}</DesktopEditor>;
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
    {url && file.type.startsWith("image/") ? <Image src={url} alt={file.name} width={360} height={200} unoptimized className={styles.image} /> : <FileText size={28} aria-hidden="true" />}
    <p className={styles.filename}>{file.name}</p><p className={styles.hint}>{receiptFormatLabel(file.type)} · {Math.ceil(file.size / 1024)} KB</p>
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
