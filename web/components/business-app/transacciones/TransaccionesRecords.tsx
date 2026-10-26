"use client";

import { Fragment, useContext, useState, type KeyboardEvent } from "react";
import { ArrowDown, ArrowUp, ChevronRight, FileText } from "lucide-react";
import { businessWorkspaceCurrency } from "@/lib/business-api";
import { currencySymbol } from "@/lib/money-entry";
import { useBusiness } from "../BusinessWorkspace";
import { formatAmount, formatRelativeDay, todayIso, UNKNOWN_VALUE } from "../business-format";
import { isOpenRecord } from "../record-tray";
import { Tooltip } from "@/components/ui/Tooltip";
import { RecordGlanceContext } from "./RecordGlanceContext";
import pageStyles from "./records-page.module.css";
import cellStyles from "./transacciones-cells.module.css";
import { RecordMarks, useOwnerView } from "../business-ui";
import { DENSITY_ROW_PX, type Density } from "./table-density";
import { headerCurrency, magnitude, type RecordRow } from "./transacciones-model";
import { AccountLabel, amountColumnSize, PlainAmount, SignedAmount, Truncated, Unknown } from "./transacciones-parts";
import { recordsColumnLabelKey, visibleRecordsColumns, recordsMinimumWidth, type RecordsViewPreferences } from "./records-view-preferences";
import { formatRecordActivityDate, previewAmountColumnSize, recordRowKey } from "./records-row-preview";
import RecordWorkflowBadge from "./RecordWorkflowBadge";
import { RecordAnnotationActions, RecordAttachmentPreview, RecordNotePreview } from "./RecordsAnnotationsPreview";
import type { RecordsSort } from "./records-pagination";
import { CELL, COLUMNS, PIN_CLASS } from "./TransaccionesTable";
import { useTransaccionesWords } from "./transacciones-words";

const nameOf = (row: RecordRow) => row.counterparty ?? UNKNOWN_VALUE;
export { recordRowKey } from "./records-row-preview";

/** The proof column for a saved record: the receipt icon when a file backs it, a dash that says "no receipt" when none does, a dash that says "no data" when no read says. An empty cell is a question. */
function Proof({ row }: { row: RecordRow }) {
  const { t } = useTransaccionesWords();
  if (row.hasProof === null) return <Unknown />;
  if (!row.hasProof) return <Unknown meaning={t("business.expenses.no_receipt")} />;
  return (
    <span data-testid="record-proof" role="img" aria-label={t("business.transactions.records.proof")} className="inline-flex h-8 w-8 items-center justify-center text-[#56635e] dark:text-white/65">
      <FileText className="h-4 w-4" aria-hidden="true" />
    </span>
  );
}

/**
 * The period's saved gastos and ventas in the ledger's columns, with no
 * igualar state. A row opens its record in the record tray; a venta has no
 * record screen yet, so its row is plain.
 */
export function RecordsTable({ records, density, rowRef, order: controlledOrder, onOrderChange, preferences, sort, onSortChange, amountSortAvailable = false, sortNoticeId }: { sort?: RecordsSort; onSortChange?: (sort: RecordsSort) => void; amountSortAvailable?: boolean; sortNoticeId?: string; preferences?: RecordsViewPreferences; order?: "desc" | "asc"; onOrderChange?: (order: "desc" | "asc") => void; records: readonly RecordRow[]; density: Density; rowRef: (id: string, node: HTMLElement | null) => void }) {
  const { t, locale } = useTransaccionesWords();
  const owner = useOwnerView();
  const openGlance = useContext(RecordGlanceContext);
  const { panel, openPanel, records: workspace } = useBusiness();
  const [localOrder, setLocalOrder] = useState<"desc" | "asc">("desc");
  const order = sort?.direction ?? controlledOrder ?? localOrder;
  const rows = sort || controlledOrder ? records : order === "desc" ? records : [...records].reverse();
  const toggleOrder = () => { const next = order === "desc" ? "asc" : "desc"; if (onOrderChange) onOrderChange(next); else setLocalOrder(next); };
  const header = preferences ? null : headerCurrency(records, businessWorkspaceCurrency(workspace?.workspace));
  const amountSize = preferences ? previewAmountColumnSize(records.map((row) => row.money), locale) : amountColumnSize(records.map((row) => row.money), header, locale);
  const columns = preferences ? visibleRecordsColumns(preferences) : COLUMNS;
  const proofPinned = columns.at(-1)?.key === "comprobante";
  const today = todayIso();
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const tabStop = focusedId && rows.some((row) => recordRowKey(row) === focusedId) ? focusedId : rows[0] ? recordRowKey(rows[0]) : undefined;

  const onKeyDown = (event: KeyboardEvent<HTMLTableElement>) => {
    if (event.target instanceof HTMLElement && event.target.closest("button, a, input, textarea, [role=menu]")) return;
    const id = (event.target as HTMLElement).closest<HTMLTableRowElement>("tr[data-record-id]")?.dataset.recordKey;
    const index = rows.findIndex((row) => recordRowKey(row) === id);
    if (index < 0) return;
    const move = (to: number) => {
      const target = rows[Math.max(0, Math.min(rows.length - 1, to))];
      setFocusedId(recordRowKey(target));
      (event.currentTarget.querySelector(`tr[data-record-key="${CSS.escape(recordRowKey(target))}"]`) as HTMLElement | null)?.focus();
    };
    if (event.key === "ArrowDown") move(index + 1);
    else if (event.key === "ArrowUp") move(index - 1);
    else if (event.key === "Enter" && rows[index].opens) { if (openGlance) openGlance(rows[index]); else openPanel(rows[index].opens!); }
    else return;
    event.preventDefault();
  };

  return (
    <div data-testid="transacciones-scroll" className="argus-thin-scrollbar relative max-h-[calc(100dvh-15rem)] min-h-[16rem] overflow-auto rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
      <table role="grid" aria-label={t("business.transactions.title")} aria-rowcount={rows.length} data-testid="transacciones-records" data-density={density} onKeyDown={onKeyDown} style={{ minWidth: recordsMinimumWidth(columns, amountSize) }} className={`w-full ${preferences ? "" : "min-w-[1100px]"} table-fixed border-separate border-spacing-0 text-[14px] text-[#172b26] dark:text-white`}>
        <colgroup>{columns.map((column) => <col key={column.key} style={column.key === "monto" ? { width: amountSize.width } : column.width ? { width: column.width } : undefined} />)}</colgroup>
        <thead>
          <tr>
            {columns.map((column) => {
              const label = preferences ? t(recordsColumnLabelKey(column.key), { currency: "" }).trim() : column.key === "monto" ? t("business.transactions.columns.monto", { currency: header ? currencySymbol(header) : "" }).trim() : t(`business.transactions.columns.${column.key}`);
              const sortableKey = column.key === "fecha" || column.key === "monto" || column.key === "contraparte" ? column.key : null;
              const sortHere = sort ? column.key === sort.key : column.key === "fecha";
              const canSort = sort ? sortableKey !== null : sortHere;
              const blocked = Boolean(sort && column.key === "monto" && !amountSortAvailable);
              return (
                <th key={column.key} scope="col" data-col={column.key} data-pinned={column.pin ? `top ${column.pin}` : "top"} aria-sort={sortHere ? (order === "desc" ? "descending" : "ascending") : undefined} className={`sticky top-0 h-11 border-b border-[#DCE0DA] bg-white px-3 text-[13px] font-normal text-[#56635e] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/65 ${column.align === "right" ? "text-right" : "text-left"} ${column.pin ? `${column.pin === "left" ? "left-0" : "right-0"} z-30` : "z-20"}`}>
                  {canSort ? (
                    <button type="button" aria-disabled={blocked || undefined} aria-describedby={blocked ? sortNoticeId : undefined} title={blocked ? t("business.transactions.pagination.amount_requires_currency") : undefined} onClick={() => {
                      if (sort && onSortChange && sortableKey) onSortChange({ key: sortableKey, direction: sort.key === sortableKey ? sort.direction === "desc" ? "asc" : "desc" : sortableKey === "contraparte" ? "asc" : "desc" });
                      else toggleOrder();
                    }} className={`${pageStyles.sortHeading} ${column.align === "right" ? pageStyles.sortRight : ""}`}>
                      {label}
                      {sortHere ? order === "desc" ? <ArrowDown data-testid="sort-arrow" className="h-3.5 w-3.5" aria-hidden="true" /> : <ArrowUp data-testid="sort-arrow" className="h-3.5 w-3.5" aria-hidden="true" /> : null}
                    </button>
                  ) : label}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const opens = row.opens;
            const open = opens ? isOpenRecord(panel, opens) : false;
            const cells = {
              contraparte: (<td data-col="contraparte" data-pinned="left" className={`${CELL} ${PIN_CLASS.left} text-left group-aria-selected:shadow-[inset_2px_0_0_var(--cuadrao-green),inset_-1px_0_0_#DCE0DA]`}><Truncated text={nameOf(row)} className="font-medium" /></td>),
              fecha: (<td data-col="fecha" className={`${CELL} whitespace-nowrap text-left text-[#56635e] dark:text-white/65`}>{preferences ? formatRecordActivityDate(row.occurredOn, locale) : formatRelativeDay(row.occurredOn, today, locale)}</td>),
              monto: (<td data-col="monto" className={`${CELL} text-right font-medium tabular-nums`}>{preferences ? <span className="cuadrao-amount whitespace-nowrap">{formatAmount(magnitude(row.money).amount, row.money.currency, locale)}</span> : <SignedAmount money={row.money} header={header} />}</td>),
              moneda: (<td data-col="moneda" className={`${CELL} whitespace-nowrap text-left text-[#56635e] dark:text-white/65`}>{currencySymbol(row.money.currency)}</td>),
              notas: (<td data-col="notas" className={`${CELL} text-left`}><RecordNotePreview row={row} /></td>),
              detalle: (<td data-col="detalle" className={`${CELL} text-left text-[#56635e] dark:text-white/65`}>
                  {preferences ? t(`business.transactions.records.detail.${row.kind}`) : <Tooltip side="top" content={[t(`business.transactions.records.detail.${row.kind}`), row.marks.personal ? t("business.marks.personal_chip") : null, row.marks.fiscal ? t(`business.marks.${row.marks.fiscal === "sin_comprobante" ? "sin_comprobante_chip" : "missing_ncf_chip"}`) : null, row.marks.personal && owner && row.marks.markedBy ? t("business.marks.marked_by", { name: row.marks.markedBy }) : null].filter(Boolean).join(" · ")}>
                    <span className={cellStyles.detail} tabIndex={recordRowKey(row) === tabStop ? 0 : -1}>{t(`business.transactions.records.detail.${row.kind}`)}<RecordMarks personal={row.marks.personal} fiscal={row.marks.fiscal} markedBy={row.marks.markedBy} /></span>
                  </Tooltip>}
                </td>),
              estado: (<td data-col="estado" className={`${CELL} text-left`}><RecordWorkflowBadge row={row} /></td>),
              categoria: (<td data-col="categoria" className={`${CELL} text-left`}>{row.categoryId ? <Truncated text={t(`business.category.${row.categoryId}`, { defaultValue: row.categoryId })} /> : <Unknown />}</td>),
              cuenta: (<td data-col="cuenta" className={`${CELL} text-left`}><AccountLabel account={row.account} /></td>),
              comprobante: (<td data-col="comprobante" data-pinned={proofPinned ? "right" : undefined} className={`${CELL} ${proofPinned ? PIN_CLASS.right : ""} text-right`}>{preferences ? <RecordAttachmentPreview row={row} /> : <Proof row={row} />}</td>),
            };
            return (
              <tr
                key={recordRowKey(row)}
                ref={(node) => rowRef(recordRowKey(row), node)}
                data-record-id={row.id} data-record-key={recordRowKey(row)}
                data-kind={row.kind}
                aria-selected={open}
                tabIndex={recordRowKey(row) === tabStop ? 0 : -1}
                style={{ height: DENSITY_ROW_PX[density] }}
                onFocus={(event) => { if (event.target === event.currentTarget) setFocusedId(recordRowKey(row)); }}
                onClick={opens ? () => { if (openGlance) openGlance(row); else openPanel(opens); } : undefined}
                className={`group outline-none focus-visible:[&>td]:shadow-[inset_0_2px_0_var(--cuadrao-green),inset_0_-2px_0_var(--cuadrao-green)] ${opens ? "cursor-pointer" : ""}`}
              >
                {columns.map((column) => <Fragment key={column.key}>{cells[column.key]}</Fragment>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The saved records on a phone: two-line rows of at least 64px; a row with a record opens it as a full page. */
export function RecordsList({ records, rowRef }: { records: readonly RecordRow[]; rowRef: (id: string, node: HTMLElement | null) => void }) {
  const { t, locale } = useTransaccionesWords();
  const { panel, openPanel, records: workspace } = useBusiness();
  const header = headerCurrency(records, businessWorkspaceCurrency(workspace?.workspace));
  const today = todayIso();
  return (
    <ul data-testid="transacciones-records" className="overflow-hidden rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
      {records.map((row) => {
        const opens = row.opens;
        const body = (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px] font-medium text-[#172b26] dark:text-white">{nameOf(row)}</span>
              <span className="mt-0.5 block truncate text-[13px] text-[#56635e] dark:text-white/65">{formatRelativeDay(row.occurredOn, today, locale)} · {t(`business.transactions.records.detail.${row.kind}`)}</span>
              <RecordMarks personal={row.marks.personal} fiscal={row.marks.fiscal} markedBy={row.marks.markedBy} className="mt-1" />
            </span>
            <span className="shrink-0 text-right text-[15px] font-medium text-[#172b26] dark:text-white"><SignedAmount money={row.money} header={header} /></span>
            {row.hasProof ? <Proof row={row} /> : null}
          </>
        );
        const rowClass = "flex min-h-16 w-full min-w-0 items-center gap-3 py-2.5 pl-4 pr-3 text-left";
        return (
          <li key={recordRowKey(row)} data-record-id={row.id} data-record-key={recordRowKey(row)} data-kind={row.kind} aria-current={opens && isOpenRecord(panel, opens) ? "true" : undefined} className="border-b border-[#DCE0DA] last:border-b-0 aria-[current=true]:bg-[#eef3ec] dark:border-white/10 dark:aria-[current=true]:bg-[#24302b]">
            {opens ? (
              <button ref={(node) => rowRef(recordRowKey(row), node)} type="button" onClick={() => openPanel(opens)} className={`${rowClass} rounded-item focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)]`}>
                {body}
                <ChevronRight className="h-4 w-4 shrink-0 text-[#56635e] dark:text-white/50" aria-hidden="true" />
              </button>
            ) : (
              <div className={rowClass}>{body}<span className="w-4 shrink-0" aria-hidden="true" /></div>
            )}
          </li>
        );
      })}
    </ul>
  );
}


/** Narrow saved-record preview. Only this or the table mounts, so row refs stay unique. */
export function RecordsNarrowList({ records, rowRef }: { records: readonly RecordRow[]; rowRef: (id: string, node: HTMLElement | null) => void }) {
  const { t, locale } = useTransaccionesWords();
  const { panel, openPanel } = useBusiness();
  const openGlance = useContext(RecordGlanceContext);
  return <ul className={pageStyles.list} data-testid="transacciones-records">
    {records.map((row) => {
      const opens = row.opens;
      const body = <><span className={pageStyles.top}><Truncated text={nameOf(row)} className={pageStyles.name} /><span className={pageStyles.amount}><PlainAmount money={row.money} /></span></span>
        <span className={pageStyles.meta}><span className={pageStyles.marks}>{t(`business.transactions.records.detail.${row.kind}`)}<RecordWorkflowBadge row={row} /></span><span className={pageStyles.date}>{formatRecordActivityDate(row.occurredOn, locale)}</span></span></>;
      return <li key={recordRowKey(row)} data-record-id={row.id} data-record-key={recordRowKey(row)} data-kind={row.kind} aria-current={opens && isOpenRecord(panel, opens) ? "true" : undefined} className={pageStyles.narrowRecord}>
        {opens ? <button type="button" ref={(node) => rowRef(recordRowKey(row), node)} className={pageStyles.row} onClick={() => { if (openGlance) openGlance(row); else openPanel(opens); }}>{body}</button> : <div className={pageStyles.row}>{body}</div>}
        <RecordAnnotationActions row={row} />
      </li>;
    })}
  </ul>;
}
