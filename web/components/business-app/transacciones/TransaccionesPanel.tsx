"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { Check, SlidersHorizontal } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness } from "../BusinessWorkspace";
import BusinessAddMenu from "../BusinessAddMenu";
import BusinessPeriodControl, { usePeriodLabel } from "../BusinessPeriodControl";
import { formatShortDay } from "../business-format";
import { cardClass, primaryButtonClass } from "../business-ui";
import { EmptyState } from "../foundation/EmptyState";
import { useClaimScreenPrimary } from "../screen-primary";
import { useWideCanvas } from "../wide-canvas";
import { DENSITIES, DENSITY_ROW_PX, setTableDensity, useTableDensity, type Density } from "./table-density";
import { defaultSegment, headerCurrency, inHeaderOrder, SEGMENTS, segmentCount, suggestionRun, type Segment, type Totals } from "./transacciones-model";
import { KeyHint, MoneyList, Unknown } from "./transacciones-parts";
import { TransaccionesList } from "./TransaccionesList";
import { TransaccionesTable } from "./TransaccionesTable";
import { TransaccionesTray } from "./TransaccionesTray";
import { useTransaccionesWords } from "./transacciones-words";
import { useTransacciones } from "./useTransacciones";

/**
 * Transacciones: does every peso that moved have its proof? One ledger of
 * movements with a proof slot, a suggestion run in the tray, and the
 * server's totals above. Behind `businessBankMatchingEnabled`.
 */
export default function TransaccionesPanel() {
  const { t, locale } = useTransaccionesWords();
  const { period, setPeriod } = useBusiness();
  const periodLabel = usePeriodLabel();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const density = useTableDensity();
  const controller = useTransacciones();
  const { list, movements, tray } = controller;
  const [chosen, setChosen] = useState<Segment | null>(null);
  const segment = chosen ?? (list.kind === "ready" ? defaultSegment(movements) : "por_igualar");
  const runCount = suggestionRun(movements).length;
  const showRun = list.kind === "loading" || runCount > 0;
  useClaimScreenPrimary(showRun);
  useWideCanvas();

  const rowNodes = useRef(new Map<string, HTMLElement>());
  const trayId = tray?.movementId ?? null;
  // Focus returns to the open row on close; the row's node is read when the tray needs it, not during render.
  const trayRow = useMemo(() => ({ get current() { return trayId ? rowNodes.current.get(trayId) ?? null : null; } }), [trayId]) as RefObject<HTMLElement | null>;
  const rowRef = (id: string, node: HTMLElement | null) => {
    if (node) rowNodes.current.set(id, node);
    else rowNodes.current.delete(id);
  };
  const trayMovement = tray ? controller.byId.get(tray.movementId) : undefined;
  const stepSegment = (step: 1 | -1) => setChosen(SEGMENTS[(SEGMENTS.indexOf(segment) + step + SEGMENTS.length) % SEGMENTS.length]);

  const view = list.kind === "ready" ? list.view : null;
  const monthly = period.key === "this_month" || period.key === "last_month";
  const when = monthly ? capitalize(new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(new Date(`${period.from}T12:00:00`))) : periodLabel(period.key);
  const subtitle = [when, view?.coverageThrough ? t("business.transactions.coverage", { day: formatShortDay(view.coverageThrough, locale) }) : null].filter(Boolean).join(". ");
  const porIgualar = view?.totals.porIgualar?.count ?? null;

  const run = showRun ? (
    <button type="button" data-testid="transacciones-run" data-primary="true" disabled={list.kind !== "ready"} onClick={controller.startRun} className={`${primaryButtonClass} ${phone ? "shrink-0" : ""}`}>
      {phone ? t("business.transactions.run_short") : t("business.transactions.run")}
      {list.kind === "ready" ? <span className="tabular-nums opacity-85">{runCount}</span> : null}
      {phone ? null : <KeyHint>I</KeyHint>}
    </button>
  ) : null;

  return (
    <section data-testid="transacciones" className="pb-6">
      {phone ? <div className="mb-4"><BusinessAddMenu placement="page" /></div> : null}
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{t("business.transactions.title")}</h2>
          <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/65">{subtitle}</p>
        </div>
        {phone ? null : run}
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SegmentedControl
          testId="transacciones-segments"
          label={t("business.transactions.segments.label")}
          fill={phone}
          value={segment}
          onChange={setChosen}
          segments={SEGMENTS.map((key) => ({ key, label: t(`business.transactions.segments.${key}`), count: key === "por_igualar" ? porIgualar : null }))}
        />
        <BusinessPeriodControl period={period} setPeriod={setPeriod} />
        {phone ? <div className="ml-auto">{run}</div> : <div className="ml-auto"><DensityMenu density={density} /></div>}
      </div>
      <Summary totals={view?.totals ?? null} header={headerCurrency(movements)} locale={locale} loading={list.kind === "loading"} />
      {list.kind === "failed" ? (
        <div className={cardClass}>
          <EmptyState kind="error" compact testId="transacciones-error" title={t("business.transactions.error.load_title")} body={t("business.transactions.error.load_body")} action={{ label: t("common.retry", "Reintentar"), run: controller.retryLoad }} />
        </div>
      ) : list.kind === "loading" ? (
        <LoadingRows density={phone ? "amplio" : density} />
      ) : movements.length === 0 ? (
        <div className={cardClass}>
          <EmptyState kind="first_run" mark="receipt" compact testId="transacciones-empty" title={t("business.transactions.empty.first_run_title")} body={t("business.transactions.empty.first_run_body")} />
        </div>
      ) : segmentCount(movements, segment) === 0 ? (
        <div className={cardClass}>
          {segment === "por_igualar"
            ? <EmptyState kind="done" compact testId="transacciones-done" title={t("business.transactions.empty.done_title")} body={t("business.transactions.empty.done_body", { count: view?.totals.igualadas?.of ?? movements.length })} />
            : <EmptyState kind="filtered" compact title={t("business.transactions.empty.segment")} />}
        </div>
      ) : phone ? (
        <TransaccionesList controller={controller} movements={movements} segment={segment} rowRef={rowRef} />
      ) : (
        <TransaccionesTable controller={controller} movements={movements} segment={segment} density={density} onSegmentStep={stepSegment} onRunKey={controller.startRun} rowRef={rowRef} />
      )}
      {trayMovement ? <TransaccionesTray key={tray?.run ? "run" : trayMovement.id} controller={controller} movement={trayMovement} phone={phone} returnFocusRef={trayRow} /> : null}
    </section>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toLocaleUpperCase() + text.slice(1);
}

/** The server's totals: exact, one per currency, the header's first. A part it does not serve reads as unknown. */
function Summary({ totals, header, locale, loading }: { totals: Totals | null; header: string | null; locale: string; loading: boolean }) {
  const { t } = useTransaccionesWords();
  const order = (money: Totals["entradas"]) => (money ? inHeaderOrder(money, header) : null);
  const cells: { key: string; value: React.ReactNode }[] = [
    { key: "entradas", value: <MoneyList totals={order(totals?.entradas ?? null)} header={header} locale={locale} /> },
    { key: "salidas", value: <MoneyList totals={order(totals?.salidas ?? null)} header={header} locale={locale} /> },
    {
      key: "por_igualar",
      value: totals?.porIgualar ? (
        <span className="flex flex-wrap items-baseline gap-x-2"><span className="tabular-nums">{totals.porIgualar.count}</span>{totals.porIgualar.amounts ? <span className="text-[14px] font-normal text-[#56635e] dark:text-white/65"><MoneyList totals={order(totals.porIgualar.amounts)} header={header} locale={locale} /></span> : null}</span>
      ) : <Unknown />,
    },
    {
      key: "igualadas",
      value: totals?.igualadas ? (
        <span className="flex items-baseline gap-x-2"><span className="tabular-nums">{totals.igualadas.count}</span><span className="text-[14px] font-normal text-[#56635e] dark:text-white/65">{t("business.transactions.totals.of", { count: totals.igualadas.of })}</span></span>
      ) : <Unknown />,
    },
  ];
  return (
    <dl data-testid="transacciones-summary" className="mb-4 grid grid-cols-2 overflow-hidden rounded-[20px] border border-[#DCE0DA] bg-white tablet:grid-cols-4 dark:border-white/10 dark:bg-[#1f2225]">
      {cells.map((cell, index) => (
        <div key={cell.key} data-total={cell.key} className={`min-w-0 px-4 py-3 ${index % 2 ? "border-l" : ""} ${index > 1 ? "border-t tablet:border-t-0" : ""} ${index === 2 ? "tablet:border-l" : ""} border-[#DCE0DA] dark:border-white/10`}>
          <dt className="text-[13px] text-[#56635e] dark:text-white/65">{t(`business.transactions.totals.${cell.key}`)}</dt>
          <dd className="mt-1 text-[17px] font-medium text-[#172b26] dark:text-white">
            {loading ? <span aria-hidden="true" className="block h-5 w-28 animate-pulse rounded-md bg-black/[0.06] motion-reduce:animate-none dark:bg-white/[0.08]" /> : cell.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Skeleton rows at the chosen row height, so nothing jumps when the rows arrive. Only while loading. */
function LoadingRows({ density }: { density: Density }) {
  const { t } = useTransaccionesWords();
  return (
    <div role="status" aria-label={t("common.loading", "Cargando")} data-testid="transacciones-loading" className="overflow-hidden rounded-[20px] border border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1f2225]">
      <div aria-hidden="true" className="animate-pulse motion-reduce:animate-none">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} style={{ height: DENSITY_ROW_PX[density] }} className="flex items-center gap-4 border-b border-[#DCE0DA] px-3 last:border-b-0 dark:border-white/10">
            <span className="h-4 w-4 rounded-full bg-black/[0.06] dark:bg-white/[0.08]" />
            <span className="h-3 w-48 rounded-md bg-black/[0.06] dark:bg-white/[0.08]" />
            <span className="ml-auto h-3 w-20 rounded-md bg-black/[0.06] dark:bg-white/[0.08]" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The quiet view options at the right of the filters: the table's row height, kept per person. */
function DensityMenu({ density }: { density: Density }) {
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
        <div role="menu" aria-label={t("business.transactions.density.label")} className="absolute right-0 top-full z-40 mt-2 w-56 origin-top-right rounded-[14px] border border-black/10 bg-white p-1.5 dark:border-white/10 dark:bg-[#1f2225]">
          <p className="px-2.5 pb-1 pt-1.5 text-[12px] font-medium text-[#56635e] dark:text-white/65">{t("business.transactions.density.label")}</p>
          {DENSITIES.map((option) => (
            <button key={option} type="button" role="menuitemradio" aria-checked={option === density} data-density-option={option} onClick={() => { setTableDensity(option); setOpen(false); }} className="flex min-h-10 w-full items-center justify-between rounded-[10px] px-2.5 text-left text-[14px] text-[#172b26] hover:bg-black/5 focus-visible:bg-black/5 focus-visible:outline-none aria-checked:font-medium dark:text-white dark:hover:bg-white/5">
              {t(`business.transactions.density.${option}`)}
              {option === density ? <Check className="h-4 w-4 text-[var(--cuadrao-green)]" aria-hidden="true" /> : null}
            </button>
          ))}
          <p className="px-2.5 pb-1.5 pt-1 text-[12px] text-[#56635e] dark:text-white/65">{t("business.transactions.density.note")}</p>
        </div>
      ) : null}
    </div>
  );
}
