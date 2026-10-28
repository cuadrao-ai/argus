"use client";

// DRAFT (design lane): Actividad's Filtros, built from the same parts and structure as Bandeja's
// (ReceptionFilters): popover on desktop, full sheet on phones, a draft applied with Aplicar, Limpiar,
// and removable chips. A shared filter shell for all three screens is a follow-up for their owners.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, CalendarDays, ChevronDown, ChevronRight, ListChecks, ListFilter, Shapes, Users, X, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import RecordsPreviewPopover from "../transacciones/RecordsPreviewPopover";
import RecordsFilterSelection from "../transacciones/RecordsFilterSelection";
import styles from "../transacciones/records-filter-preview.module.css";

export type ActivityDate = "all" | "today" | "week" | "month";
export type ActivityFilterValue = { date: ActivityDate; people: string[]; areas: string[]; actions: string[] };
export const EMPTY_ACTIVITY_FILTERS: ActivityFilterValue = { date: "all", people: [], areas: [], actions: [] };

type Group = "date" | "people" | "areas" | "actions";
type Option = { value: string; label: string };
export type ActivityFilterWords = { title: string; date: string; people: string; areas: string; actions: string; clear: string; clearGroup: string; dates: Record<ActivityDate, string>; remove: (label: string) => string };
type Props = { value: ActivityFilterValue; onChange: (value: ActivityFilterValue) => void; options: { people: Option[]; areas: Option[]; actions: Option[] }; words: ActivityFilterWords };

const ICONS: Record<Group, LucideIcon> = { date: CalendarDays, people: Users, areas: Shapes, actions: ListChecks };
const DATES: readonly ActivityDate[] = ["all", "today", "week", "month"];
const isActive = (value: ActivityFilterValue, group: Group) => group === "date" ? value.date !== "all" : value[group].length > 0;

function FilterEditor({ value, onChange, options, words, close, phone = false, groups }: Props & { close: () => void; phone?: boolean; groups: readonly Group[] }) {
  const { t } = useTranslation();
  const shared = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const [draft, setDraft] = useState(value);
  const [group, setGroup] = useState<Group>(groups[0]);
  const [choosing, setChoosing] = useState(phone);
  const rail = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const navigated = useRef(false);
  useEffect(() => {
    if (!phone || !navigated.current) return;
    if (choosing) rail.current?.querySelector<HTMLButtonElement>(`[data-group="${group}"]`)?.focus();
    else back.current?.focus();
  }, [phone, choosing, group]);
  const body = <div className={phone ? styles.phonePanel : styles.panel}>
    {!phone || choosing ? <div ref={rail} className={styles.rail} role={phone ? undefined : "tablist"} aria-label={words.title} aria-orientation={phone ? undefined : "vertical"} onKeyDown={event => {
      if (phone || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = event.key === "Home" ? 0 : event.key === "End" ? groups.length - 1 : (groups.indexOf(group) + (event.key === "ArrowDown" ? 1 : -1) + groups.length) % groups.length;
      setGroup(groups[index]);
      event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[index]?.focus();
    }}>
      {groups.map(key => { const Icon = ICONS[key]; return <button key={key} type="button" data-group={key} role={phone ? undefined : "tab"} tabIndex={phone || group === key ? 0 : -1} aria-selected={phone ? undefined : group === key} className={styles.group} onClick={() => { navigated.current = true; setGroup(key); setChoosing(false); }}><Icon size={17} aria-hidden="true" /><span>{words[key]}</span>{isActive(draft, key) ? <span className={styles.count} aria-hidden="true">•</span> : null}{phone ? <ChevronRight size={16} aria-hidden="true" /> : null}</button>; })}
    </div> : null}
    {!phone || !choosing ? <section className={styles.editor} role={phone ? undefined : "tabpanel"} aria-label={words[group]}>
      {phone ? <button ref={back} type="button" className={styles.clear} onClick={() => setChoosing(true)}><ArrowLeft size={18} aria-hidden="true" />{shared("back")}</button> : null}
      <div className="flex items-center justify-between gap-3"><h3 className={styles.heading}>{words[group]}</h3><button type="button" className={styles.clear} onClick={() => setDraft(group === "date" ? { ...draft, date: "all" } : { ...draft, [group]: [] })}>{words.clearGroup}</button></div>
      {group === "date"
        ? DATES.map(date => <label key={date} className={styles.choice}><input type="radio" name="activity-date" className="!rounded-full" checked={draft.date === date} onChange={() => setDraft({ ...draft, date })} /><span>{words.dates[date]}</span></label>)
        : <RecordsFilterSelection options={options[group]} selected={draft[group]} onChange={next => setDraft({ ...draft, [group]: next })} />}
    </section> : null}
  </div>;
  const footer = <div className={phone ? `${styles.footer} ${styles.phoneFooter}` : styles.footer}><button type="button" className={styles.clear} onClick={() => setDraft(groups.includes("date") ? EMPTY_ACTIVITY_FILTERS : { ...EMPTY_ACTIVITY_FILTERS, date: draft.date })}>{words.clear}</button><button type="button" className={styles.apply} onClick={() => { onChange(draft); close(); }}>{shared("apply")}</button></div>;
  return phone ? <BottomSheet isOpen onClose={close} title={words.title} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={footer}>{body}</BottomSheet> : <>{body}{footer}</>;
}

/** Fecha sits beside Filtros where there is room; on phones it is the sheet's first group. */
export default function ActivityFilters(props: Props & { datePicker: ReactNode }) {
  const { isBelowDesktop: sheet, isBelowTablet: narrow } = useResponsiveLayout();
  const groups: readonly Group[] = narrow ? ["date", "people", "areas", "actions"] : ["people", "areas", "actions"];
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  useEffect(() => { if (wasOpen.current && !open) trigger.current?.focus(); wasOpen.current = open; }, [open]);
  const count = groups.filter(group => isActive(props.value, group)).length;
  const { words } = props;
  return <>
    {narrow ? null : props.datePicker}
    {sheet
      ? <><button ref={trigger} type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><ListFilter size={17} aria-hidden="true" /><span>{words.title}</span>{count ? <span className={styles.count}>{count}</span> : null}<ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>{open ? <FilterEditor {...props} groups={groups} phone close={() => setOpen(false)} /> : null}</>
      : <RecordsPreviewPopover label={words.title} icon={<ListFilter size={17} aria-hidden="true" />} count={count} preferredHeight={405}>{close => <FilterEditor {...props} groups={groups} close={close} />}</RecordsPreviewPopover>}
  </>;
}

/** Applied filters as removable chips; Fecha shows here only when it lives in the sheet. */
export function ActivityFilterChips({ value, onChange, options, words }: Props) {
  const { isBelowTablet: narrow } = useResponsiveLayout();
  const chips: { key: string; label: string; remove: () => void }[] = [
    ...(narrow && value.date !== "all" ? [{ key: "date", label: words.dates[value.date], remove: () => onChange({ ...value, date: "all" }) }] : []),
    ...(["people", "areas", "actions"] as const).flatMap(group => value[group].map(id => ({ key: `${group}:${id}`, label: options[group].find(option => option.value === id)?.label ?? id, remove: () => onChange({ ...value, [group]: value[group].filter(item => item !== id) }) }))),
  ];
  if (!chips.length) return null;
  return <div className={styles.chips} data-testid="activity-filter-chips">
    {chips.map(chip => <button type="button" key={chip.key} className={styles.chip} aria-label={words.remove(chip.label)} onClick={chip.remove}><span>{chip.label}</span><X size={14} aria-hidden="true" /></button>)}
    <button type="button" className={styles.clear} onClick={() => onChange({ ...EMPTY_ACTIVITY_FILTERS, date: narrow ? "all" : value.date })}>{words.clear}</button>
  </div>;
}
