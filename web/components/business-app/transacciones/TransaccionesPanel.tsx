"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { Check, SlidersHorizontal } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { currencySymbol } from "@/lib/money-entry";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { PullToRefresh } from "@/components/ui/PullToRefresh";
import { useBusiness } from "../BusinessWorkspace";
import BusinessAddMenu from "../BusinessAddMenu";
import { RecordsExportButton } from "./RecordsExportButton";
import { MonthCurrencyMenu } from "../MonthCurrencyMenu";
import BusinessPeriodControl, { usePeriodLabel } from "../BusinessPeriodControl";
import OutsidePeriodNote from "../OutsidePeriodNote";
import { formatShortDay } from "../business-format";
import { cardClass, primaryButtonClass, quietButtonClass, secondaryButtonClass } from "../business-ui";
import { EmptyState } from "../foundation/EmptyState";
import { DENSITIES, DENSITY_ROW_PX, setTableDensity, useTableDensity, type Density, type DensityState } from "./table-density";
import { headerCurrency, inHeaderOrder, perCurrency, SEGMENTS, suggestionRun, tableCounts, type CurrencyTotals, type IgualarView, type Money, type OtherCurrency, type RecordsTotals } from "./transacciones-model";
import { useIgualarEnabled } from "./transacciones-gate";
import { KeyHint, MoneyList, Unknown } from "./transacciones-parts";
import { recordRowKey, RecordsList, RecordsTable } from "./TransaccionesRecords";
import { EMPTY_RECORDS_FILTER, RecordsToolbar, type RecordsFilter } from "./RecordsToolbar";
import RecordsSettingsPreview from "./RecordsSettingsPreview";
import { defaultRecordsPreferences } from "./records-view-preferences";
import RecordsPagePreview from "./RecordsPagePreview";
import RecordsLoadingPreview from "./RecordsLoadingPreview";
import { emptyPreviewFilters, matchesPreviewAmount, matchesPreviewAttachment } from "./records-filter-preview-model";
import RecordsResultsSummary from "./RecordsResultsSummary";
import { useRecordPreviewSearch } from "./RecordsAnnotationsPreview";
import { matchesPreviewPeriod, matchesPreviewWorkflow, overviewPreviewCounts } from "./records-results-preview";
import RecordsOverviewPreview from "./RecordsOverviewPreview";
import { TransaccionesList } from "./TransaccionesList";
import { TransaccionesTable } from "./TransaccionesTable";
import { TransaccionesTray } from "./TransaccionesTray";
import { useTransaccionesWords } from "./transacciones-words";
import BusinessReportsPanel from "./BusinessReportsPanel";
import { useTransacciones } from "./useTransacciones";

/**
 * Transacciones: does every peso that moved have its proof? With igualar on
 * (`businessBankMatchingEnabled`), one ledger of movements with a proof slot,
 * a suggestion run in the tray, and the server's totals above. With it off,
 * or while the server has the bank routes off, the period's saved gastos and
 * ventas in the same columns, each opening its record.
 */
export default function TransaccionesPanel() {
  const { source } = useBusiness();
  const igualar = useIgualarEnabled();
  return source.mode === "live" && !igualar ? <BusinessReportsPanel /> : <LegacyTransaccionesPanel />;
}

function LegacyTransaccionesPanel() {
  const { t, locale } = useTransaccionesWords();
  const { period, setPeriod, panel, records, actions, chosen, openExport } = useBusiness();
  const igualarOn = useIgualarEnabled();
  const periodLabel = usePeriodLabel();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const densityState = useTableDensity();
  const density = densityState.density;
  const [viewPreferences, setViewPreferences] = useState(defaultRecordsPreferences);
  const controller = useTransacciones();
  const { list, movements, tray, segment, view: bank } = controller;
  const view = list.kind === "ready" ? list.view : null;
  // Until the first read lands, the gate says which screen is coming.
  const igualar = view ? view.mode === "igualar" : igualarOn;
  // Counts name the rows the table covers; the period's own counts, across currencies, name the period.
  const counts = bank ? tableCounts(bank) : null;
  const runCount = counts?.sugerencias ?? null;
  const showRun = igualar && (list.kind === "loading" || (runCount ?? (bank ? suggestionRun(bank).length : 0)) > 0);

  const rowNodes = useRef(new Map<string, HTMLElement>());
  const trayId = tray?.movementId ?? null;
  // Focus returns to the open row on close; the row's node is read when the tray needs it, not during render.
  const trayRow = useMemo(() => ({ get current() { return trayId ? rowNodes.current.get(trayId) ?? null : null; } }), [trayId]) as RefObject<HTMLElement | null>;
  const rowRef = (id: string, node: HTMLElement | null) => {
    if (node) rowNodes.current.set(id, node);
    else rowNodes.current.delete(id);
  };
  const trayMovement = tray ? controller.byId.get(tray.movementId) ?? (controller.failure?.movement.id === tray.movementId ? controller.failure.movement : undefined) : undefined;
  const stepSegment = (step: 1 | -1) => controller.choose(SEGMENTS[(SEGMENTS.indexOf(segment) + step + SEGMENTS.length) % SEGMENTS.length]);

  const monthly = period.key === "this_month" || period.key === "last_month";
  const when = monthly ? capitalize(new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(new Date(`${period.from}T12:00:00`))) : periodLabel(period);
  const subtitle = [when, bank?.coverageThrough ? t("business.transactions.coverage", { day: formatShortDay(bank.coverageThrough, locale) }) : null].filter(Boolean).join(". ");
  const porIgualar = counts?.porIgualar ?? null;
  const header = bank ? bank.currency ?? headerCurrency(movements, bank.accountCurrency) : null;
  const saved = view?.mode === "records" ? view.records : null;
  const [filter, setFilter] = useState<RecordsFilter>(EMPTY_RECORDS_FILTER);
  const [previewFilters, setPreviewFilters] = useState(emptyPreviewFilters);
  const [previewPeriod, setPreviewPeriod] = useState(period);
  const [previewRevision, setPreviewRevision] = useState(0);
  const localPaging = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const pageResetKey = JSON.stringify([filter, period, previewPeriod, previewRevision, previewFilters.amount, previewFilters.review, previewFilters.attachment]);
  const query = filter.query.trim().toLocaleLowerCase(locale);
  const matchesPreviewSearch = useRecordPreviewSearch();
  const periodRecords = localPaging ? saved?.filter((row) => matchesPreviewPeriod(row, previewPeriod)) ?? null : saved;
  const visibleRecords = periodRecords?.filter((row) => (filter.kind === "all" || row.kind === filter.kind) && (localPaging ? matchesPreviewSearch(row, query) : !query || (row.counterparty ?? "").toLocaleLowerCase(locale).includes(query)) && (!localPaging || matchesPreviewAttachment(row.hasProof, previewFilters.attachment) && matchesPreviewAmount(row.money, previewFilters.amount) && matchesPreviewWorkflow(row, chosen?.space_id ?? null, previewFilters.review))) ?? null;
  // Back from a record's own page, its row takes focus once the list is in, or the screen does when the period leaves it out.
  // Once per arrival: a background reload never takes focus back from wherever the person moved it.
  const cameFrom = panel.kind === "transactions" ? panel.expenseId : undefined;
  const screen = useRef<HTMLElement>(null);
  const focusedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!cameFrom) focusedFor.current = null;
    if (!cameFrom || !saved || focusedFor.current === cameFrom) return;
    focusedFor.current = cameFrom;
    const restored = saved.find((row) => row.opens?.kind === "expense" && row.opens.expenseId === cameFrom);
    (restored ? rowNodes.current.get(recordRowKey(restored)) : screen.current)?.focus();
  }, [cameFrom, saved]);
  const add = actions.create.find((action) => action.id === "upload_receipt");

  const recordsEmptyContent = saved?.length === 0 ? <div className={cardClass} data-testid="transacciones-records-empty">
    {period.key === "this_month" || period.key === "all"
      ? <EmptyState kind="first_run" mark="receipt" compact title={t("business.transactions.records.empty_title")} body={t("business.transactions.records.empty_body")} action={add ? { label: add.label, run: add.run } : undefined} />
      : <EmptyState kind="filtered" compact title={t("business.transactions.records.filtered_title")} body={t("business.transactions.records.filtered_body")} action={{ label: t("business.empty.see_all_periods"), run: () => setPeriod("all") }} />}
  </div> : localPaging && periodRecords?.length === 0 ? <div className={cardClass}><EmptyState kind="filtered" compact title={t("business.transactions.layout.no_period_records")} action={{ label: t("business.transactions.layout.reset_period"), run: () => setPreviewPeriod(period) }} /></div> : <div className={cardClass}><EmptyState kind="filtered" compact title={t("business.transactions.layout.no_results")} action={{ label: t("business.transactions.layout.clear"), run: () => { setFilter(EMPTY_RECORDS_FILTER); if (localPaging) setPreviewFilters(emptyPreviewFilters()); } }} /></div>;

  const run = showRun ? (
    <button type="button" data-testid="transacciones-run" data-primary="true" disabled={list.kind !== "ready"} onClick={controller.startRun} className={`${primaryButtonClass} ${phone ? "shrink-0" : ""}`}>
      {phone ? t("business.transactions.run_short") : t("business.transactions.run")}
      {runCount !== null ? <span className="tabular-nums opacity-85">{runCount}</span> : null}
      {phone ? null : <KeyHint>I</KeyHint>}
    </button>
  ) : null;

  return (
    <PullToRefresh onRefresh={controller.refresh}>
      <section ref={screen} tabIndex={-1} data-testid="transacciones" className="pb-6 outline-none">
        {phone || igualar || panel.kind !== "transactions" ? <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            {phone || panel.kind !== "transactions" ? <h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{t("business.transactions.title")}</h2> : null}
            {igualar ? <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/65">{subtitle}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-3">{phone ? null : run}{phone ? <BusinessAddMenu placement="header" /> : null}</div>
        </div> : null}
        {igualar ? <div className="mb-4 flex flex-wrap items-center gap-2">
          <SegmentedControl
            testId="transacciones-segments"
            label={t("business.transactions.segments.label")}
            fill={phone}
            value={segment}
            onChange={controller.choose}
            segments={SEGMENTS.map((key) => ({ key, label: t(`business.transactions.segments.${key}`), count: key === "por_igualar" ? porIgualar : null }))}
          />
          <BusinessPeriodControl period={period} setPeriod={setPeriod} />
          {phone ? <div className="ml-auto">{run}</div> : <div className="ml-auto"><DensityMenu state={densityState} /></div>}
        </div> : null}
        {!igualar && process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? <RecordsOverviewPreview loading={list.kind === "loading"} counts={overviewPreviewCounts(periodRecords, chosen?.space_id ?? null)} selected={previewFilters.review} onChoose={(review) => setPreviewFilters((current) => ({ ...current, review: current.review.includes(review) ? [] : [review] }))} /> : null}
        {!igualar ? <RecordsToolbar appliedPeriod={previewPeriod} onPeriodChange={setPreviewPeriod} appliedFilters={previewFilters} onFiltersChange={setPreviewFilters} preferences={viewPreferences} onPreferencesChange={setViewPreferences} onPreviewChange={() => setPreviewRevision((value) => value + 1)} filter={filter} onChange={setFilter} period={period} setPeriod={setPeriod} options={<>{phone ? null : <RecordsExportButton onExport={openExport} />}{localPaging ? <RecordsSettingsPreview value={viewPreferences} onChange={setViewPreferences} /> : !phone ? <DensityMenu state={densityState} /> : null}</>} /> : null}
        {!igualar && records.overview ? <div className="-mt-1 mb-4"><OutsidePeriodNote count={records.overview.outside_period_count} latestOn={records.overview.outside_period_latest_on} onShowAll={() => setPeriod("all")} /></div> : null}
        {igualar && controller.currencyMenu ? (
          <div data-testid="transacciones-currency" className="mb-3">
            <MonthCurrencyMenu currencies={controller.currencyMenu.choices} value={controller.currencyMenu.value} businessCurrency={controller.businessCurrency} onChoose={controller.chooseCurrency} note={<OtherCurrencies others={bank?.otherCurrencies ?? []} onChoose={controller.chooseCurrency} />} />
          </div>
        ) : null}
        {!igualar && !localPaging ? <p className="mb-2 text-[13px] text-[#56635e] dark:text-white/65">{t("business.transactions.layout.period_summary", { period: subtitle })}</p> : null}
        {igualar
          ? <Summary view={bank} header={header} locale={locale} loading={list.kind === "loading"} />
          : localPaging ? (saved ? <RecordsResultsSummary kind={filter.kind} records={visibleRecords ?? saved} businessId={chosen?.space_id ?? null} /> : null) : <RecordsSummary totals={view?.mode === "records" ? view.totals : null} header={headerCurrency(saved ?? [])} locale={locale} loading={list.kind === "loading"} />}
        {list.kind === "failed" ? (
          <div className={cardClass}>
            <EmptyState kind="error" compact testId="transacciones-error" title={igualar ? t("business.transactions.error.load_title") : t("business.transactions.records.error_title")} body={igualar ? t("business.transactions.error.load_body") : t("business.empty.error_body")} action={{ label: t("common.retry", "Reintentar"), run: controller.retryLoad }} />
          </div>
        ) : list.kind === "loading" ? (
          igualar ? <LoadingRows density={phone ? "amplio" : density} /> : <RecordsLoadingPreview density={localPaging ? viewPreferences.density : density} preferences={localPaging ? viewPreferences : undefined} />
        ) : saved ? (
          localPaging ? <RecordsPagePreview onSortChange={(sort) => setViewPreferences((current) => ({ ...current, sort }))} preferences={viewPreferences} records={visibleRecords ?? saved} density={viewPreferences.density} rowRef={rowRef} resetKey={pageResetKey} emptyContent={recordsEmptyContent} />
            : saved.length === 0 || visibleRecords?.length === 0 ? recordsEmptyContent
              : phone ? <RecordsList records={visibleRecords ?? saved} rowRef={rowRef} /> : <RecordsTable records={visibleRecords ?? saved} density={density} rowRef={rowRef} />
        ) : !bank ? null : bank.counts !== null && bank.counts.movimientos + bank.counts.sinMovimiento === 0 ? (
          <div className={cardClass}>
            <EmptyState kind="first_run" mark="receipt" compact testId="transacciones-empty" title={t("business.transactions.empty.first_run_title")} body={t("business.transactions.empty.first_run_body")} />
          </div>
        ) : movements.length === 0 ? (
          <div className={cardClass}>
            {bank.segment === "por_igualar"
              ? <EmptyState kind="done" compact testId="transacciones-done" title={t("business.transactions.empty.done_title")} body={counts ? t("business.transactions.empty.done_body", { count: counts.movimientos }) : undefined} />
              : <EmptyState kind="filtered" compact title={t("business.transactions.empty.segment")} />}
          </div>
        ) : (
          <>
            {phone
              ? <TransaccionesList controller={controller} view={bank} rowRef={rowRef} />
              : <TransaccionesTable controller={controller} view={bank} density={density} onSegmentStep={stepSegment} onRunKey={controller.startRun} rowRef={rowRef} />}
            <LoadMore controller={controller} view={bank} />
          </>
        )}
        {saved && !localPaging ? <p data-testid="records-count" aria-live="polite" className="mt-4 text-[13px] text-[#56635e] dark:text-white/65">{t("business.transactions.layout.count", { count: visibleRecords?.length ?? 0 })}</p> : null}
        {trayMovement ? <TransaccionesTray key={tray?.run ? "run" : trayMovement.id} controller={controller} movement={trayMovement} phone={phone} returnFocusRef={trayRow} /> : null}
      </section>
    </PullToRefresh>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toLocaleUpperCase() + text.slice(1);
}

/**
 * The server's totals: exact, one per currency, the header's first. Por
 * igualar counts the rows the table covers; Igualadas counts the whole period,
 * every currency, as the server sends it.
 */
function Summary({ view, header, locale, loading }: { view: IgualarView | null; header: string | null; locale: string; loading: boolean }) {
  const { t } = useTransaccionesWords();
  const totals: readonly CurrencyTotals[] = view?.totals ?? [];
  const money = (key: "entradas" | "salidas" | "porIgualar"): Money[] | null => (view ? inHeaderOrder(perCurrency(totals, key), header) : null);
  const zeroIn = view ? view.currency ?? view.accountCurrency : null;
  const covered = view ? tableCounts(view) : null;
  const period = view?.counts ?? null;
  const cells: { key: string; value: React.ReactNode }[] = [
    { key: "entradas", value: <MoneyList totals={money("entradas")} header={header} locale={locale} zeroIn={zeroIn} /> },
    { key: "salidas", value: <MoneyList totals={money("salidas")} header={header} locale={locale} zeroIn={zeroIn} /> },
    {
      key: "por_igualar",
      value: view ? (
        <span className="flex flex-wrap items-baseline gap-x-2"><span className="tabular-nums">{covered ? covered.porIgualar : <Unknown />}</span><span className="text-[14px] font-normal text-[#56635e] dark:text-white/65"><MoneyList totals={money("porIgualar")} header={header} locale={locale} zeroIn={zeroIn} /></span></span>
      ) : <Unknown />,
    },
    {
      key: "igualadas",
      value: period ? (
        <span className="flex items-baseline gap-x-2"><span className="tabular-nums">{period.igualadas + period.noLleva}</span><span className="text-[14px] font-normal text-[#56635e] dark:text-white/65">{t("business.transactions.totals.of", { count: period.movimientos })}</span></span>
      ) : <Unknown />,
    },
  ];
  return (
    <dl data-testid="transacciones-summary" className="mb-4 grid grid-cols-2 overflow-hidden rounded-surface border border-[#DCE0DA] bg-white tablet:grid-cols-4 dark:border-white/10 dark:bg-[#1f2225]">
      {cells.map((cell, index) => (
        <div key={cell.key} data-total={cell.key} className={`min-w-0 px-4 py-3 ${index % 2 ? "border-l" : ""} ${index > 1 ? "border-t tablet:border-t-0" : ""} ${index === 2 ? "tablet:border-l" : ""} border-[#DCE0DA] dark:border-white/10`}>
          <dt className="text-[13px] text-[#56635e] dark:text-white/65">{t(`business.transactions.totals.${cell.key}`)}</dt>
          <dd className="mt-1 text-[17px] font-medium text-[#172b26] dark:text-white">
            {loading ? <span aria-hidden="true" className="block h-5 w-28 animate-pulse rounded-mark bg-black/[0.06] motion-reduce:animate-none dark:bg-white/[0.08]" /> : cell.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The saved records' totals: Salidas exact, one per currency. No read serves a total of the period's ventas, so Entradas is unknown. */
function RecordsSummary({ totals, header, locale, loading }: { totals: RecordsTotals | null; header: string | null; locale: string; loading: boolean }) {
  const { t } = useTransaccionesWords();
  const cells = { entradas: <Unknown />, salidas: <MoneyList totals={totals ? inHeaderOrder(totals.salidas, header) : null} header={header} locale={locale} /> };
  return (
    <dl data-testid="transacciones-summary" data-mode="records" className="mb-4 grid grid-cols-2 gap-4 border-y border-[#DCE0DA] py-3 tablet:flex tablet:gap-12 dark:border-white/10">
      {(["entradas", "salidas"] as const).map((key) => (
        <div key={key} data-total={key} className="min-w-0 tablet:min-w-40">
          <dt className="text-[13px] text-[#56635e] dark:text-white/65">{t(`business.transactions.totals.${key}`)}</dt>
          <dd className="mt-1 text-[17px] font-medium text-[#172b26] dark:text-white">
            {loading ? <span aria-hidden="true" className="block h-5 w-28 animate-pulse rounded-mark bg-black/[0.06] motion-reduce:animate-none dark:bg-white/[0.08]" /> : cells[key]}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** What the chosen currency leaves out of the segment, one line per other currency with a way to switch. Nothing when nothing is left out. */
function OtherCurrencies({ others, onChoose }: { others: readonly OtherCurrency[]; onChoose: (currency: string) => void }) {
  const { t } = useTransaccionesWords();
  if (others.length === 0) return null;
  return (
    <span data-testid="transacciones-other-currencies" className="flex flex-wrap items-center gap-x-4">
      {others.map((other) => (
        <span key={other.currency} data-currency={other.currency} className="inline-flex flex-wrap items-center gap-x-2 text-[13px] text-[#56635e] dark:text-white/70">
          {t("business.transactions.other_currencies", { count: other.count, currency: currencySymbol(other.currency) })}
          <button type="button" onClick={() => onChoose(other.currency)} className={quietButtonClass}>{t("business.transactions.other_currencies_show", { currency: currencySymbol(other.currency) })}</button>
        </span>
      ))}
    </span>
  );
}

/** Cargar más fetches the next page; rows already shown stay. A failure says so here with its way out. Hidden when there is no next page. */
function LoadMore({ controller, view }: { controller: ReturnType<typeof useTransacciones>; view: IgualarView }) {
  const { t } = useTransaccionesWords();
  const { more } = controller;
  if (!view.nextCursor && more.kind !== "failed") return null;
  return (
    <div data-testid="transacciones-more" className="mt-3 flex flex-wrap items-center justify-center gap-3">
      {more.kind === "failed" ? (
        <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{more.changed ? t("business.transactions.error.list_changed") : t("business.transactions.error.more")}</p>
      ) : null}
      {more.kind === "failed" && more.changed ? (
        <button type="button" onClick={controller.retryLoad} className={secondaryButtonClass}>{t("business.transactions.error.reload")}</button>
      ) : (
        <button type="button" onClick={() => void controller.loadMore()} disabled={more.kind === "loading"} aria-busy={more.kind === "loading"} className={secondaryButtonClass}>
          {more.kind === "failed" ? t("common.retry", "Reintentar") : t("business.transactions.more")}
        </button>
      )}
    </div>
  );
}

/** Skeleton rows at the chosen row height, so nothing jumps when the rows arrive. Only while loading. */
function LoadingRows({ density }: { density: Density }) {
  const { t } = useTransaccionesWords();
  return (
    <div role="status" aria-label={t("common.loading", "Cargando")} data-testid="transacciones-loading" className="overflow-hidden rounded-surface border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
      <div aria-hidden="true" className="animate-pulse motion-reduce:animate-none">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} style={{ height: DENSITY_ROW_PX[density] }} className="flex items-center gap-4 border-b border-[#DCE0DA] px-3 last:border-b-0 dark:border-white/10">
            <span className="h-4 w-4 rounded-full bg-black/[0.06] dark:bg-white/[0.08]" />
            <span className="h-3 w-48 rounded-mark bg-black/[0.06] dark:bg-white/[0.08]" />
            <span className="ml-auto h-3 w-20 rounded-mark bg-black/[0.06] dark:bg-white/[0.08]" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The quiet view options at the right of the filters: the table's row height, kept on the person's profile. A refused save stays open and says so. */
function DensityMenu({ state }: { state: DensityState }) {
  const { density } = state;
  const { t } = useTransaccionesWords();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  return (
    <div ref={root} className="relative" onKeyDown={(event) => { if (event.key === "Escape" && open) { event.preventDefault(); setOpen(false); } }}>
      <button type="button" data-testid="transacciones-view-options" aria-label={t("business.transactions.density.options")} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)} className="flex h-11 w-11 items-center justify-center rounded-full border border-[#DCE0DA] bg-white text-[#56635e] hover:bg-[#F7F5EE] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:border-white/15 dark:bg-[#1f2225] dark:text-white/70">
        <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
      </button>
      {open ? (
        <div role="menu" aria-label={t("business.transactions.density.label")} aria-busy={state.saving} className="absolute right-0 top-full z-40 mt-2 w-56 origin-top-right rounded-surface border border-black/10 bg-white p-1.5 dark:border-white/10 dark:bg-[#1f2225]">
          <p className="px-2.5 pb-1 pt-1.5 text-[12px] font-medium text-[#56635e] dark:text-white/65">{t("business.transactions.density.label")}</p>
          {DENSITIES.map((option) => (
            <button key={option} type="button" role="menuitemradio" aria-checked={option === density} data-density-option={option} onClick={() => { void setTableDensity(option).then((kept) => { if (kept) setOpen(false); }); }} className="flex min-h-10 w-full items-center justify-between rounded-item px-2.5 text-left text-[14px] text-[#172b26] hover:bg-black/5 focus-visible:bg-black/5 focus-visible:outline-none aria-checked:font-medium dark:text-white dark:hover:bg-white/5">
              {t(`business.transactions.density.${option}`)}
              {option === density ? <Check className="h-4 w-4 text-[var(--cuadrao-green)]" aria-hidden="true" /> : null}
            </button>
          ))}
          {state.failed
            ? <p role="alert" data-testid="density-failed" className="px-2.5 pb-1.5 pt-1 text-[12px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.transactions.density.failed")}</p>
            : <p className="px-2.5 pb-1.5 pt-1 text-[12px] text-[#56635e] dark:text-white/65">{t("business.transactions.density.note")}</p>}
        </div>
      ) : null}
    </div>
  );
}
