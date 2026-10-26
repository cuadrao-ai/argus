"use client";

import { createContext, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { FileText, Pencil, Plus, StickyNote, X } from "lucide-react";
import Image from "next/image";
import { appendBusinessReportSupportingFile, downloadBusinessReportAttachment, getBusinessReportAnnotationDossier, setBusinessReportCurrentNote, type CurrentNoteCommand, type ReportScope, type SupportingFileCommand } from "@/lib/business-reports-api";
import { reportFailure, type ReportFailure } from "@/lib/business-reporting-wire";
import { saveBlobDownload } from "../ExportRecordsPanel";
import type { ReceiptLimits } from "@/lib/business-api";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import BottomSheet from "@/components/ui/BottomSheet";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness } from "../BusinessWorkspace";
import { formatMoney, UNKNOWN_VALUE } from "../business-format";
import { canAddRecords, primaryButtonClass, quietButtonClass } from "../business-ui";
import { receiptFormatLabel } from "../receipt-file";
import { AccountLabel, PlainAmount, Unknown } from "./transacciones-parts";
import RecordsEvidenceDropZone from "./RecordsEvidenceDropZone";
import { addLocalEvidence, type LocalEvidence } from "./records-evidence-preview";
import { formatRecordActivityDate, recordRowKey } from "./records-row-preview";
import { RecordEvidenceContext } from "./RecordGlanceContext";
import type { RecordRow } from "./transacciones-model";
import { previewRecordMetadata } from "./records-results-preview";
import { matchesRecordSearch } from "./records-search-preview";
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
  noteEditable: (row: RecordRow) => boolean;
  attachmentEditable: (row: RecordRow) => boolean;
};
const EMPTY_ANNOTATION: RecordAnnotation = { note: "", attachments: [] };
type PendingAnnotation = { note: string; attachments: readonly LocalEvidence[]; noteCommand: CurrentNoteCommand | null; fileCommand: SupportingFileCommand | null; queue: readonly LocalEvidence[]; version: number; problem: ReportFailure };
export type ConnectedAnnotations = { scope: ReportScope; rows: readonly RecordRow[]; refresh: () => Promise<void>; revoke: () => void };
const AnnotationContext = createContext<AnnotationContextValue | null>(null);
const annotationKey = (scope: string, row: RecordRow) => JSON.stringify([scope, recordRowKey(row)]);

export function useRecordPreviewSearch() {
  const annotations = useContext(AnnotationContext);
  const { chosen, records } = useBusiness();
  return (row: RecordRow, query: string): boolean => {
    if (!annotations?.canRead) return !query.trim();
    const current = annotations.read(row);
    const receiptId = row.opens?.kind === "receipt" ? row.opens.receiptId : null;
    const linked = records.inbox?.filter((receipt) => receipt.id === receiptId || receipt.expense_id === row.id) ?? [];
    return matchesRecordSearch(query, {
      name: row.counterparty,
      note: current.note,
      documents: [
        ...(previewRecordMetadata(row, chosen?.space_id ?? null)?.documentNumbers ?? []),
        ...linked.flatMap((receipt) => receipt.filename ? [receipt.filename] : []),
        ...current.attachments.map(({ file }) => file.name),
      ],
    });
  };
}

export function RecordsAnnotationsPreview({ children, connected }: { children: ReactNode; connected?: ConnectedAnnotations }) {
  const { chosen, records } = useBusiness();
  const scope = connected ? `${connected.scope.userId}:${connected.scope.businessId}:${connected.scope.grantId}` : chosen?.space_id ?? "own";
  const canRead = Boolean(chosen?.capabilities.includes("read"));
  const canEdit = canRead && canAddRecords(chosen);
  const limits = records.workspace?.receipt_limits ?? null;
  const attachmentPreviewEnabled = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const pending = useMemo(() => new Map<string, PendingAnnotation>(), []);
  const noteEditable = (row: RecordRow) => row.report ? Boolean(connected && canRead && row.report.can_edit_note) : canEdit;
  const attachmentEditable = (row: RecordRow) => row.report ? Boolean(connected && canRead && row.report.can_append_supporting && limits) : attachmentPreviewEnabled && canEdit && limits !== null;
  const [annotations, setAnnotations] = useState<ReadonlyMap<string, RecordAnnotation>>(() => new Map());
  const [selected, setSelected] = useState<EditorSelection | null>(null);
  const read = (row: RecordRow) => canRead ? row.report ? { note: row.report.note ?? "", attachments: [] } : annotations.get(annotationKey(scope, row)) ?? EMPTY_ANNOTATION : EMPTY_ANNOTATION;
  const edit = (row: RecordRow, kind: EditorSelection["kind"]) => {
    if (row.report && !(kind === "note" ? noteEditable(row) || Boolean(row.report.note) : attachmentEditable(row) || row.hasProof === true)) return;
    if (!row.report && kind === "attachment" && !attachmentPreviewEnabled) return;
    setSelected({ scope, row, kind, opener: document.activeElement instanceof HTMLElement ? document.activeElement : null });
  };
  const selectedRow = selected ? connected?.rows.find((row) => recordRowKey(row) === recordRowKey(selected.row)) ?? selected.row : null;
  const active = canRead && selected?.scope === scope && (selected.kind === "note" || connected || attachmentPreviewEnabled) ? { ...selected, row: selectedRow! } : null;
  const save = (value: RecordAnnotation) => {
    if (!active || !canEdit) return;
    setAnnotations((current) => new Map(current).set(annotationKey(scope, active.row), value));
    setSelected(null);
  };
  return <AnnotationContext.Provider value={{ read, edit, canRead, canEdit, canAttach: Boolean(connected) || attachmentPreviewEnabled && canEdit && limits !== null, noteEditable, attachmentEditable }}>
    {children}
    {active ? <AnnotationEditor key={`${scope}:${recordRowKey(active.row)}:${active.kind}`} selected={active} initial={read(active.row)} limits={limits} connected={active.row.report && connected ? connected : undefined} pending={pending} canEdit={active.kind === "note" ? noteEditable(active.row) : attachmentEditable(active.row)} close={() => setSelected(null)} save={save} /> : null}
  </AnnotationContext.Provider>;
}

export function RecordNotePreview({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { t } = useTransaccionesWords();
  const note = row.report?.note ?? annotations?.read(row).note ?? "";
  if (!annotations?.noteEditable(row)) return note ? <span className={cells.noteButton} title={note}>{note}</span> : <Unknown />;
  return <Tooltip content={note || t("business.transactions.layout.annotations.add_note")} side="top"><button type="button" data-record-note={recordRowKey(row)} className={note ? cells.noteButton : styles.icon} aria-label={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => { event.stopPropagation(); annotations.edit(row, "note"); }}>{note || <span className={cells.emptyAction} aria-hidden="true"><span className={cells.emptyActionDash}>{UNKNOWN_VALUE}</span><Pencil size={16} className={cells.emptyActionIcon} /></span>}</button></Tooltip>;
}

export function RecordAttachmentPreview({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { openPanel } = useBusiness();
  const openEvidence = useContext(RecordEvidenceContext);
  const { t } = useTransaccionesWords();
  const attachments = annotations?.read(row).attachments ?? [];
  const canAttach = annotations?.attachmentEditable(row);
  const localCount = attachments.length;
  const label = localCount ? t("business.transactions.layout.annotations.local_files", { count: localCount }) : t(`business.transactions.layout.annotations.${row.hasProof ? "open_attachment" : "add_attachment"}`);
  if (annotations && !annotations.canRead || !localCount && row.hasProof === null) return <Unknown />;
  if (!localCount && !row.hasProof && !canAttach) return <Unknown meaning={t("business.transactions.layout.annotations.no_attachment")} />;
  if (!localCount && row.hasProof && !row.opens && !canAttach) return <Tooltip content={t("business.transactions.layout.annotations.linked_unavailable")} side="top"><span className={styles.icon} role="img" aria-label={t("business.transactions.layout.annotations.linked_unavailable")}><FileText size={16} aria-hidden="true" /></span></Tooltip>;
  return <Tooltip content={label} side="top"><button type="button" data-record-attachment={recordRowKey(row)} data-local-attachment-count={localCount || undefined} className={styles.icon} aria-label={t("business.transactions.layout.annotations.attachment_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => {
    event.stopPropagation();
    if (annotations && (localCount || canAttach || row.report?.attachment_sources?.length)) annotations.edit(row, "attachment");
    else if (row.opens) { if (openEvidence) openEvidence(row); else openPanel(row.opens); }
  }}>{localCount || row.hasProof ? <><FileText size={16} aria-hidden="true" />{localCount ? <span className="ml-1 text-[14px] tabular-nums" aria-hidden="true">{localCount}</span> : null}</> : <span className={cells.emptyAction} aria-hidden="true"><span className={cells.emptyActionDash}>{UNKNOWN_VALUE}</span><Plus size={16} className={cells.emptyActionIcon} /></span>}</button></Tooltip>;
}

export function RecordAnnotationActions({ row }: { row: RecordRow }) {
  const annotations = useContext(AnnotationContext);
  const { t } = useTransaccionesWords();
  if (!annotations?.canRead) return null;
  const saved = annotations.read(row);
  const NoteIcon = saved.note ? StickyNote : Pencil;
  const note = annotations.noteEditable(row) || saved.note;
  const attachment = saved.attachments.length || row.hasProof || row.hasProof === false && annotations.attachmentEditable(row);
  if (!note && !attachment) return null;
  return <div className={cells.touchActions}>
    {note && row.report && !annotations.noteEditable(row) ? <button type="button" className={styles.icon} aria-label={t("business.transactions.layout.annotations.current_note")} onClick={(event) => { event.stopPropagation(); annotations.edit(row, "note"); }}><StickyNote size={16} aria-hidden="true" /></button> : note ? <Tooltip content={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} side="top"><button type="button" className={styles.icon} data-record-note={recordRowKey(row)} aria-label={t("business.transactions.layout.annotations.edit_note_for", { name: row.counterparty ?? t("business.transactions.unknown") })} onClick={(event) => { event.stopPropagation(); annotations.edit(row, "note"); }}><NoteIcon size={16} aria-hidden="true" /></button></Tooltip> : null}
    {attachment ? <RecordAttachmentPreview row={row} /> : null}
  </div>;
}

type EditorProps = { connected?: ConnectedAnnotations; pending: Map<string, PendingAnnotation>; selected: EditorSelection; initial: RecordAnnotation; limits: ReceiptLimits | null; canEdit: boolean; close: () => void; save: (value: RecordAnnotation) => void };
type FileSelectionState = { kind: "idle" } | { kind: "preparing" } | { kind: "error"; message: string } | { kind: "duplicates"; count: number };
function AnnotationEditor({ selected, initial, limits, canEdit, close, save, connected, pending }: EditorProps) {
  const { t, locale } = useTransaccionesWords();
  const { openPanel, chosen } = useBusiness();
  const documentNumbers = !connected && process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? previewRecordMetadata(selected.row, chosen?.space_id ?? null)?.documentNumbers ?? [] : [];
  const openEvidence = useContext(RecordEvidenceContext);
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const word = (key: string) => t(`business.transactions.layout.annotations.${key}`);
  const pendingKey = `${recordRowKey(selected.row)}:${selected.kind}`;
  const restored = pending.get(pendingKey);
  const [note, setNote] = useState(restored?.note ?? initial.note);
  const [attachments, setAttachments] = useState(restored?.attachments ?? initial.attachments);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ReportFailure | null>(restored?.problem ?? null);
  const [serverNote, setServerNote] = useState<string | null | undefined>(undefined);
  const version = useRef(restored?.version ?? selected.row.report?.revision ?? 0);
  const noteCommand = useRef<CurrentNoteCommand | null>(restored?.noteCommand ?? null);
  const fileCommand = useRef<SupportingFileCommand | null>(restored?.fileCommand ?? null);
  const queue = useRef<readonly LocalEvidence[] | null>(restored?.queue ?? null);
  const request = useRef<AbortController | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; request.current?.abort(); }; }, []);
  const denyAccess = (failure: ReportFailure) => {
    if (failure.kind !== 'access') return false;
    pending.clear(); connected?.revoke(); close(); return true;
  };
  const noteCount = connected ? Array.from(note).length : note.length;
  const closeEditor = () => { if (!busy) close(); };
  const saveConnected = async () => {
    if (!connected || !selected.row.report?.draft_id || busy || !canEdit) return;
    const abort = new AbortController(); request.current = abort; setBusy(true); setProblem(null);
    try {
      const draftId = selected.row.report.draft_id;
      if (selected.kind === "note") {
        noteCommand.current ??= { draftId, expectedVersion: version.current, note, key: crypto.randomUUID() };
        const answer = await setBusinessReportCurrentNote(connected.scope, noteCommand.current, abort.signal);
        version.current = answer.dossier.version;
      } else {
        queue.current ??= [...attachments];
        while (queue.current.length) {
          const entry = queue.current[0];
          fileCommand.current ??= { draftId, expectedVersion: version.current, file: entry.file, key: crypto.randomUUID() };
          const answer = await appendBusinessReportSupportingFile(connected.scope, fileCommand.current, abort.signal);
          version.current = answer.dossier.version;
          queue.current = queue.current.slice(1); fileCommand.current = null;
          if (alive.current) setAttachments(queue.current);
          if (queue.current.length && !answer.dossier.supporting_append_available) throw Object.assign(new Error("Annotation unavailable"), { status: 422, code: "business_annotation_unavailable" });
        }
      }
      await connected.refresh();
      if (!alive.current || abort.signal.aborted) return;
      pending.delete(pendingKey); close();
    } catch (error) {
      if (!alive.current || abort.signal.aborted) return;
      const failure = reportFailure(error, true);
      if (denyAccess(failure)) return;
      setProblem(failure);
      pending.set(pendingKey, { note, attachments: queue.current ?? attachments, noteCommand: noteCommand.current, fileCommand: fileCommand.current, queue: queue.current ?? attachments, version: version.current, problem: failure });
    } finally { if (alive.current) setBusy(false); }
  };
  const reloadVersion = async () => {
    if (!connected || !selected.row.report?.draft_id || busy) return;
    const abort = new AbortController(); request.current = abort; setBusy(true);
    try {
      const dossier = await getBusinessReportAnnotationDossier(connected.scope, selected.row.report.draft_id, abort.signal);
      if (!alive.current || abort.signal.aborted) return;
      version.current = dossier.version; setServerNote(dossier.current_note); noteCommand.current = null; fileCommand.current = null;
      pending.delete(pendingKey); setProblem(null);
      await connected.refresh();
    } catch (error) { if (alive.current && !abort.signal.aborted) { const failure = reportFailure(error); if (!denyAccess(failure)) setProblem(failure); } }
    finally { if (alive.current) setBusy(false); }
  };
  const [selection, setSelection] = useState<FileSelectionState>({ kind: "idle" });
  const pendingSelection = useRef(0);
  useEffect(() => () => { pendingSelection.current++; }, []);
  const field = useRef<HTMLTextAreaElement>(null);
  const opener = useRef(selected.opener);
  const fieldId = useId();
  const title = selected.kind === "note" ? t("business.transactions.columns.notas") : t("business.transactions.layout.column_attachment");
  const selectFiles = async (files: File[]) => {
    if (!canEdit || !limits || !files.length || busy || problem?.kind === "uncertain") return;
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
  const failure = problem ? <p role="alert" className={styles.error}>{t(problem.kind === "version" ? "business.dossier.stale" : `business.transactions.reporting.${problem.kind === "uncertain" ? "uncertain_view" : problem.kind === "access" ? "access_unavailable" : "unavailable"}`)}{problem.kind === "version" ? <button type="button" disabled={busy} className={quietButtonClass} onClick={() => void reloadVersion()}>{t("business.transactions.reporting.reload")}</button> : null}{problem.requestId ? <ReferenceCode reference={problem.requestId} /> : null}</p> : null;
  const downloadSource = async (receiptId: string, filename: string) => {
    if (!connected || busy) return;
    const abort = new AbortController(); request.current = abort; setBusy(true); setProblem(null);
    try { const blob = await downloadBusinessReportAttachment(connected.scope, receiptId, abort.signal); if (alive.current && !abort.signal.aborted) saveBlobDownload(blob, filename); }
    catch (error) { if (alive.current && !abort.signal.aborted) { const failure = reportFailure(error); if (!denyAccess(failure)) setProblem(failure); } }
    finally { if (alive.current) setBusy(false); }
  };
  const body = <div className={styles.content}>
    <div className={styles.recordContext}>
      <div><p className={styles.counterparty}>{selected.row.counterparty ?? t("business.transactions.unknown")}</p><p className={styles.recordKind}>{selected.row.report?.family === null ? <Unknown /> : t(`business.transactions.records.detail.${selected.row.kind}`)}{selected.kind === "attachment" ? <> · {formatRecordActivityDate(selected.row.occurredOn, locale)}</> : null}</p></div>
      {selected.kind === "attachment" ? <div className={styles.amount}>{selected.row.report && (selected.row.report.gross_amount === null || selected.row.report.currency === null) ? <Unknown /> : selected.row.report ? <span className="cuadrao-amount whitespace-nowrap tabular-nums">{formatMoney(selected.row.money.amount, selected.row.money.currency, locale)}</span> : <PlainAmount money={selected.row.money} />}</div> : null}
      {selected.kind === "attachment" && selected.row.account ? <p className={styles.account}>{t("business.transactions.columns.cuenta")} · <AccountLabel account={selected.row.account} /></p> : null}
    </div>
    {selected.kind === "note" ? <><label htmlFor={fieldId} className={styles.label}>{word("current_note")}</label><textarea ref={field} id={fieldId} className={styles.textarea} rows={4} maxLength={connected ? undefined : NOTE_LIMIT} value={note} readOnly={!canEdit || busy || problem?.kind === "uncertain"} aria-describedby={`${fieldId}-count`} onChange={(event) => setNote(connected ? event.target.value : event.target.value.slice(0, NOTE_LIMIT))} /><div id={`${fieldId}-count`} className="mt-1 text-right text-[13px] tabular-nums text-[#56635e] dark:text-white/55">{noteCount}/{NOTE_LIMIT}</div>{serverNote !== undefined ? <p className={styles.hint}>{word("current_note")} · {serverNote || t("business.dossier.not_recorded")}</p> : null}</> : <>
      <section aria-label={word("linked_evidence")} className={styles.linkedEvidence}>
        <h3 className={styles.label}>{word("linked_evidence")}</h3>
        {documentNumbers.length ? <p className={styles.hint}>{documentNumbers.join(" · ")}</p> : null}
        {connected && selected.row.report?.attachment_sources?.length ? <ul className={styles.fileList}>{selected.row.report.attachment_sources.map((source) => <li key={source.source_id}><button type="button" className={quietButtonClass} disabled={busy || !source.receipt_id || !source.source_available || !source.download_available} title={!source.download_available || !source.source_available ? word("linked_unavailable") : undefined} onClick={() => { if (source.receipt_id) void downloadSource(source.receipt_id, source.filename ?? word("received_document")); }}><FileText size={16} aria-hidden="true" />{source.filename ?? word("received_document")}</button></li>)}</ul> : selected.row.hasProof ? selected.row.opens ? <button type="button" className={quietButtonClass} onClick={openOriginal}><FileText size={16} aria-hidden="true" />{word("open_linked_attachment")}</button> : <p className={styles.hint}>{word("linked_unavailable")}</p> : <p className={styles.hint}>{word(selected.row.hasProof === null ? "linked_unknown" : "no_linked_attachment")}</p>}
        {canEdit ? <p className={styles.hint}>{word("received_unavailable")}</p> : null}
      </section>
      <ul className={styles.fileList} aria-label={word("local_preview")} data-local-files="">{attachments.map(({ digest, file }) => <li key={digest}><LocalFilePreview file={file} /></li>)}</ul>
      {canEdit && limits ? <RecordsEvidenceDropZone limits={limits} busy={busy || selection.kind === "preparing"} onFiles={(files) => { void selectFiles(files); }} /> : null}
      {selection.kind === "error" ? <p id={`${fieldId}-error`} role="alert" className={styles.error}>{selection.message}</p> : null}
      {selection.kind === "preparing" ? <p role="status" className={styles.hint}>{word("preparing_preview")}</p> : null}
      {selection.kind === "duplicates" ? <p role="status" className={styles.hint}>{t("business.transactions.layout.annotations.duplicates", { count: selection.count })}</p> : null}
      {!connected || attachments.length ? <p className={styles.disclosure}>{word("local_only")}</p> : null}
    </>}
    {failure}
  </div>;

  const footer = canEdit ? <div className={styles.footer}><button type="button" className={`${primaryButtonClass} w-full`} disabled={busy || problem?.kind === "version" || problem?.kind === "conflict" || problem?.kind === "access" || (selected.kind === "note" ? noteCount > NOTE_LIMIT : !attachments.length || selection.kind === "preparing" || selection.kind === "error")} onClick={() => { if (connected) { void saveConnected(); return; } save(selected.kind === "note" ? { ...initial, note: note.trim() } : { ...initial, attachments }); }}>{connected ? busy ? t("common.loading") : problem?.kind === "uncertain" ? t("common.retry") : t("common.save") : selected.kind === "note" ? t("common.save") : word("keep_local_preview")}</button></div> : null;
  return phone ? <BottomSheet isOpen onClose={closeEditor} title={title} closeLabel={t("common.close")} backLabel={t("common.back")} snaps={["half", "full"]} initialSnap={selected.kind === "attachment" ? "full" : "half"} footer={footer}>{body}</BottomSheet> : <DesktopEditor title={title} close={closeEditor} footer={footer} initialFocusRef={selected.kind === "note" ? field : undefined} returnFocusRef={opener}>{body}</DesktopEditor>;
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
