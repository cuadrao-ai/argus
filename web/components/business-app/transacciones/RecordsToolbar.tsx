"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { CalendarDays, Check, ChevronDown, Search, X } from "lucide-react";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { customPeriod, PERIOD_PRESETS, todayIso, type Period, type PeriodKey } from "../business-format";
import { usePeriodLabel } from "../BusinessPeriodControl";
import { RangeCalendar, type DayRange } from "../foundation/RangeCalendar";
import { primaryButtonClass, secondaryButtonClass } from "../business-ui";
import type { RecordKind } from "./transacciones-model";
import { useTransaccionesWords } from "./transacciones-words";
import RecordsDatePreview from "./RecordsDatePreview";
import RecordsFiltersPreview from "./RecordsFiltersPreview";
import { emptyPreviewFilters } from "./records-filter-preview-model";
import { RecordsViewsPreview, type SavedRecordsView, type RecordsViewSelection } from "./RecordsViewsPreview";

export type RecordsFilter = { query: string; kind: RecordKind | "all" };
export const EMPTY_RECORDS_FILTER: RecordsFilter = { query: "", kind: "all" };

const optionClass = "flex min-h-11 w-full items-center justify-between gap-3 rounded-item px-3 text-left text-[15px] text-[#172b26] hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white dark:hover:bg-white/5";

function ToolbarPicker({ label, value, icon, wide = false, children }: { label: string; value: string; icon?: ReactNode; wide?: boolean; children: (close: () => void) => ReactNode }) {
  const { t } = useTransaccionesWords();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const [availableHeight, setAvailableHeight] = useState(480);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = () => setOpen(false);
  useOverlayLayer({ isOpen: open && !phone, overlayId: id, containerRef: root, onEscape: close, onOutsidePointerDown: close });
  useEffect(() => {
    if (!open || phone) return;
    const trigger = button.current;
    content.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => trigger?.focus();
  }, [open, phone]);
  return (
    <div ref={root} className="relative min-w-0">
      <button ref={button} type="button" aria-label={`${label}: ${value}`} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => { setAvailableHeight(Math.max(96, window.innerHeight - (button.current?.getBoundingClientRect().bottom ?? 0) - 16)); setOpen((current) => !current); }} className={`${secondaryButtonClass} max-w-full gap-2 px-3 text-[14px]`}>
        {icon}<span className="truncate">{value}</span><ChevronDown aria-hidden="true" className={`h-4 w-4 shrink-0 transition-transform duration-150 motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
      {open && !phone ? (
        <div ref={content} id={id} role="dialog" aria-label={label} style={{ maxHeight: availableHeight, overflowY: "auto" }} className={`absolute left-0 top-full z-[70] mt-2 max-w-[calc(100vw-2rem)] rounded-surface border border-[#DCE0DA] bg-[var(--cuadrao-menu-surface)] p-2 dark:border-white/10 ${wide ? "w-[22rem]" : "w-48"}`}>
          {children(close)}
        </div>
      ) : null}
      {phone ? <BottomSheet isOpen={open} onClose={close} title={label} closeLabel={t("common.close")} snaps="fit"><div id={id} className="p-4">{open ? children(close) : null}</div></BottomSheet> : null}
    </div>
  );
}

function PeriodChoices({ period, setPeriod, close }: { period: Period; setPeriod: (period: PeriodKey | Period) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const name = usePeriodLabel();
  const [custom, setCustom] = useState(false);
  const [draft, setDraft] = useState<DayRange>({ from: period.from, to: period.to ?? todayIso() });
  const next = customPeriod(draft.from, draft.to);
  return <>
    <div className={custom ? "mb-3 grid grid-cols-2 gap-1" : "space-y-0.5"}>
      {PERIOD_PRESETS.map((key) => <button key={key} type="button" className={optionClass} onClick={() => { setPeriod(key); close(); }}>
        {name({ ...period, key })}{period.key === key ? <Check className="h-4 w-4 shrink-0" aria-hidden="true" /> : null}
      </button>)}
      <button type="button" className={optionClass} aria-expanded={custom} onClick={() => setCustom((value) => !value)}>{t("business.period.custom")}{period.key === "custom" ? <Check className="h-4 w-4" aria-hidden="true" /> : null}</button>
    </div>
    {custom ? <div className="border-t border-[#DCE0DA] px-1 pt-3 dark:border-white/10">
      <RangeCalendar label={t("business.period.custom")} value={draft} maxDays={366} onChange={setDraft} />
      <button type="button" disabled={!next} className={`${primaryButtonClass} mt-3 w-full`} onClick={() => { if (next) { setPeriod(next); close(); } }}>{t("business.period.apply")}</button>
    </div> : null}
  </>;
}

export function RecordsToolbar({ filter, onChange, period, setPeriod, options }: { filter: RecordsFilter; onChange: (filter: RecordsFilter) => void; period: Period; setPeriod: (period: PeriodKey | Period) => void; options: ReactNode }) {
  const { t } = useTransaccionesWords();
  const periodName = usePeriodLabel();
  const { isBelowTablet: phone, isBelowDesktop } = useResponsiveLayout();
  const preview = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" && !isBelowDesktop;
  const [previewPeriod, setPreviewPeriod] = useState(period);
  const [previewFilters, setPreviewFilters] = useState(emptyPreviewFilters);
  const [views, setViews] = useState<SavedRecordsView[]>([]);
  const restoreView = (selection: RecordsViewSelection) => {
    onChange(selection.record);
    setPreviewPeriod(selection.period);
    setPreviewFilters(selection.filters);
  };
  const kindName = (kind: RecordsFilter["kind"]) => kind === "all" ? t("business.transactions.layout.all_types") : t(`business.transactions.records.detail.${kind}`);
  return <div data-testid="records-toolbar" className="mb-4 flex flex-wrap items-center gap-2">
    {preview ? <RecordsViewsPreview views={views} select={restoreView} save={(name) => setViews((current) => [...current, { name, selection: structuredClone({ record: filter, period: previewPeriod, filters: previewFilters }) }])} /> : null}
    <div className="relative" style={{ width: phone ? "100%" : "min(16rem, 40%)" }}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#56635e] dark:text-white/60" aria-hidden="true" />
      <input type="search" value={filter.query} onChange={(event) => onChange({ ...filter, query: event.target.value })} aria-label={t("business.transactions.layout.search")} placeholder={t("business.transactions.layout.search")} className="h-11 w-full rounded-full border border-[#DCE0DA] bg-white pl-10 pr-3 text-[16px] text-[#172b26] placeholder:text-[#7d8a84] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:border-white/15 dark:bg-[#1f2225] dark:text-white dark:placeholder:text-white/45" />
    </div>
    {preview ? <RecordsDatePreview period={period} value={previewPeriod} onChange={setPreviewPeriod} /> : <ToolbarPicker label={t("business.period.label")} value={periodName(period)} icon={<CalendarDays className="h-4 w-4 shrink-0" aria-hidden="true" />} wide>
      {(close) => <PeriodChoices period={period} setPeriod={setPeriod} close={close} />}
    </ToolbarPicker>}
    <ToolbarPicker label={t(preview ? "business.transactions.layout.filters.record" : "business.transactions.layout.type")} value={filter.kind === "all" ? t(preview ? "business.transactions.layout.filters.record" : "business.transactions.layout.type") : kindName(filter.kind)}>
      {(close) => <div>{(["all", "gasto", "venta"] as const).map((kind) => <button key={kind} type="button" className={optionClass} onClick={() => { onChange({ ...filter, kind }); close(); }}>{kindName(kind)}{filter.kind === kind ? <Check className="h-4 w-4" aria-hidden="true" /> : null}</button>)}</div>}
    </ToolbarPicker>
    {preview ? <RecordsFiltersPreview options={options} value={previewFilters} onChange={setPreviewFilters} /> : <div className="ml-auto flex items-center gap-3">{options}</div>}
    {filter.kind !== "all" || filter.query ? <div className="flex w-full items-center gap-2 pt-1">
      <button type="button" onClick={() => onChange(EMPTY_RECORDS_FILTER)} className="flex min-h-11 items-center gap-1.5 rounded-full px-2 text-[13px] text-[#56635e] hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/65 dark:hover:bg-white/5"><X className="h-3.5 w-3.5" aria-hidden="true" />{t("business.transactions.layout.clear")}</button>
    </div> : null}
  </div>;
}
