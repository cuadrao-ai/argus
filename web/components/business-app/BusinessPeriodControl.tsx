"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { customPeriod, PERIOD_PRESETS, todayIso, type Period, type PeriodKey } from "./business-format";
import { DayTextInput } from "./foundation/DayTextInput";

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
  const chip = (key: PeriodKey, checked: boolean, onClick: () => void) => (
    <button key={key} type="button" role="radio" aria-checked={checked} onClick={onClick} className={`min-h-9 rounded-full px-3.5 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 ${checked ? "bg-white text-black dark:bg-[#2a2d31] dark:text-white" : "text-black/55 hover:text-black dark:text-white/55 dark:hover:text-white"}`}>
      {label(key)}
    </button>
  );
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="business-period-control">
      <div role="radiogroup" aria-label={t("business.period.label", "Period")} className="flex flex-wrap gap-1 rounded-full bg-black/[0.04] p-1 dark:bg-white/[0.06]">
        {PERIOD_PRESETS.map((key) => chip(key, period.key === key && !typing, () => { setTyping(false); setPeriod(key); }))}
        {chip("custom", period.key === "custom" || typing, () => setTyping(true))}
      </div>
      {typing ? (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); const next = customPeriod(from, to); if (next) setPeriod(next); }}>
          <label className="text-[12px] text-black/60 dark:text-white/60">{t("business.period.from", "From")}<DayTextInput required testId="business-period-from" value={from} onChange={(iso) => setFrom(iso ?? "")} className="mt-1 block min-h-11 w-[9.5rem] rounded-[12px] border border-[#7d8a84] bg-transparent px-3 text-[16px] text-black dark:text-white" /></label>
          <label className="text-[12px] text-black/60 dark:text-white/60">{t("business.period.to", "Through")}<DayTextInput required testId="business-period-to" value={to} onChange={(iso) => setTo(iso ?? "")} className="mt-1 block min-h-11 w-[9.5rem] rounded-[12px] border border-[#7d8a84] bg-transparent px-3 text-[16px] text-black dark:text-white" /></label>
          <button type="submit" disabled={!customPeriod(from, to)} className="min-h-9 rounded-full bg-black px-3.5 text-[13px] font-medium text-white disabled:opacity-40 dark:bg-white dark:text-black">{t("business.period.apply", "Show")}</button>
        </form>
      ) : null}
    </div>
  );
}
