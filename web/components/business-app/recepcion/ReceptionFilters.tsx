"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCheck, ChevronDown, ChevronRight, Inbox, ListFilter, Users, X } from "lucide-react";
import { EnvelopeSimple, NotePencil, UploadSimple, WhatsappLogo } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import RecordsPreviewPopover from "../transacciones/RecordsPreviewPopover";
import RecordsFilterSelection from "../transacciones/RecordsFilterSelection";
import styles from "../transacciones/records-filter-preview.module.css";
import { emptyReceptionFilters, type ReceptionFiltersValue, type SenderIdentity } from "./reception-filters";

type Props = { senders: SenderIdentity[]; value: ReceptionFiltersValue; onChange: (value: ReceptionFiltersValue) => void };
const CHANNELS = [{ value: "whatsapp", icon: WhatsappLogo }, { value: "email", icon: EnvelopeSimple }, { value: "web", icon: UploadSimple }, { value: "note", icon: NotePencil }] as const;
const GROUPS = ["source", "sender", "status"] as const;

function FilterEditor({ senders, value, onChange, close, phone = false }: Props & { close: () => void; phone?: boolean }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const shared = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const [draft, setDraft] = useState(value);
  const [query, setQuery] = useState("");

  const [group, setGroup] = useState<typeof GROUPS[number]>("source");
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
    {!phone || choosing ? <div ref={rail} className={styles.rail} role={phone ? undefined : "tablist"} aria-label={shared("title")} aria-orientation={phone ? undefined : "vertical"} onKeyDown={event => {
      if (phone || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = event.key === "Home" ? 0 : event.key === "End" ? GROUPS.length - 1 : (GROUPS.indexOf(group) + (event.key === "ArrowDown" ? 1 : -1) + GROUPS.length) % GROUPS.length;
      setGroup(GROUPS[index]);
      event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[index]?.focus();
    }}>
      {GROUPS.map(key => { const Icon = key === "source" ? Inbox : key === "sender" ? Users : CheckCheck; const active = key === "source" ? draft.channels.length > 0 : key === "sender" ? draft.senders.length > 0 : draft.states.length > 0; return <button key={key} type="button" data-group={key} role={phone ? undefined : "tab"} tabIndex={phone || group === key ? 0 : -1} aria-selected={phone ? undefined : group === key} className={styles.group} onClick={() => { navigated.current = true; setGroup(key); setChoosing(false); }}><Icon size={17} aria-hidden="true" /><span>{word(key)}</span>{active ? <span className={styles.count} aria-hidden="true">•</span> : null}{phone ? <ChevronRight size={16} aria-hidden="true" /> : null}</button>; })}
    </div> : null}
    {!phone || !choosing ? <section className={styles.editor} role={phone ? undefined : "tabpanel"} aria-label={word(group)}>
      {phone ? <button ref={back} type="button" className={styles.clear} onClick={() => setChoosing(true)}><ArrowLeft size={18} aria-hidden="true" />{shared("back")}</button> : null}
      <div className="flex items-center justify-between gap-3"><h3 className={styles.heading}>{word(group)}</h3><button type="button" className={styles.clear} onClick={() => setDraft({ ...draft, [group === "source" ? "channels" : group === "sender" ? "senders" : "states"]: [] })}>{word("clear_group")}</button></div>
      {group === "source" ? <RecordsFilterSelection options={CHANNELS.map(({ value, icon: Icon }) => ({ value, label: word(`source_${value}`), icon: <Icon size={17} aria-hidden="true" /> }))} selected={draft.channels} onChange={channels => setDraft({ ...draft, channels })} /> : group === "status" ? <RecordsFilterSelection options={(["review", "processing", "attention"] as const).map(value => ({ value, label: word(value) }))} selected={draft.states} onChange={states => setDraft({ ...draft, states })} /> : <>
        <input type="search" className={`${styles.input} ${styles.search}`} aria-label={word("sender_search")} placeholder={word("sender_search")} value={query} onChange={event => setQuery(event.target.value)} />
        <RecordsFilterSelection options={senders.map(sender => ({ value: sender.id, label: sender.name || sender.address, description: sender.name ? sender.address : undefined }))} selected={draft.senders} query={query} keepSelectedVisible onChange={senders => setDraft({ ...draft, senders })} />
      </>}

    </section> : null}
  </div>;
  const footer = <div className={phone ? `${styles.footer} ${styles.phoneFooter}` : styles.footer}><button type="button" className={styles.clear} onClick={() => setDraft(emptyReceptionFilters())}>{word("clear")}</button><button type="button" className={styles.apply} onClick={() => { onChange(draft); close(); }}>{shared("apply")}</button></div>;
  return phone ? <BottomSheet isOpen onClose={close} title={shared("title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={footer}>{body}</BottomSheet> : <>{body}{footer}</>;
}

export default function ReceptionFilters(props: Props) {
  const { t } = useTranslation();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  useEffect(() => { if (wasOpen.current && !open) trigger.current?.focus(); wasOpen.current = open; }, [open]);
  const label = t("business.transactions.layout.filters.title");
  const count = Number(props.value.channels.length > 0) + Number(props.value.senders.length > 0) + Number(props.value.states.length > 0);
  return phone ? <><button ref={trigger} type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><ListFilter size={17} aria-hidden="true" /><span>{label}</span>{count ? <span className={styles.count}>{count}</span> : null}<ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>{open ? <FilterEditor {...props} phone close={() => setOpen(false)} /> : null}</> : <RecordsPreviewPopover label={label} icon={<ListFilter size={17} aria-hidden="true" />} count={count} preferredHeight={405}>{close => <FilterEditor {...props} close={close} />}</RecordsPreviewPopover>;
}

export function ReceptionFilterChips({ value, senders, onChange }: Props) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const groups = ["channels", "senders", "states"] as const;
  return <div className={styles.chips} data-testid="reception-filter-chips">{groups.flatMap(group => value[group].map(id => {
    const sender = senders.find(sender => sender.id === id);
    const label = group === "channels" ? word(`source_${id}`) : group === "states" ? word(id) : sender?.name || sender?.address || word("sender");
    return <button type="button" key={`${group}:${id}`} className={styles.chip} aria-label={t("business.reception_preview.remove_filter", { label })} onClick={() => onChange({ ...value, [group]: value[group].filter(item => item !== id) })}><span>{label}</span><X size={14} aria-hidden="true" /></button>;
  }))}{groups.some(group => value[group].length) ? <button type="button" className={styles.clear} onClick={() => onChange(emptyReceptionFilters())}>{word("clear")}</button> : null}</div>;
}
