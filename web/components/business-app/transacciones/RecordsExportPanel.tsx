"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import type { TFunction } from "i18next";
import { ChevronLeft, CircleMinus, TriangleAlert } from "lucide-react";
import BottomSheet from "@/components/ui/BottomSheet";
import CenteredDialog from "@/components/ui/CenteredDialog";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { joinCurrencyList } from "@/lib/business-month-close";
import { reportFailure, type ReportFailure, type ReportingTransport } from "@/lib/business-reporting-wire";
import type { ExportPreview, RecordsExportChoice, RecordsExportFile } from "@/lib/business-reports-api";
import { saveBlobDownload } from "@/lib/save-blob-download";
import { canSaveAs } from "@/lib/save-file-as";
import DgiiRegistryTag from "../DgiiRegistryTag";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import GuideCard from "../foundation/GuideCard";
import { showToast } from "../foundation/toasts";
import { exportFailureText, failureOn, useRecordsExportJob, type ExportPanelRequest } from "./records-export-job";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

type Mode = RecordsExportChoice["mode"];
type Format = RecordsExportChoice["format"];
type Currencies = "all" | "current";
type Load = { kind: "loading" } | { kind: "ready"; preview: ExportPreview } | { kind: "failed"; problem: ReportFailure };
const SAVE_TIP = "business.guide_cards.exportar_guardar.";
const noticeLinkClass = "inline min-h-0! min-w-0! cursor-pointer whitespace-nowrap rounded-mark text-[14px] leading-[inherit] text-[var(--cuadrao-green)] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)]";

const noticeClass = "flex items-start gap-2";
const noticeMark = <CircleMinus className="mt-0.5 h-4 w-4 shrink-0 text-[#7d8a84] dark:text-white/50" aria-hidden="true" />;

/** A notice's action in its own right-hand column, so the sentence wraps beside it. */
function NoticeAction({ children }: { children: ReactNode }) {
  return <span data-testid="records-export-notice-action" className="ml-4 min-w-[112px] shrink-0 text-right">{children}</span>;
}

/** The result of a finished export, said once in a toast. */
function sayExported(t: TFunction, result: "saved" | "downloaded", file: RecordsExportFile) {
  if (result === "saved") showToast({ kind: "success", text: t("business.transactions.reporting.export.saved") });
  // The same bytes again, never a second request.
  else showToast({ kind: "success", text: t("business.transactions.reporting.export.done"), action: { label: t("business.transactions.reporting.export.download_again"), run: () => saveBlobDownload(file.blob, file.filename) } });
}

export type RecordsExportProps = ExportPanelRequest & {
  transport: Pick<ReportingTransport, "exportPreview" | "exportFile">;
  /** Shows pending fiscal records for the tab, period and form currency, clearing other filters. */
  onReviewFiscal: (currency: string) => void;
  /** Opens the Bandeja. Absent for a person who cannot work there: the count shows with no link. */
  onOpenBandeja?: () => void;
  onClose: () => void;
};

/**
 * Exportar in Registros: the table as the person sees it, or the month's 606
 * lines, as one Excel or CSV file. Every count and notice is the server's.
 */
export default function RecordsExportPanel({ scope, request, periodLabel, filterCount, transport, onReviewFiscal, onOpenBandeja, onClose }: RecordsExportProps) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop } = useResponsiveLayout();
  const sale = request.filters.record_families[0] === "sale";
  const current = request.filters.currencies[0] ?? "";
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const { job, state } = useRecordsExportJob();
  // Opened on a file that failed, the panel starts on that file's choices.
  const [seed] = useState(() => failureOn(state, { scope, request })?.run.choice);
  const [selectedMode, setMode] = useState<Mode>(seed?.mode ?? "table");
  const [chosen, setChosen] = useState<string[] | null>(seed?.mode === "table" ? seed.columns : null);
  const [editing, setEditing] = useState(false);
  const [currencies, setCurrencies] = useState<Currencies>(seed?.mode === "table" ? seed.currencies : "all");
  const [suppliersExpanded, setSuppliersExpanded] = useState(false);
  const suppliersId = useId();
  const [format, setFormat] = useState<Format>(seed?.format ?? "xlsx");

  useEffect(() => {
    const abort = new AbortController();
    setLoad({ kind: "loading" });
    transport.exportPreview(scope, request, abort.signal).then(
      (preview) => { if (!abort.signal.aborted) setLoad({ kind: "ready", preview }); },
      (error) => { if (!abort.signal.aborted) setLoad({ kind: "failed", problem: reportFailure(error) }); },
    );
    return () => abort.abort();
  }, [scope, request, transport, attempt]);

  const preview = load.kind === "ready" ? load.preview : null;
  const dgii = preview?.dgii;
  const mode: Mode = dgii ? selectedMode : "table";
  const everyCurrency = currencies === "all" && preview?.table.all !== null;
  const selection = preview ? (everyCurrency ? preview.table.all : preview.table.current) : null;
  // The server lists the file's columns for this currency choice; a required one is always checked.
  const fileColumns = selection?.columns ?? [];
  const ownColumns = fileColumns.filter((column) => column.shown || column.required).map((column) => column.key);
  const checked = (key: string) => (chosen ?? ownColumns).includes(key) || fileColumns.some((column) => column.key === key && column.required);
  const columns = fileColumns.map((column) => column.key).filter(checked);
  const count = preview ? (mode === "dgii" && dgii ? dgii.record_count : selection?.record_count ?? 0) : null;

  const summary = !preview ? [periodLabel] : mode === "dgii" && dgii
    ? dgii.pending_count
      ? [periodLabel, t("business.transactions.reporting.export.summary_dgii_ready", { count }), t("business.transactions.reporting.export.summary_dgii_pending", { count: dgii.pending_count })]
      : [periodLabel, t("business.transactions.reporting.export.summary_dgii_purchases"), t("business.transactions.reporting.export.summary_records", { count })]
    : [periodLabel, filterCount ? t("business.transactions.reporting.export.summary_filters", { count: filterCount }) : null, t("business.transactions.reporting.export.summary_records", { count }), (selection?.currencies.length ?? 0) > 1 ? t("business.transactions.reporting.export.summary_currencies", { count: selection?.currencies.length }) : null];

  // The file this panel would download now. Until the preview answers, nothing in it can have changed.
  const choice: RecordsExportChoice | null = !preview || !selection ? null : mode === "dgii" ? { mode, format } : { mode, format, columns, currencies: everyCurrency ? "all" : "current" };
  const failed = failureOn(state, { scope, request }, choice);

  const download = () => {
    if (!choice || !count || !selection) return;
    const filename = (mode === "dgii" && dgii ? dgii : selection).filenames[format];
    void job.start({ panel: { scope, request, periodLabel, filterCount }, choice, filename, exportFile: transport.exportFile, onSaved: (result, file) => sayExported(t, result, file) });
  };

  const toggle = (key: string) => setChosen(columns.includes(key) ? columns.filter((item) => item !== key) : fileColumns.map((column) => column.key).filter((item) => item === key || columns.includes(item)));
  const custom = chosen !== null && (columns.length !== ownColumns.length || columns.some((key) => !ownColumns.includes(key)));
  const problem = failed?.problem ?? (load.kind === "failed" ? load.problem : null);

  const supplierLines = dgii?.rnc_suppliers.map((supplier) => <li key={supplier.rnc}>
    <div className="flex items-start justify-between gap-3">
      <span className="min-w-0">{supplier.name}</span>
      <span className="shrink-0"><DgiiRegistryTag status={supplier.status === "rnc_inactive" ? "inactive" : "unverified"} /></span>
    </div>
    <span className="block font-mono">{supplier.rnc}</span>
  </li>);
  const pendingFiscalSentence = dgii?.pending_fiscal_count ? t("business.transactions.reporting.export.pending_fiscal_purchases", { count: dgii.pending_fiscal_count }) : null;
  const reviewFiscal = dgii ? <button type="button" className={noticeLinkClass} onClick={() => { onClose(); onReviewFiscal(dgii.currency); }}>{t("business.transactions.reporting.export.review")}</button> : null;
  const pendingRate = dgii?.pending_rate_count ? t("business.transactions.reporting.export.pending_rate_purchases", { count: dgii.pending_rate_count, currencies: joinCurrencyList(dgii.pending_rate_currencies, t("business.month_close.list_and")) }) : null;
  // The 606 notices, then the Bandeja's count for the period in either mode, inside the chosen option.
  const formNotices = dgii && mode === "dgii";
  const noticeItems = preview ? [
    formNotices && dgii.rnc_warning_count > 0 ? <li key="rnc" data-testid="records-export-rnc-notice" className={noticeClass}>
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p>{t("business.transactions.reporting.export.rnc_notice_title", { count: dgii.rnc_supplier_count })}</p>
        <p>{t("business.transactions.reporting.export.rnc_notice_body")}</p>
        <ul id={suppliersId} data-testid="records-export-rnc-suppliers" hidden={!suppliersExpanded} tabIndex={0} aria-label={t("business.transactions.reporting.export.rnc_view_suppliers")} className="mt-2 max-h-[132px] space-y-2 overflow-y-auto rounded-mark border border-black/15 p-2 dark:border-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)]">{supplierLines}</ul>
      </div>
      <NoticeAction><button type="button" data-testid="records-export-rnc-toggle" className={noticeLinkClass} aria-expanded={suppliersExpanded} aria-controls={suppliersId} onClick={() => setSuppliersExpanded((expanded) => !expanded)}>{t(suppliersExpanded ? "business.transactions.reporting.export.rnc_hide_suppliers" : "business.transactions.reporting.export.rnc_view_suppliers")}</button></NoticeAction>
    </li> : null,
    formNotices && pendingFiscalSentence ? <li key="fiscal" className={noticeClass}>{noticeMark}<p className="min-w-0 flex-1">{pendingFiscalSentence}</p><NoticeAction>{reviewFiscal}</NoticeAction></li> : null,
    formNotices && pendingRate ? <li key="rate" className={noticeClass}>{noticeMark}<p className="min-w-0 flex-1">{pendingRate}</p></li> : null,
    preview.bandeja_count > 0 ? <li key="bandeja" data-testid="records-export-bandeja-notice" className={noticeClass}>
      {noticeMark}
      <p className="min-w-0 flex-1">{t("business.transactions.reporting.export.bandeja_notice", { count: preview.bandeja_count })}</p>
      {onOpenBandeja ? <NoticeAction><button type="button" className={noticeLinkClass} onClick={() => { onClose(); onOpenBandeja(); }}>{t("business.transactions.reporting.export.bandeja_open")}</button></NoticeAction> : null}
    </li> : null,
  ].filter(Boolean) : [];
  const notices = noticeItems.length ? <ul data-testid="records-export-notices" className="flex flex-col gap-[10px] pb-3 pl-10 pr-3 text-[14px] text-[#56635e] dark:text-white/70">{noticeItems}</ul> : null;

  const footer = editing ? (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <button type="button" className={quietButtonClass} onClick={() => setChosen(null)}>{t("business.transactions.reporting.export.columns_reset")}</button>
      <button type="button" className={primaryButtonClass} onClick={() => setEditing(false)}>{t("business.transactions.reporting.export.columns_done")}</button>
    </div>
  ) : (
    <div className="space-y-2">
      {problem ? <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">
        {exportFailureText(t, problem, failed?.toPlace ?? false)}
        {problem.kind !== "access" ? <> <button type="button" className={quietButtonClass} onClick={() => { if (failed) void job.start(failed.run); else setAttempt((value) => value + 1); }}>{t("common.retry")}</button></> : null}
        {problem.requestId ? <ReferenceCode reference={problem.requestId} /> : null}
      </p> : null}
      {count === 0 ? <p role="status" className="text-[13px] text-[#56635e] dark:text-white/70">{t("business.transactions.reporting.export.empty")}</p> : null}
      <button type="button" data-testid="records-export-download" disabled={!count || state.kind === "preparing"} onClick={download} className={`${primaryButtonClass} w-full`}>
        {count === null ? t("business.export.action") : t("business.transactions.reporting.export.action", { count })}
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
          {fileColumns.map(({ key, label_key, required }) => <li key={key}><label className={styles.choice}>
            <input type="checkbox" checked={columns.includes(key)} disabled={required} onChange={() => toggle(key)} />
            <span>{t(label_key, { currency: "" }).trim()}</span>
          </label></li>)}
        </ul>
      </> : <>
        <p data-testid="records-export-summary" className="mb-4 text-[14px] text-[#56635e] dark:text-white/70">{summary.filter(Boolean).join(" · ")}</p>
        <div role="radiogroup" aria-label={t("business.transactions.reporting.export.what")} className="space-y-2">
          {(dgii ? ["table", "dgii"] as const : ["table"] as const).map((key) => <div key={key} data-testid={`records-export-mode-${key}`} className="rounded-item border border-black/15 dark:border-white/20">
            <label className="flex min-h-14 cursor-pointer items-center gap-3 px-3 py-2">
              <input type="radio" name="records-export-mode" checked={mode === key} onChange={() => setMode(key)} />
              <span className="min-w-0 text-[14px]">
                <span className="block font-medium">{key === "table" ? t("business.transactions.reporting.export.table_title") : t("business.transactions.reporting.export.dgii_title", { form: dgii?.form })}</span>
                <span className="block text-black/60 dark:text-white/60">{t(key === "table" ? "business.transactions.reporting.export.table_body" : "business.transactions.reporting.export.dgii_body")}</span>
              </span>
            </label>
            {key === mode ? notices : null}
          </div>)}
        </div>
        {preview && mode === "table" ? <>
          <div className="mt-3 flex min-h-11 items-center justify-between gap-3">
            <span className="text-[14px]">{t(custom ? "business.transactions.reporting.export.columns_custom" : "business.transactions.reporting.export.columns_table", { count: columns.filter((key) => preview.table.current.columns.some((column) => column.key === key)).length })}</span>
            <button type="button" data-testid="records-export-edit-columns" className={quietButtonClass} onClick={() => setEditing(true)}>{t("business.transactions.reporting.export.columns_edit")}</button>
          </div>
          <div className="mt-3"><SegmentedControl fill testId="records-export-currencies" label={t("business.transactions.reporting.export.currencies")} disabled={preview.table.all === null} value={everyCurrency ? "all" : "current"} onChange={setCurrencies} segments={[{ key: "all" as const, label: t("business.transactions.reporting.export.currencies_all") }, { key: "current" as const, label: t("business.transactions.reporting.export.currencies_current", { currency: current }) }]} /></div>
        </> : null}
        {preview && mode === "dgii" ? <div className="mt-4 space-y-2 text-[14px]" data-testid="records-export-dgii">
          <p>{t("business.transactions.reporting.export.dgii_note")}</p>
        </div> : null}
        {preview ? <div className="mt-3"><SegmentedControl fill testId="records-export-format" label={t("business.transactions.reporting.export.format")} value={format} onChange={setFormat} segments={[{ key: "xlsx" as const, label: t("business.transactions.reporting.export.format_xlsx") }, { key: "csv" as const, label: t("business.transactions.reporting.export.format_csv") }]} /></div> : null}
        {/* Without Save As on a desktop, one tip on letting the browser ask where to save. */}
        {preview && !isBelowDesktop && !canSaveAs() ? <div className="mt-4 empty:hidden"><GuideCard cardId="exportar-guardar" title={t(`${SAVE_TIP}title`)} points={[
          { label: t(`${SAVE_TIP}settings.label`), body: t(`${SAVE_TIP}settings.body`) },
          { label: t(`${SAVE_TIP}downloads.label`), body: t(`${SAVE_TIP}downloads.body`) },
          { label: t(`${SAVE_TIP}ask.label`), body: t(`${SAVE_TIP}ask.body`) },
        ]} /></div> : null}
      </>}
    </div>
  );

  // A centered dialog on desktop, the shared bottom sheet on a phone.
  if (isBelowDesktop) return <BottomSheet isOpen onClose={onClose} title={title} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" footer={footer}>{body}</BottomSheet>;
  return <CenteredDialog title={title} closeLabel={t("common.close")} onClose={onClose} footer={footer} testId="records-export-dialog">{body}</CenteredDialog>;
}
