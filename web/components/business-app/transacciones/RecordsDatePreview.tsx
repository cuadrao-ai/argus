"use client";

import { useEffect, useState } from "react";
import { CalendarDays, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import type { ReportPeriod } from "@/lib/business-reports-api";
import { formatMonthYear, periodRange, todayIso, type Period } from "../business-format";
import { usePeriodLabel } from "../BusinessPeriodControl";
import RangePicker, { RangePickerConfirm, useRangePickerDraft } from "../foundation/RangePicker";
import { reportKindOf } from "../foundation/range-picker-state";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import styles from "./records-filter-preview.module.css";

const initialRange = (period: Period) => ({ from: period.from && period.key !== "all" ? period.from : todayIso(), to: period.to ?? todayIso() });

type DateLabels = { title?: string; allDatesLabel?: string };

function DateOptions({ title, allDatesLabel, onAll }: DateLabels & { onAll: () => void }) {
  if (!title && !allDatesLabel) return null;
  return <div className={styles.footer}>{title ? <span className="text-[14px] font-medium">{title}</span> : null}{allDatesLabel ? <button type="button" className={styles.clear} onClick={onAll}>{allDatesLabel}</button> : null}</div>;
}

type PresetKind = Exclude<ReportPeriod["kind"], "custom">;
type DateSessionProps = DateLabels & { onPreset?: (kind: PresetKind) => void; period: Period; apply: (period: Period) => void; close: () => void };

function useDateChoice({ period, apply, close, onPreset }: Pick<DateSessionProps, "period" | "apply" | "close" | "onPreset">) {
  const finish = (kind: PresetKind | null, next: Period) => { if (onPreset && kind) onPreset(kind); else apply(next); close(); };
  return useRangePickerDraft(
    initialRange(period),
    (range) => finish(reportKindOf(range, todayIso()), { key: "custom", ...range }),
    undefined,
    () => finish("all", periodRange("all")),
  );
}

function DesktopDateSession({ title, allDatesLabel, ...choice }: DateSessionProps) {
  const session = useDateChoice(choice);
  return <><DateOptions title={title} allDatesLabel={allDatesLabel} onAll={() => { choice.apply(periodRange("all")); choice.close(); }} /><RangePicker session={session} /><RangePickerConfirm session={session} /></>;
}

function PhoneDateSession({ open, title, allDatesLabel, ...choice }: DateSessionProps & { open: boolean }) {
  const { t } = useTranslation();
  const session = useDateChoice(choice);
  return <BottomSheet isOpen={open} onClose={choice.close} title={title ?? t("business.date_range.title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={<RangePickerConfirm session={session} phone />}><DateOptions allDatesLabel={allDatesLabel} onAll={() => { choice.apply(periodRange("all")); choice.close(); }} /><RangePicker session={session} phone /></BottomSheet>;
}

export default function RecordsDatePreview({ period, value, onChange, onPreset, reportPeriod, title, allDatesLabel }: DateLabels & { reportPeriod?: ReportPeriod; onPreset?: (kind: PresetKind) => void; period: Period; value?: Period; onChange?: (next: Period) => void }) {
  const [localPeriod, setLocalPeriod] = useState(period);
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState(0);
  const [wide, setWide] = useState(false);
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const { t, i18n } = useTranslation();
  useEffect(() => {
    const update = () => setWide(window.innerWidth >= 1600);
    update(); window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  const selected = value ?? localPeriod;
  const apply = (next: Period) => { if (onChange) onChange(next); else setLocalPeriod(next); };
  const name = usePeriodLabel();
  const latestMonth = selected.from ? formatMonthYear(selected.from, i18n.language) : t("business.period.label");
  const label = reportPeriod?.kind === "this_year" ? new Intl.DateTimeFormat(undefined, { year: "numeric", timeZone: "America/Santo_Domingo" }).format(new Date()) : reportPeriod?.kind === "latest_month" ? latestMonth : selected.key === "all" && allDatesLabel ? allDatesLabel : name(selected);
  if (phone) return <>
    <button type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => { setSessionId((id) => id + 1); setOpen(true); }}><CalendarDays size={17} aria-hidden="true" /><span>{label}</span><ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>
    <PhoneDateSession title={title} allDatesLabel={allDatesLabel} key={sessionId} period={selected} onPreset={onPreset} apply={apply} open={open} close={() => setOpen(false)} />
  </>;
  return <RecordsPreviewPopover label={label} icon={<CalendarDays size={17} aria-hidden="true" />} width={wide ? 1200 : 900} preferredHeight={640}>{(close) => <DesktopDateSession title={title} allDatesLabel={allDatesLabel} period={selected} onPreset={onPreset} apply={apply} close={close} />}</RecordsPreviewPopover>;
}
