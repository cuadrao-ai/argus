"use client";

import { useContext, type MouseEvent } from "react";
import { FileText, Pencil, Plus, StickyNote } from "lucide-react";
import { Tooltip } from "@/components/ui/Tooltip";
import { useBusiness, type DossierDetailsCard } from "../BusinessWorkspace";
import { UNKNOWN_VALUE } from "../business-format";
import { RecordGlanceContext } from "./RecordGlanceContext";
import { recordRowKey } from "./records-row-preview";
import type { RecordRow } from "./transacciones-model";
import { Unknown } from "./transacciones-parts";
import { useTransaccionesWords } from "./transacciones-words";
import cells from "./transacciones-cells.module.css";

const COPY = "business.transactions.layout.annotations";
const ICON = "inline-flex size-11 shrink-0 items-center justify-center rounded-full text-black/60 hover:bg-black/[0.06] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/60 dark:hover:bg-white/[0.06]";

function useOpenDetails(row: RecordRow, detailsCard: DossierDetailsCard) {
  const { openPanel } = useBusiness();
  const openGlance = useContext(RecordGlanceContext);
  return (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!row.opens) return;
    if (openGlance) openGlance(row, { detailsCard });
    else openPanel({ ...row.opens, detailsCard });
  };
}

function EmptyAction({ icon: Icon }: { icon: typeof Plus }) {
  return <span className={cells.emptyAction} aria-hidden="true">
    <span className={cells.emptyActionDash}>{UNKNOWN_VALUE}</span><Icon size={16} className={cells.emptyActionIcon} />
  </span>;
}

export function RecordNoteLink({ row, compact = false }: { row: RecordRow; compact?: boolean }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const open = useOpenDetails(row, "note");
  if (!chosen?.capabilities.includes("read")) return compact ? null : <Unknown />;
  const note = row.report?.note;
  const canEdit = row.report?.can_edit_note === true;
  if (!row.opens || row.opens.kind === "expense" || (!note && !canEdit)) {
    if (compact) return null;
    return note ? <span className={cells.noteButton} title={note}>{note}</span> : <Unknown />;
  }
  const label = canEdit
    ? t(`${COPY}.edit_note_for`, { name: row.counterparty ?? t("business.transactions.unknown") })
    : t(`${COPY}.current_note`);
  const glyph = note ? <StickyNote size={16} aria-hidden="true" /> : <Pencil size={16} aria-hidden="true" />;
  return <Tooltip content={note || t(`${COPY}.add_note`)} side="top">
    <button type="button" data-record-note={recordRowKey(row)} className={note && !compact ? cells.noteButton : ICON} aria-label={label} onClick={open}>
      {compact ? glyph : note || <EmptyAction icon={Pencil} />}
    </button>
  </Tooltip>;
}

export function RecordSupportLink({ row, compact = false, legacy = false }: { row: RecordRow; compact?: boolean; legacy?: boolean }) {
  const { chosen } = useBusiness();
  const { t } = useTransaccionesWords();
  const open = useOpenDetails(row, "support");
  if (!chosen?.capabilities.includes("read")) return compact ? null : <Unknown />;
  const count = row.report?.attachment_sources?.length ?? 0;
  const existing = row.report ? count > 0 : row.hasProof === true;
  const canAppend = row.report?.draft_id && row.report.can_append_supporting === true;
  if (!existing && !canAppend) return compact ? null : <Unknown meaning={row.hasProof === false ? t(legacy ? "business.expenses.no_receipt" : `${COPY}.no_attachment`) : undefined} />;
  const countLabel = count > 0 ? t("business.intake.files_count", { count }) : "";
  const fileIcon = <>
    <FileText size={16} aria-hidden="true" />
    {!compact && count > 0 && <span className={cells.attachmentCount}>{count}</span>}
  </>;
  if (!row.opens) {
    const unavailable = t(`${COPY}.linked_unavailable`);
    return <Tooltip content={unavailable} side="top"><span role="img" aria-label={[unavailable, countLabel].filter(Boolean).join(" ")} className={ICON}>{fileIcon}</span></Tooltip>;
  }
  const label = t(`${COPY}.attachment_for`, { name: row.counterparty ?? t("business.transactions.unknown") });
  const hint = existing
    ? `${t("business.dossier.tab.detalles")} · ${t("business.dossier.supporting.title")}`
    : t(`${COPY}.add_attachment`);
  return <Tooltip content={hint} side="top">
    <button type="button" data-record-attachment={recordRowKey(row)} data-testid={existing ? "record-proof" : undefined} className={ICON} aria-label={countLabel ? `${label} (${countLabel})` : label} onClick={open}>
      {existing ? fileIcon : compact ? <Plus size={16} aria-hidden="true" /> : <EmptyAction icon={Plus} />}
    </button>
  </Tooltip>;
}

export function RecordDetailsLinks({ row }: { row: RecordRow }) {
  return <div className={cells.touchActions}><RecordNoteLink row={row} compact /><RecordSupportLink row={row} compact /></div>;
}
