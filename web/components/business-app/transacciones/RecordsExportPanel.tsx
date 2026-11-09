"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { ChevronLeft, Loader2 } from "lucide-react";
import BottomSheet from "@/components/ui/BottomSheet";
import CenteredDialog from "@/components/ui/CenteredDialog";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { joinCurrencyList } from "@/lib/business-month-close";
import { recordColumnKey, reportFailure, type ReportFailure, type ReportingTransport } from "@/lib/business-reporting-wire";
import type { ExportColumnKey, ExportPreview, RecordsExportChoice, RecordsExportFile, ReportRequest, ReportScope } from "@/lib/business-reports-api";
import { saveBlobDownload } from "../ExportRecordsPanel";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { showToast } from "../foundation/toasts";
import { recordsColumnLabelKey } from "./records-view-preferences";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

type Mode = RecordsExportChoice["mode"];
type Format = RecordsExportChoice["format"];
type Currencies = "all" | "current";
type Load = { kind: "loading" } | { kind: "ready"; preview: ExportPreview } | { kind: "failed"; problem: ReportFailure };
type Run = { kind: "idle" | "preparing" } | { kind: "failed"; problem: ReportFailure };
const LIMIT_CODES = new Set(["business_report_too_large"]);

export type RecordsExportProps = {
  scope: ReportScope;
  /** The table's own request: tab, period, currency, filters and layout. */
  request: ReportRequest;
  /** The screen's period, as its date control names it. */
  periodLabel: string;
  /** Optional filters and search the screen has on. */
  filterCount: number;
  transport: Pick<ReportingTransport, "exportPreview" | "exportFile">;
  /** Applies the Faltan datos fiscales filter, as the card does. */
  onReviewFiscal: () => void;
  onClose: () => void;
};

/**
 * Exportar in Registros: the table as the person sees it, or the month's 606/607
 * lines, as one Excel or CSV file. Every count and notice is the server's.
 */
export default function RecordsExportPanel({ scope, request, periodLabel, filterCount, transport, onReviewFiscal, onClose }: RecordsExportProps) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop } = useResponsiveLayout();
  const sale = request.filters.record_families[0] === "sale";
  const current = request.filters.currencies[0] ?? "";
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<Mode>("table");
  const [chosen, setChosen] = useState<ExportColumnKey[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [currencies, setCurrencies] = useState<Currencies>("all");
  const [format, setFormat] = useState<Format>("xlsx");
  const [run, setRun] = useState<Run>({ kind: "idle" });
  const running = useRef<AbortController | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    setLoad({ kind: "loading" });
    transport.exportPreview(scope, request, abort.signal).then(
      (preview) => { if (!abort.signal.aborted) setLoad({ kind: "ready", preview }); },
      (error) => { if (!abort.signal.aborted) setLoad({ kind: "failed", problem: reportFailure(error) }); },
    );
    return () => abort.abort();
  }, [scope, request, transport, attempt]);
  // Closing the panel cancels the file in flight: nothing downloads after it is gone.
  useEffect(() => () => running.current?.abort(), []);

  const preview = load.kind === "ready" ? load.preview : null;
  const tableColumns = preview?.table.columns ?? [];
  const ownColumns = tableColumns.filter((column) => column.shown).map((column) => column.key);
  const columns = chosen ?? ownColumns;
  const everyCurrency = currencies === "all" && preview?.table.all !== null;
  const selection = preview ? (everyCurrency ? preview.table.all : preview.table.current) : null;
  const count = preview ? (mode === "dgii" ? preview.dgii.record_count : selection?.record_count ?? 0) : null;
  const label = (key: ExportColumnKey) => t(recordsColumnLabelKey(recordColumnKey(key)), { currency: "" }).trim();

  const summary = !preview ? [periodLabel] : mode === "dgii"
    ? [periodLabel, t(sale ? "business.transactions.reporting.export.summary_dgii_sales" : "business.transactions.reporting.export.summary_dgii_purchases"), t("business.transactions.reporting.export.summary_records", { count })]
    : [periodLabel, filterCount ? t("business.transactions.reporting.export.summary_filters", { count: filterCount }) : null, t("business.transactions.reporting.export.summary_records", { count }), (selection?.currencies.length ?? 0) > 1 ? t("business.transactions.reporting.export.summary_currencies", { count: selection?.currencies.length }) : null];

  const download = async () => {
    if (!preview || !count || running.current) return;
    const choice: RecordsExportChoice = mode === "dgii" ? { mode, format } : { mode, format, columns, currencies: everyCurrency ? "all" : "current" };
    const abort = new AbortController();
    running.current = abort;
    setRun({ kind: "preparing" });
    let file: RecordsExportFile;
    try {
      file = await transport.exportFile(scope, request, choice, abort.signal);
    } catch (error) {
      if (abort.signal.aborted) return;
      running.current = null;
      setRun({ kind: "failed", problem: reportFailure(error) });
      return;
    }
    if (abort.signal.aborted) return;
    running.current = null;
    saveBlobDownload(file.blob, file.filename);
    onClose();
    // The same bytes again, never a second request.
    showToast({ kind: "success", text: t("business.transactions.reporting.export.done"), action: { label: t("business.transactions.reporting.export.download_again"), run: () => saveBlobDownload(file.blob, file.filename) } });
  };

  const toggle = (key: ExportColumnKey) => setChosen(columns.includes(key) ? columns.filter((item) => item !== key) : tableColumns.map((column) => column.key).filter((item) => item === key || columns.includes(item)));
  const custom = chosen !== null && (chosen.length !== ownColumns.length || chosen.some((key) => !ownColumns.includes(key)));
  const problem = run.kind === "failed" ? run.problem : load.kind === "failed" ? load.problem : null;
  const preparing = run.kind === "preparing";

  const footer = editing ? (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <button type="button" className={quietButtonClass} onClick={() => setChosen(null)}>{t("business.transactions.reporting.export.columns_reset")}</button>
      <button type="button" className={primaryButtonClass} onClick={() => setEditing(false)}>{t("business.transactions.reporting.export.columns_done")}</button>
    </div>
  ) : (
    <div className="space-y-2">
      {problem ? <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">
        {problem.kind === "access" ? t("business.transactions.reporting.access_unavailable") : LIMIT_CODES.has(problem.code) ? t("business.export.limit_error") : t("business.transactions.reporting.export.error")}
        {problem.kind !== "access" ? <> <button type="button" className={quietButtonClass} onClick={() => { if (run.kind === "failed") void download(); else setAttempt((value) => value + 1); }}>{t("common.retry")}</button></> : null}
        {problem.requestId ? <ReferenceCode reference={problem.requestId} /> : null}
      </p> : null}
      {count === 0 ? <p role="status" className="text-[13px] text-[#56635e] dark:text-white/70">{t("business.transactions.reporting.export.empty")}</p> : null}
      <button type="button" data-testid="records-export-download" disabled={!count || preparing} aria-busy={preparing || undefined} onClick={() => void download()} className={`${primaryButtonClass} w-full`}>
        {preparing ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
        {preparing ? t("business.transactions.reporting.export.preparing") : count === null ? t("business.export.action") : t("business.transactions.reporting.export.action", { count })}
      </button>
    </div>
  );

  const tabTitle = t(sale ? "business.transactions.reporting.export.title_sales" : "business.transactions.reporting.export.title_purchases");
  const title = editing ? t("business.transactions.reporting.export.columns_title") : tabTitle;
  const body = (
    <div className={isBelowDesktop ? "pb-5 pt-1" : "px-6 pb-5 pt-1"} data-testid="records-export-panel" aria-busy={load.kind === "loading" || undefined}>
      {editing && preview ? <>
        {/* The column choice is a step inside this dialog; the arrow returns to it. */}
        <button type="button" data-testid="records-export-back" onClick={() => setEditing(false)} className="-ml-1 mb-1 flex min-h-11 items-center gap-1.5 rounded-full px-1 text-[14px] text-[#56635e] hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/70 dark:hover:text-white">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />{tabTitle}
        </button>
        <ul data-testid="records-export-columns">
          {tableColumns.map(({ key }) => <Fragment key={key}>
            <li><label className={styles.choice}>
              <input type="checkbox" checked={key === "counterparty" || columns.includes(key)} disabled={key === "counterparty"} onChange={() => toggle(key)} />
              <span>{label(key)}</span>
            </label></li>
            {/* All currencies put Moneda after Monto in the file, locked on. */}
            {key === "gross_amount" && everyCurrency ? <li><label className={styles.choice}><input type="checkbox" checked disabled /><span>{t("business.transactions.columns.moneda")}</span></label></li> : null}
          </Fragment>)}
        </ul>
      </> : <>
        <p data-testid="records-export-summary" className="mb-4 text-[14px] text-[#56635e] dark:text-white/70">{summary.filter(Boolean).join(" · ")}</p>
        <div role="radiogroup" aria-label={t("business.transactions.reporting.export.what")} className="space-y-2">
          {(["table", "dgii"] as const).map((key) => <label key={key} data-testid={`records-export-mode-${key}`} className="flex min-h-14 cursor-pointer items-center gap-3 rounded-item border border-black/15 px-3 py-2 dark:border-white/20">
            <input type="radio" name="records-export-mode" checked={mode === key} onChange={() => setMode(key)} />
            <span className="min-w-0 text-[14px]">
              <span className="block font-medium">{key === "table" ? t("business.transactions.reporting.export.table_title") : t("business.transactions.reporting.export.dgii_title", { form: sale ? "607" : "606" })}</span>
              <span className="block text-black/60 dark:text-white/60">{t(key === "table" ? "business.transactions.reporting.export.table_body" : "business.transactions.reporting.export.dgii_body")}</span>
            </span>
          </label>)}
        </div>
        {preview && mode === "table" ? <>
          <div className="mt-3 flex min-h-11 items-center justify-between gap-3">
            <span className="text-[14px]">{t(custom ? "business.transactions.reporting.export.columns_custom" : "business.transactions.reporting.export.columns_table", { count: columns.length })}</span>
            <button type="button" data-testid="records-export-edit-columns" className={quietButtonClass} onClick={() => setEditing(true)}>{t("business.transactions.reporting.export.columns_edit")}</button>
          </div>
          <div className="mt-3"><SegmentedControl fill testId="records-export-currencies" label={t("business.transactions.reporting.export.currencies")} disabled={preview.table.all === null} value={everyCurrency ? "all" : "current"} onChange={setCurrencies} segments={[{ key: "all" as const, label: t("business.transactions.reporting.export.currencies_all") }, { key: "current" as const, label: t("business.transactions.reporting.export.currencies_current", { currency: current }) }]} /></div>
        </> : null}
        {preview && mode === "dgii" ? <div className="mt-4 space-y-2 text-[14px]" data-testid="records-export-dgii">
          <p>{t("business.transactions.reporting.export.dgii_note")}</p>
          {preview.dgii.pending_fiscal_count ? <p>{t(sale ? "business.transactions.reporting.export.pending_fiscal_sales" : "business.transactions.reporting.export.pending_fiscal_purchases", { count: preview.dgii.pending_fiscal_count })} <button type="button" className={quietButtonClass} onClick={() => { onClose(); onReviewFiscal(); }}>{t("business.transactions.reporting.export.review")}</button></p> : null}
          {preview.dgii.pending_rate_count ? <p>{t(sale ? "business.transactions.reporting.export.pending_rate_sales" : "business.transactions.reporting.export.pending_rate_purchases", { count: preview.dgii.pending_rate_count, currencies: joinCurrencyList(preview.dgii.pending_rate_currencies, t("business.month_close.list_and")) })}</p> : null}
        </div> : null}
        {preview ? <div className="mt-3"><SegmentedControl fill testId="records-export-format" label={t("business.transactions.reporting.export.format")} value={format} onChange={setFormat} segments={[{ key: "xlsx" as const, label: t("business.transactions.reporting.export.format_xlsx") }, { key: "csv" as const, label: t("business.transactions.reporting.export.format_csv") }]} /></div> : null}
      </>}
    </div>
  );

  // A centered dialog on desktop, the shared bottom sheet on a phone.
  if (isBelowDesktop) return <BottomSheet isOpen onClose={onClose} title={title} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" footer={footer}>{body}</BottomSheet>;
  return <CenteredDialog title={title} closeLabel={t("common.close")} onClose={onClose} footer={footer} testId="records-export-dialog">{body}</CenteredDialog>;
}
