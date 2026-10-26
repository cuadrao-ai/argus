"use client";

import { useEffect, useState } from "react";
import { CalendarDays, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { todayIso, type Period } from "../business-format";
import { usePeriodLabel } from "../BusinessPeriodControl";
import RangePicker, { RangePickerConfirm, useRangePickerDraft } from "../foundation/RangePicker";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import styles from "./records-filter-preview.module.css";

const initialRange = (period: Period) => ({ from: period.key === "all" ? todayIso() : period.from, to: period.to ?? todayIso() });

function DesktopDateSession({ period, apply, close }: { period: Period; apply: (period: Period) => void; close: () => void }) {
  const session = useRangePickerDraft(initialRange(period), (range) => { apply({ key: "custom", ...range }); close(); });
  return <><RangePicker session={session} /><RangePickerConfirm session={session} /></>;
}

function PhoneDateSession({ period, apply, open, close }: { period: Period; apply: (period: Period) => void; open: boolean; close: () => void }) {
  const { t } = useTranslation();
  const session = useRangePickerDraft(initialRange(period), (range) => { apply({ key: "custom", ...range }); close(); });
  return <BottomSheet isOpen={open} onClose={close} title={t("business.date_range.title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={<RangePickerConfirm session={session} phone />}><RangePicker session={session} phone /></BottomSheet>;
}

export default function RecordsDatePreview({ period, value, onChange }: { period: Period; value?: Period; onChange?: (next: Period) => void }) {
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
  if (phone) return <>
    <button type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => { setSessionId((id) => id + 1); setOpen(true); }}><CalendarDays size={17} aria-hidden="true" /><span>{name(selected)}</span><ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>
    <PhoneDateSession key={sessionId} period={selected} apply={apply} open={open} close={() => setOpen(false)} />
  </>;
  return <RecordsPreviewPopover label={name(selected)} icon={<CalendarDays size={17} aria-hidden="true" />} width={wide ? 1200 : 900} preferredHeight={640}>{(close) => <DesktopDateSession period={selected} apply={apply} close={close} />}</RecordsPreviewPopover>;
}
