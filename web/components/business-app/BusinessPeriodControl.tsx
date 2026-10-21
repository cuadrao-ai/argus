"use client";

import { useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import BottomSheet from "@/components/ui/BottomSheet";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { customPeriod, formatShortDay, PERIOD_PRESETS, todayIso, type Period, type PeriodKey } from "./business-format";
import { RangeCalendar, type DayRange } from "./foundation/RangeCalendar";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

/** The longest range the calendar takes, the export's own limit. */
const MAX_DAYS = 366;
/** The phone picker's option for the range already applied. */
const CHOSEN = "chosen";

/** A period's name: the preset's word, or a chosen range as "21 sept – 20 oct". */
export function usePeriodLabel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "es-419";
  return (period: Pick<Period, "key" | "from" | "to">) =>
    period.key === "custom"
      ? t("business.period.range", { from: formatShortDay(period.from, locale), to: formatShortDay(period.to ?? todayIso(), locale), defaultValue: "{{from}} – {{to}}" })
      : ({
          this_month: t("business.period.this_month", "This month"),
          last_month: t("business.period.last_month", "Last month"),
          last_30_days: t("business.period.last_30_days", "Last 30 days"),
          all: t("business.period.all", "All"),
        })[period.key];
}

/**
 * The one period chooser: the presets, or Personalizado, which opens the
 * range calendar in a popover under its segment (a sheet on a phone) so
 * nothing in the row moves. Once applied, the segment reads the range.
 */
export default function BusinessPeriodControl({ period, setPeriod }: { period: Period; setPeriod: (next: PeriodKey | Period) => void }) {
  const { t } = useTranslation();
  const name = usePeriodLabel();
  const { isBelowTablet } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DayRange>(() => ({ from: period.from, to: period.to ?? todayIso() }));
  const [anchor, setAnchor] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const popoverId = useId();
  const custom = name({ key: "custom", from: period.from, to: period.to });
  const label = (key: PeriodKey) => (key === "custom" ? (period.key === "custom" ? custom : t("business.period.custom", "Custom")) : name({ key, from: period.from, to: period.to }));
  const keys = [...PERIOD_PRESETS, "custom" as const];

  const close = () => setOpen(false);
  const choose = (key: PeriodKey) => {
    if (key !== "custom") {
      close();
      setPeriod(key);
      return;
    }
    const segment = root.current?.querySelector<HTMLElement>('[data-segment="custom"]');
    // The popover's right edge meets the segment's, so it grows toward the page and never past the canvas.
    if (segment && root.current) setAnchor(root.current.getBoundingClientRect().right - segment.getBoundingClientRect().right);
    setDraft({ from: period.from, to: period.to ?? todayIso() });
    setOpen(true);
  };
  const apply = () => {
    const next = customPeriod(draft.from, draft.to);
    if (!next) return;
    setPeriod(next);
    close();
  };
  useOverlayLayer({ isOpen: open && !isBelowTablet, overlayId: popoverId, containerRef: root, onEscape: close, onOutsidePointerDown: close });

  const calendar = <RangeCalendar label={t("business.period.custom", "Custom")} value={draft} maxDays={MAX_DAYS} onChange={setDraft} />;
  const show = <button type="button" data-testid="period-apply" disabled={!customPeriod(draft.from, draft.to)} onClick={apply} className={`${primaryButtonClass} w-full`}>{t("business.period.apply", "Show")}</button>;

  return (
    <div ref={root} className="relative inline-flex" data-testid="business-period-control">
      {isBelowTablet ? (
        // Five periods never fit a phone's width as a bar; the phone's own picker fits any width, and Personalizado opens the calendar sheet.
        <span className="relative inline-flex">
          <select
            aria-label={t("business.period.label", "Period")}
            value={period.key === "custom" ? CHOSEN : period.key}
            onChange={(event) => { if (event.target.value !== CHOSEN) choose(event.target.value as PeriodKey); }}
            className={`${secondaryButtonClass} appearance-none pr-10`}
          >
            {PERIOD_PRESETS.map((key) => <option key={key} value={key}>{label(key)}</option>)}
            {/* An applied range shows as its own option, so Personalizado stays pickable for a new one. */}
            {period.key === "custom" ? <option value={CHOSEN}>{custom}</option> : null}
            <option value="custom">{t("business.period.custom", "Custom")}</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#56635e] dark:text-white/60" aria-hidden="true" />
        </span>
      ) : (
        <SegmentedControl
          label={t("business.period.label", "Period")}
          segments={keys.map((key) => ({ key, label: label(key) }))}
          value={period.key}
          onChange={choose}
        />
      )}
      {open && !isBelowTablet ? (
        <div id={popoverId} role="dialog" aria-label={t("business.period.custom", "Custom")} data-testid="period-popover" style={{ right: anchor }} className="absolute top-full z-[70] mt-2 w-[22rem] origin-top-right rounded-surface border border-[#DCE0DA] bg-[var(--cuadrao-menu-surface)] p-4 dark:border-white/10">
          {calendar}
          <div className="mt-3">{show}</div>
        </div>
      ) : null}
      {isBelowTablet ? (
        <BottomSheet isOpen={open} onClose={close} title={t("business.period.custom", "Custom")} closeLabel={t("common.close", "Close")} snaps="fit" footer={show}>
          <div data-testid="period-sheet">{calendar}</div>
        </BottomSheet>
      ) : null}
    </div>
  );
}
