"use client";

import { useEffect, useState } from "react";
import { CalendarDays, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import type { ReportPeriod } from "@/lib/business-reports-api";
import { formatMonthYear, namedPeriod, periodRange, todayIso, type Period } from "../business-format";
import { usePeriodLabel } from "../BusinessPeriodControl";
import { PRESET_KEYS } from "../foundation/range-picker-state";
import RangePicker, { RangePickerConfirm, useRangePickerDraft } from "../foundation/RangePicker";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import styles from "./records-filter-preview.module.css";

type DateLabels = { title?: string };

function DateTitle({ title }: DateLabels) {
  return title ? <div className={styles.footer}><span className="text-[14px] font-medium">{title}</span></div> : null;
}

type DateSessionProps = DateLabels & { period: Period; apply: (period: Period) => void; close: () => void };

const initialRange = (period: Period) => period.key === "all" ? { from: "", to: "" } : { from: period.from || todayIso(), to: period.to ?? todayIso() };

function useDateChoice({ period, apply, close }: Pick<DateSessionProps, "period" | "apply" | "close">) {
  const finish = (next: Period) => { apply(next); close(); };
  return useRangePickerDraft(initialRange(period), (range) => finish(namedPeriod(range, todayIso())), undefined, () => finish(periodRange("all")));
}

function DesktopDateSession({ title, ...choice }: DateSessionProps) {
  const session = useDateChoice(choice);
  return <><DateTitle title={title} /><RangePicker session={session} /><RangePickerConfirm session={session} /></>;
}

function PhoneDateSession({ open, title, ...choice }: DateSessionProps & { open: boolean }) {
  const { t } = useTranslation();
  const session = useDateChoice(choice);
  return <BottomSheet isOpen={open} onClose={choice.close} title={title ?? t("business.date_range.title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={<RangePickerConfirm session={session} phone />}><RangePicker session={session} phone /></BottomSheet>;
}

/** The screen's name for its period: the newest month by name, Todo, or the preset or range. */
export function useRecordsPeriodLabel() {
  const { t, i18n } = useTranslation();
  const name = usePeriodLabel();
  return (selected: Period, reportPeriod?: ReportPeriod) => reportPeriod?.kind === "latest_month" ? selected.from ? formatMonthYear(selected.from, i18n.language) : t("business.period.label") : selected.key === "all" ? t(PRESET_KEYS.all) : name(selected);
}

export default function RecordsDatePreview({ period, value, onChange, reportPeriod, title }: DateLabels & { reportPeriod?: ReportPeriod; period: Period; value?: Period; onChange?: (next: Period) => void }) {
  const [localPeriod, setLocalPeriod] = useState(period);
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState(0);
  const [wide, setWide] = useState(false);
  const { isBelowDesktop: phone } = useResponsiveLayout();
  useEffect(() => {
    const update = () => setWide(window.innerWidth >= 1600);
    update(); window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  const selected = value ?? localPeriod;
  const apply = (next: Period) => { if (onChange) onChange(next); else setLocalPeriod(next); };
  const label = useRecordsPeriodLabel()(selected, reportPeriod);
  if (phone) return <>
    <button type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => { setSessionId((id) => id + 1); setOpen(true); }}><CalendarDays size={17} aria-hidden="true" /><span>{label}</span><ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>
    <PhoneDateSession title={title} key={sessionId} period={selected} apply={apply} open={open} close={() => setOpen(false)} />
  </>;
  return <RecordsPreviewPopover label={label} icon={<CalendarDays size={17} aria-hidden="true" />} width={wide ? 1200 : 900} preferredHeight={640}>{(close) => <DesktopDateSession title={title} period={selected} apply={apply} close={close} />}</RecordsPreviewPopover>;
}
