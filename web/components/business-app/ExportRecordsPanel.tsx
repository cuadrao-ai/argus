"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { CalendarDays, Check, Download, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { currentMonthKey, loadCurrentMonth, shiftMonthKey, windowForMonth, type DgiiForms, type DgiiFormStatus, type MonthCloseSnapshot } from "@/lib/business-month-close";
import { businessExportPeriodValid, fetchBusinessExport } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { useBusinessNaming } from "./BusinessNamingProvider";
import BusinessFiscalProfile from "./BusinessFiscalProfile";
import type { MonthCloseSource } from "./BusinessMonthClosePanel";
import { formatBusinessName, UNKNOWN_VALUE } from "./business-format";
import { RangeCalendar } from "./foundation/RangeCalendar";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { showToast } from "./foundation/toasts";
import { primaryButtonClass, quietButtonClass } from "./business-ui";
import { resolveLanguage } from "@/lib/language-features";

export function finishPeriodExportRequest(request: { current: AbortController | null }, controller: AbortController, setBusy: (busy: boolean) => void) {
  if (request.current !== controller) return;
  request.current = null;
  setBusy(false);
}

export function startPeriodExportRequest(request: { current: AbortController | null }, setBusy: (busy: boolean) => void): AbortController | null {
  if (request.current) return null;
  const controller = new AbortController();
  request.current = controller;
  setBusy(true);
  controller.signal.addEventListener("abort", () => finishPeriodExportRequest(request, controller, setBusy), { once: true });
  return controller;
}

export function saveBlobDownload(blob: Blob, filename: string, revokeAfterMs = 30_000) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  // Safari and Firefox read the object URL after click returns; revoke later.
  try { link.click(); } finally { link.remove(); globalThis.setTimeout(() => URL.revokeObjectURL(url), revokeAfterMs); }
}

type Preset = "this_month" | "last_month" | "year";
export type ExportChoice = { kind: Preset } | { kind: "custom"; from: string; to: string };
type Range = { from: string; to: string };

/** The dates a choice exports, both inclusive, around the server's current month. A year runs January to December. */
export function exportRange(choice: ExportChoice, current: string): Range {
  if (choice.kind === "custom") return { from: choice.from, to: choice.to };
  if (choice.kind === "this_month") return wholeMonth(current);
  if (choice.kind === "last_month") return wholeMonth(shiftMonthKey(current, -1));
  return { from: `${current.slice(0, 4)}-01-01`, to: `${current.slice(0, 4)}-12-31` };
}

/** The panel opens on `month` when one is given: a preset when one names it, else that month as typed dates. Otherwise this month. */
export function openingChoice(month: string | undefined, current: string): ExportChoice {
  if (month === undefined || month === current) return { kind: "this_month" };
  if (month === shiftMonthKey(current, -1)) return { kind: "last_month" };
  return { kind: "custom", ...wholeMonth(month) };
}

function wholeMonth(month: string): Range {
  const window = windowForMonth(month);
  return { from: window.from, to: window.to ?? window.from };
}

/** `YYYY-MM` when the range is exactly one calendar month, the only period a 606 or 607 covers. */
export function wholeMonthOf(range: Range): string | null {
  const month = range.from.slice(0, 7);
  if (!/^\d{4}-\d{2}-01$/.test(range.from)) return null;
  return windowForMonth(month).to === range.to ? month : null;
}

/** What the 606 and 607 line says: each form's own status word from the export packet, which decides what goes in the ZIP. */
export type FiscalLine = { kind: "checking" } | { kind: "forms"; forms: DgiiForms } | { kind: "whole_month_only" } | { kind: "unknown" };

const formsLine = (snapshot: MonthCloseSnapshot): FiscalLine => (snapshot.dgii_forms ? { kind: "forms", forms: snapshot.dgii_forms } : { kind: "unknown" });

/** `current` is the month already read to learn the server's day; its forms need no second read. */
function useFiscalLine(range: Range | null, monthClose: MonthCloseSource, current: MonthCloseSnapshot | null): FiscalLine {
  const month = range ? wholeMonthOf(range) : null;
  const [seen, setSeen] = useState<{ key: string; line: FiscalLine } | null>(null);
  const key = `${monthClose.scopeKey}:${month}`;
  const known = current && current.month === month ? current : null;
  useEffect(() => {
    if (!month || known || monthClose.scopeKey === null) return undefined;
    let live = true;
    monthClose.client.load(month, monthClose.scopeKey).then(
      (snapshot) => { if (live) setSeen({ key, line: formsLine(snapshot) }); },
      () => { if (live) setSeen({ key, line: { kind: "unknown" } }); },
    );
    return () => { live = false; };
  }, [key, known, month, monthClose]);
  if (!range) return { kind: "checking" };
  if (!month) return { kind: "whole_month_only" };
  if (known) return formsLine(known);
  return seen?.key === key ? seen.line : { kind: "checking" };
}

/** The current month as the server's day places it. An older server or a failed read leaves the month first asked for. */
function useCurrentMonth(monthClose: MonthCloseSource): { month: string; snapshot: MonthCloseSnapshot | null } | null {
  const [current, setCurrent] = useState<{ key: string; month: string; snapshot: MonthCloseSnapshot | null } | null>(null);
  const key = String(monthClose.scopeKey);
  useEffect(() => {
    if (monthClose.scopeKey === null) return undefined;
    let live = true;
    const seed = currentMonthKey();
    loadCurrentMonth(monthClose.client, monthClose.scopeKey, seed).then(
      (snapshot) => { if (live) setCurrent({ key, month: snapshot.today?.slice(0, 7) ?? snapshot.month ?? seed, snapshot }); },
      () => { if (live) setCurrent({ key, month: seed, snapshot: null }); },
    );
    return () => { live = false; };
  }, [key, monthClose]);
  return current?.key === key ? current : null;
}

function monthName(month: string, locale: string): string {
  const name = new Intl.DateTimeFormat(locale, { month: "long" }).format(new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1));
  return `${name.charAt(0).toLocaleUpperCase(locale)}${name.slice(1)}`;
}

/** "1 al 31 oct 2026": the start drops what it shares with the end. */
function rangeEnds(range: Range, locale: string): { from: string; to: string } {
  const day = (iso: string, parts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(locale, { day: "numeric", ...parts }).format(new Date(`${iso}T12:00:00`));
  const sameYear = range.from.slice(0, 4) === range.to.slice(0, 4);
  const sameMonth = sameYear && range.from.slice(0, 7) === range.to.slice(0, 7);
  return {
    from: sameMonth ? day(range.from, {}) : day(range.from, sameYear ? { month: "short" } : { month: "short", year: "numeric" }),
    to: day(range.to, { month: "short", year: "numeric" }),
  };
}

/**
 * The Business export. Three periods cover almost every export (this month,
 * last month, this year); any other range is typed. The list says what the
 * ZIP holds, and the 606 and 607 line says when they come with it.
 */
export default function ExportRecordsPanel({ month: startMonth, monthClose, onClose }: { month?: string; monthClose: MonthCloseSource; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const { chosen, source } = useBusiness();
  const naming = useBusinessNaming();
  const current = useCurrentMonth(monthClose);
  const [picked, setChoice] = useState<ExportChoice | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  // The periods are named from the server's month, so nothing is offered until it is known.
  const choice = picked ?? (current ? openingChoice(startMonth, current.month) : null);
  const range = choice && current ? exportRange(choice, current.month) : null;
  const valid = range !== null && businessExportPeriodValid(range.from, range.to);
  const fiscal = useFiscalLine(range, monthClose, current?.snapshot ?? null);
  const available = source.mode === "live";
  const scope = chosen ? { name: chosen.name, grantId: chosen.role === "owner" ? null : chosen.grant_id } : null;
  const canExport = chosen?.permissions?.includes("export") === true;

  // A change of Business, access or period drops the download in flight: it would save what the owner no longer asked for.
  useEffect(() => () => request.current?.abort(), [chosen?.grant_id, canExport, available, range?.from, range?.to]);

  const segments = current ? [
    { key: "this_month" as const, label: monthName(current.month, locale) },
    { key: "last_month" as const, label: monthName(shiftMonthKey(current.month, -1), locale) },
    { key: "year" as const, label: current.month.slice(0, 4) },
  ] : [];
  const choose = (next: ExportChoice) => { setProblem(null); setChoice(next); };

  const download = async () => {
    if (!scope || !range || request.current || !available || !valid) return;
    const controller = startPeriodExportRequest(request, setBusy);
    if (!controller) return;
    setProblem(null);
    try {
      if (naming && !await naming.requireName()) return;
      controller.signal.throwIfAborted();
      const blob = await fetchBusinessExport(undefined, range.from, range.to, controller.signal, scope.grantId);
      controller.signal.throwIfAborted();
      saveBlobDownload(blob, `business-export-${range.from}-${range.to}.zip`);
      showToast({ kind: "success", text: t("business.export.done", "Downloaded. Find the ZIP in your downloads.") });
      onClose();
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = (error as { status?: number }).status;
      setProblem(status === 401 || status === 403 || status === 404 ? t("business.export.access_error", "This export isn't available with your current access.") : status === 413 ? t("business.export.limit_error", "This export exceeds a package limit. Choose a shorter period.") : t("business.export.error", "The export could not be downloaded. Check your access and try again."));
    } finally {
      finishPeriodExportRequest(request, controller, setBusy);
    }
  };

  const footer = canExport ? (
    <div className="space-y-2">
      {problem ? <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{problem}</p> : null}
      {!available ? <p className="text-[13px] text-[#56635e] dark:text-white/70">{t("business.export.preview", "Downloads are available in the connected Business view.")}</p> : null}
      <button type="button" data-testid="export-download" disabled={busy || !available || !valid} onClick={() => void download()} className={`${primaryButtonClass} w-full`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
        {busy ? t("business.export.preparing", "Preparing your file…") : t("business.export.action", "Export")}
      </button>
    </div>
  ) : undefined;

  return (
    <AdaptivePanel
      title={t("business.overview.export_records", "Export records")}
      summary={chosen ? formatBusinessName(chosen.name, t("business.overview.title", "My business")) : undefined}
      closeLabel={t("common.close", "Close")}
      onClose={onClose}
      width="md"
      footer={footer}
    >
      <div className="pb-6 pt-2 desktop:px-5" data-testid="export-records-panel">
        {canExport ? (
          <>
            <h3 className="mb-2 text-[13px] font-medium text-[#56635e] dark:text-white/70">{t("business.period.label", "Period")}</h3>
            {!choice || !range ? (
              <p role="status" data-testid="export-period-loading" className="flex min-h-11 items-center text-[13px] text-[#56635e] dark:text-white/70">{t("business.export.fiscal_checking", "Checking…")}</p>
            ) : <>
            <SegmentedControl
              fill
              testId="export-period"
              label={t("business.period.label", "Period")}
              segments={segments}
              value={choice.kind === "custom" ? null : choice.kind}
              onChange={(kind) => choose({ kind })}
            />
            {choice.kind === "custom" ? (
              <div className="mt-3" data-testid="export-custom-range">
                <RangeCalendar label={t("business.export.other_dates", "Other dates")} value={{ from: choice.from, to: choice.to }} maxDays={366} onChange={(next) => choose({ kind: "custom", ...next })} />
              </div>
            ) : null}
            <div className={`mt-2 min-h-11 flex-wrap items-center justify-between gap-x-3 ${choice.kind === "custom" && valid ? "hidden" : "flex"}`}>
              <p data-testid="export-range" className="text-[13px] tabular-nums text-[#56635e] dark:text-white/70">
                {valid
                  ? t("business.export.range", { ...rangeEnds(range, locale), defaultValue: "{{from}} to {{to}}" })
                  : t("business.export.range_invalid", "Choose between 1 and 366 days.")}
              </p>
              {choice.kind === "custom" ? null : (
                <button type="button" data-testid="export-other-dates" onClick={() => choose({ kind: "custom", ...range })} className={quietButtonClass}>
                  <CalendarDays className="h-4 w-4" aria-hidden="true" />
                  {t("business.export.other_dates", "Other dates")}
                </button>
              )}
            </div>
            </>}

            <h3 className="mb-1 mt-5 text-[13px] font-medium text-[#56635e] dark:text-white/70">{t("business.export.includes", "Includes")}</h3>
            <ul className="divide-y divide-[#EEF0EC] dark:divide-white/[0.06]" data-testid="export-includes">
              <IncludedRow title={t("business.export.records", "Records")} detail={t("business.export.records_detail", "Excel and CSV")} status={<Included />} />
              <IncludedRow title={t("business.export.originals", "Originals")} detail={t("business.export.originals_detail", "Photos and PDFs of each receipt")} status={<Included />} />
              <IncludedRow testId="export-fiscal" title={t("business.export.fiscal", "606 and 607")} detail={t("business.export.fiscal_detail", "For the DGII")} status={<FiscalStatus line={fiscal} />} />
            </ul>
            {available ? (
              <details className="group mt-4">
                <summary className="flex min-h-11 cursor-pointer list-none items-center rounded-item text-[14px] font-medium text-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-[#8fcbb0]">
                  {t("business.export.fiscal_profile", "Name and RNC on the 606")}
                </summary>
                <BusinessFiscalProfile />
              </details>
            ) : null}
          </>
        ) : (
          <p className="text-[14px] text-[#56635e] dark:text-white/70">{t("business.export.access_error", "This export isn't available with your current access.")}</p>
        )}
      </div>
    </AdaptivePanel>
  );
}

function IncludedRow({ title, detail, status, testId }: { title: string; detail: string; status: ReactNode; testId?: string }) {
  return (
    <li data-testid={testId} className="flex min-h-14 items-center justify-between gap-3 py-2.5">
      <span className="min-w-0">
        <span className="block text-[15px] text-[#172b26] dark:text-white">{title}</span>
        <span className="block text-[13px] text-[#56635e] dark:text-white/70">{detail}</span>
      </span>
      <span className="shrink-0 text-right text-[13px]">{status}</span>
    </li>
  );
}

function Included() {
  const { t } = useTranslation();
  return <Check className="h-5 w-5 text-[#2f5a49] dark:text-[#8fcbb0]" role="img" aria-label={t("business.export.included", "Included")} />;
}

function FiscalStatus({ line }: { line: FiscalLine }) {
  const { t } = useTranslation();
  if (line.kind === "forms") {
    return (
      <span className="flex flex-col items-end gap-0.5">
        {(["606", "607"] as const).map((form) => <FormStatus key={form} form={form} status={line.forms[form]} />)}
      </span>
    );
  }
  if (line.kind === "whole_month_only") return <span className="text-[#56635e] dark:text-white/70">{t("business.export.fiscal_month_only", "Whole month only")}</span>;
  if (line.kind === "unknown") return <span className="text-[#56635e] dark:text-white/70">{UNKNOWN_VALUE}</span>;
  return <span className="text-[#56635e] dark:text-white/70">{t("business.export.fiscal_checking", "Checking…")}</span>;
}

/** One form and the packet's word for it. Only `prepared_candidate` means the ZIP carries the form. */
function FormStatus({ form, status }: { form: "606" | "607"; status: DgiiFormStatus | null }) {
  const { t } = useTranslation();
  const words: Record<DgiiFormStatus, string> = {
    prepared_candidate: t("business.export.included", "Included"),
    needs_review: t("business.export.form_needs_review", "Needs review"),
    no_operations: t("business.export.form_no_operations", "No operations"),
    summary_only: t("business.export.form_summary_only", "Summary only"),
    no_aplica: t("business.export.form_no_aplica", "Does not apply"),
  };
  const tone = status === "prepared_candidate" ? "font-medium text-[#2f5a49] dark:text-[#8fcbb0]" : status === "needs_review" ? "font-medium text-[#735c14] dark:text-[#f6e7c1]" : "text-[#56635e] dark:text-white/70";
  return (
    <span data-testid={`export-form-${form}`} data-status={status ?? "unknown"} className={`inline-flex items-center gap-1.5 tabular-nums ${tone}`}>
      <span className="text-[#56635e] dark:text-white/70">{form}</span>
      {status === "prepared_candidate" ? <Check className="h-4 w-4" aria-hidden="true" /> : null}
      {status === null ? UNKNOWN_VALUE : words[status]}
    </span>
  );
}
