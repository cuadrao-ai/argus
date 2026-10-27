"use client";

import { useEffect, useState } from "react";
import { CalendarDays, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import type { ReportPeriod } from "@/lib/business-reports-api";
import { periodRange, todayIso, type Period } from "../business-format";
import { usePeriodLabel } from "../BusinessPeriodControl";
import RangePicker, { RangePickerConfirm, useRangePickerDraft } from "../foundation/RangePicker";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import styles from "./records-filter-preview.module.css";

const initialRange = (period: Period) => ({ from: period.key === "all" ? todayIso() : period.from, to: period.to ?? todayIso() });

type DateLabels = { title?: string; allDatesLabel?: string };

function DateOptions({ title, allDatesLabel, onAll }: DateLabels & { onAll: () => void }) {
  if (!title && !allDatesLabel) return null;
  return <div className={styles.footer}>{title ? <span className="text-[14px] font-medium">{title}</span> : null}{allDatesLabel ? <button type="button" className={styles.clear} onClick={onAll}>{allDatesLabel}</button> : null}</div>;
}

function ReportPresets({ choose }: { choose: (kind: Exclude<ReportPeriod["kind"], "custom">) => void }) {
  const { t } = useTranslation();
  return <div className={styles.currencies}>{(["all", "this_month", "last_month", "this_year"] as const).map((kind) => <button key={kind} type="button" className={styles.currency} onClick={() => choose(kind)}>{kind === "this_year" ? new Intl.DateTimeFormat(undefined, { year: "numeric", timeZone: "America/Santo_Domingo" }).format(new Date()) : t(`business.period.${kind}`)}</button>)}</div>;
}

function DesktopDateSession({ period, apply, close, onPreset, title, allDatesLabel }: DateLabels & { onPreset?: (kind: Exclude<ReportPeriod["kind"], "custom">) => void; period: Period; apply: (period: Period) => void; close: () => void }) {
  const session = useRangePickerDraft(initialRange(period), (range) => { apply({ key: "custom", ...range }); close(); });
  return <><DateOptions title={title} allDatesLabel={allDatesLabel} onAll={() => { apply(periodRange("all")); close(); }} />{onPreset ? <ReportPresets choose={(kind) => { onPreset(kind); close(); }} /> : null}<RangePicker session={session} /><RangePickerConfirm session={session} /></>;
}

function PhoneDateSession({ period, apply, open, close, onPreset, title, allDatesLabel }: DateLabels & { onPreset?: (kind: Exclude<ReportPeriod["kind"], "custom">) => void; period: Period; apply: (period: Period) => void; open: boolean; close: () => void }) {
  const { t } = useTranslation();
  const session = useRangePickerDraft(initialRange(period), (range) => { apply({ key: "custom", ...range }); close(); });
  return <BottomSheet isOpen={open} onClose={close} title={title ?? t("business.date_range.title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={<RangePickerConfirm session={session} phone />}><DateOptions allDatesLabel={allDatesLabel} onAll={() => { apply(periodRange("all")); close(); }} />{onPreset ? <ReportPresets choose={(kind) => { onPreset(kind); close(); }} /> : null}<RangePicker session={session} phone /></BottomSheet>;
}

export default function RecordsDatePreview({ period, value, onChange, onPreset, reportPeriod, title, allDatesLabel }: DateLabels & { reportPeriod?: ReportPeriod; onPreset?: (kind: Exclude<ReportPeriod["kind"], "custom">) => void; period: Period; value?: Period; onChange?: (next: Period) => void }) {
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
  const name = usePeriodLabel();
  const label = reportPeriod?.kind === "this_year" ? new Intl.DateTimeFormat(undefined, { year: "numeric", timeZone: "America/Santo_Domingo" }).format(new Date()) : selected.key === "all" && allDatesLabel ? allDatesLabel : name(selected);
  if (phone) return <>
    <button type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => { setSessionId((id) => id + 1); setOpen(true); }}><CalendarDays size={17} aria-hidden="true" /><span>{label}</span><ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>
    <PhoneDateSession title={title} allDatesLabel={allDatesLabel} key={sessionId} period={selected} onPreset={onPreset} apply={apply} open={open} close={() => setOpen(false)} />
  </>;
  return <RecordsPreviewPopover label={label} icon={<CalendarDays size={17} aria-hidden="true" />} width={wide ? 1200 : 900} preferredHeight={640}>{(close) => <DesktopDateSession title={title} allDatesLabel={allDatesLabel} period={selected} onPreset={onPreset} apply={apply} close={close} />}</RecordsPreviewPopover>;
}
