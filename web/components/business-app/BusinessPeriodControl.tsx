"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { customPeriod, PERIOD_PRESETS, todayIso, type Period, type PeriodKey } from "./business-format";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

export function usePeriodLabel() {
  const { t } = useTranslation();
  return (key: PeriodKey) =>
    ({
      this_month: t("business.period.this_month", "This month"),
      last_month: t("business.period.last_month", "Last month"),
      last_30_days: t("business.period.last_30_days", "Last 30 days"),
      all: t("business.period.all", "All"),
      custom: t("business.period.custom", "Custom"),
    })[key];
}

/** The one period chooser for the home and the expenses: presets, all, or a typed range. */
export default function BusinessPeriodControl({ period, setPeriod }: { period: Period; setPeriod: (next: PeriodKey | Period) => void }) {
  const { t } = useTranslation();
  const label = usePeriodLabel();
  const [typing, setTyping] = useState(period.key === "custom");
  const [from, setFrom] = useState(period.from);
  const [to, setTo] = useState(period.to ?? todayIso());
  const { isBelowTablet } = useResponsiveLayout();
  const keys = [...PERIOD_PRESETS, "custom" as const];
  const choose = (key: PeriodKey) => {
    if (key === "custom") { setTyping(true); return; }
    setTyping(false);
    setPeriod(key);
  };
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="business-period-control">
      {isBelowTablet ? (
        // Five periods never fit a phone's width as a bar; the phone's own picker fits any width.
        <span className="relative inline-flex">
          <select
            aria-label={t("business.period.label", "Period")}
            value={typing ? "custom" : period.key}
            onChange={(event) => choose(event.target.value as PeriodKey)}
            className={`${secondaryButtonClass} appearance-none pr-10`}
          >
            {keys.map((key) => <option key={key} value={key}>{label(key)}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#56635e] dark:text-white/60" aria-hidden="true" />
        </span>
      ) : (
        <SegmentedControl
          label={t("business.period.label", "Period")}
          segments={keys.map((key) => ({ key, label: label(key) }))}
          value={typing ? "custom" : period.key}
          onChange={choose}
        />
      )}
      {typing ? (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); const next = customPeriod(from, to); if (next) setPeriod(next); }}>
          <label className="text-[12px] text-black/60 dark:text-white/60">{t("business.period.from", "From")}<input type="date" required value={from} max={to} onChange={(event) => setFrom(event.target.value)} className="mt-1 block min-h-9 rounded-item border border-black/15 bg-transparent px-2 text-[13px] text-black dark:border-white/20 dark:text-white" /></label>
          <label className="text-[12px] text-black/60 dark:text-white/60">{t("business.period.to", "Through")}<input type="date" required value={to} min={from} onChange={(event) => setTo(event.target.value)} className="mt-1 block min-h-9 rounded-item border border-black/15 bg-transparent px-2 text-[13px] text-black dark:border-white/20 dark:text-white" /></label>
          <button type="submit" disabled={!customPeriod(from, to)} className={primaryButtonClass}>{t("business.period.apply", "Show")}</button>
        </form>
      ) : null}
    </div>
  );
}
