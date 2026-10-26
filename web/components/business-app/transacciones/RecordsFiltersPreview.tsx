"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, Banknote, Building2, CheckCheck, FileText, Folder, ListFilter, Paperclip, ReceiptText, Users, X, type LucideIcon } from "lucide-react";
import BottomSheet from "@/components/ui/BottomSheet";
import MoneyInput from "@/components/money/MoneyInput";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { activeFilterGroups, emptyPreviewFilters, FILTER_GROUPS, validPreviewAmount, type FilterGroup, type PreviewFilters } from "./records-filter-preview-model";
import { useTransaccionesWords } from "./transacciones-words";
import type { RecordKind } from "./transacciones-model";
import styles from "./records-filter-preview.module.css";

export type ReportFilterCatalogues = { counterparties: { key: string; labels: string[] }[]; categories: string[]; funding_sources: { key: string; label: string | null; kind: string | null }[] };
type Kind = RecordKind | "all";
type EditorGroup = FilterGroup | "record";
const EDITOR_GROUPS: readonly EditorGroup[] = ["record", ...FILTER_GROUPS];
const ICONS: Record<EditorGroup, LucideIcon> = { record: FileText, review: CheckCheck, attachment: Paperclip, amount: Banknote, counterparty: Users, category: Folder, account: Building2, document: FileText, fiscal: ReceiptText };
const COUNTERPARTIES = ["Estación Ruta 3", "Nube Hosting", "Comedor Doña Ana"];
const CATEGORIES = ["none", "transport", "other", "dining"];
const ACCOUNTS = ["checking", "card", "owner"];
const toggle = (values: string[], value: string): string[] => values.includes(value) ? values.filter((item) => item !== value) : [...values, value];

function FilterEditor({ initial, initialKind, apply, close, phone = false, catalogues }: { catalogues?: ReportFilterCatalogues; phone?: boolean; initial: PreviewFilters; initialKind: Kind; apply: (next: PreviewFilters, kind: Kind) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [draft, setDraft] = useState(initial);
  const [draftKind, setDraftKind] = useState(initialKind);
  const [amountInvalid, setAmountInvalid] = useState({ min: false, max: false });
  const [amountReset, setAmountReset] = useState(0);
  const [group, setGroup] = useState<EditorGroup>("record");
  const [query, setQuery] = useState("");
  const [choosingGroup, setChoosingGroup] = useState(phone);
  const rail = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const navigated = useRef(false);
  useEffect(() => {
    if (!phone || !navigated.current) return;
    if (choosingGroup) rail.current?.querySelector<HTMLButtonElement>(`[data-group="${group}"]`)?.focus();
    else back.current?.focus();
  }, [phone, choosingGroup, group]);
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const groupLabel = (key: EditorGroup) => key === "record" ? word("record") : word(`groups.${key}`);
  const labelFor = (kind: FilterGroup, value: string): string => value === "unknown" ? t("business.transactions.unknown") : value === "no_comprobante" ? t("business.marks.sin_comprobante_chip") : value === "owner_funds" ? t("business.dossier.owner_funds") : kind === "counterparty" ? catalogues?.counterparties.find((option) => option.key === value)?.labels.join(" / ") ?? value : kind === "account" && catalogues ? catalogues.funding_sources.find((option) => option.key === value)?.label ?? value : kind === "category" && catalogues ? value === "uncategorized" ? word("category.none") : t(`business.category.${value}`, { defaultValue: value }) : kind === "review" ? t(`business.transactions.layout.overview.${value}.title`) : t(`business.transactions.layout.filters.${kind}.${value}`, { defaultValue: value.toUpperCase() });
  const selection = (kind: "review" | "counterparty" | "category" | "account" | "document" | "fiscal", values: string[]) => {
    const search = query.trim().toLocaleLowerCase();
    const visible = values.filter((value) => labelFor(kind, value).toLocaleLowerCase().includes(search));
    const selected: string[] = draft[kind];
    const selectedCount = visible.filter((value) => selected.includes(value)).length;
    const all = visible.length > 0 && selectedCount === visible.length;
    const mixed = selectedCount > 0 && !all;
    const chooseVisible = () => setDraft({ ...draft, [kind]: all ? selected.filter((value) => !visible.includes(value)) : [...new Set([...selected, ...visible])] });
    return <>
      <label className={`${styles.choice} ${styles.parentChoice}`}>
        <input type="checkbox" checked={all} disabled={visible.length === 0} aria-checked={mixed ? "mixed" : all} ref={(node) => { if (node) node.indeterminate = mixed; }} onChange={chooseVisible} />
        <span>{word(search ? "select_results" : "select_all")}</span>
      </label>
      {search ? <p className={styles.hint}>{word("visible_selection_hint")}</p> : null}
      <div className={styles.options}>{visible.map((value) => <label key={value} className={styles.choice}>
        <input type="checkbox" checked={selected.includes(value)} onChange={() => setDraft({ ...draft, [kind]: toggle(selected, value) })} />
        <span>{labelFor(kind, value)}</span>
      </label>)}</div>
      {visible.length === 0 ? <p className={styles.hint}>{word("no_matches")}</p> : null}
    </>;
  };
  const searchable = group === "counterparty" || group === "category" || group === "account";
  const body = <div className={phone ? styles.phonePanel : styles.panel}>
      {!phone || choosingGroup ? <div ref={rail} className={styles.rail} role={phone ? undefined : "tablist"} aria-label={word("title")} aria-orientation={phone ? undefined : "vertical"} onKeyDown={(event) => {
        if (phone) return;
        const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
        if (!step && event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? EDITOR_GROUPS.length - 1 : (EDITOR_GROUPS.indexOf(group) + step + EDITOR_GROUPS.length) % EDITOR_GROUPS.length;
        setGroup(EDITOR_GROUPS[next]); setQuery("");
        event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
      }}>
        {EDITOR_GROUPS.map((key) => { const Icon = ICONS[key]; return <button key={key} type="button" data-group={key} role={phone ? undefined : "tab"} tabIndex={phone || group === key ? 0 : -1} aria-selected={phone ? undefined : group === key} className={styles.group} onClick={() => { navigated.current = true; setGroup(key); setQuery(""); setChoosingGroup(false); }}><Icon size={17} aria-hidden="true" /><span>{groupLabel(key)}</span>{(key === "record" ? draftKind !== "all" : activeFilterGroups(draft).includes(key)) ? <span aria-hidden="true" className={styles.count}>•</span> : null}{phone ? <ChevronRight size={16} aria-hidden="true" /> : null}</button>; })}
      </div> : null}
      {!phone || !choosingGroup ? <section className={styles.editor} role={phone ? undefined : "tabpanel"} aria-label={groupLabel(group)}>
        {phone ? <button ref={back} type="button" className={styles.clear} onClick={() => setChoosingGroup(true)}><ArrowLeft size={18} aria-hidden="true" />{word("back")}</button> : null}
        <h3 className={styles.heading}>{groupLabel(group)}</h3>
        {searchable ? <input type="search" className={`${styles.input} ${styles.search}`} aria-label={word("search")} placeholder={word("search")} value={query} onChange={(event) => setQuery(event.target.value)} /> : null}
        {group === "record" ? <>{(["all", "gasto", "venta"] as const).map((kind) => <label key={kind} className={styles.choice}><input type="radio" name="preview-record-kind" checked={!(draft.recordFamilies && draft.recordFamilies.length > 1) && draftKind === kind} onChange={() => { setDraftKind(kind); setDraft({ ...draft, recordFamilies: undefined }); }} /><span>{kind === "all" ? t("business.transactions.layout.all_types") : t(`business.transactions.records.detail.${kind}`)}</span></label>)}</> : null}
        {group === "review" ? selection("review", ["review", "approval", "export"]) : null}
        {group === "attachment" ? <>{(["any", "with", "without"] as const).map((value) => <label key={value} className={styles.choice}><input type="radio" name="preview-attachment" checked={draft.attachment === value} onChange={() => setDraft({ ...draft, attachment: value })} /><span>{word(`attachment.${value}`)}</span></label>)}<p className={styles.hint}>{word("attachment.hint")}</p></> : null}
        {group === "amount" ? <>
          <p className={styles.hint}>{word("amount.currency")}</p>
          <div className={styles.currencies}>{(["DOP", "USD", "EUR"] as const).map((currency) => <button key={currency} type="button" className={styles.currency} aria-pressed={draft.currencies ? draft.currencies.includes(currency) : draft.amount.currency === currency} onClick={() => { if (draft.currencies) { const currencies = toggle(draft.currencies, currency); setDraft({ ...draft, currencies, amount: { ...draft.amount, currency: currencies.length === 1 ? currencies[0] : "" } }); } else setDraft({ ...draft, amount: { ...draft.amount, currency } }); }}>{currency}</button>)}</div>
          <div className={styles.fields}>{(["min", "max"] as const).map((key) => <label key={`${key}:${amountReset}`} className={styles.field}><span>{word(`amount.${key}`)}</span><MoneyInput label={word(`amount.${key}`)} currency={draft.amount.currency} allowZero disabled={!draft.amount.currency} value={draft.amount[key] || null} onValueChange={({ value, invalid }) => { setDraft((current) => ({ ...current, amount: { ...current.amount, [key]: value ?? "" } })); setAmountInvalid((current) => ({ ...current, [key]: invalid })); }} /></label>)}</div>
          {!draft.amount.currency ? <p className={styles.hint}>{word("amount.choose_currency")}</p> : null}
          {!validPreviewAmount(draft.amount, draft.currencies) ? <p role="alert" className={styles.error}>{word("amount.invalid")}</p> : null}
        </> : null}
        {group === "counterparty" ? selection("counterparty", catalogues ? catalogues.counterparties.map((option) => option.key) : COUNTERPARTIES) : null}
        {group === "category" ? selection("category", catalogues?.categories ?? CATEGORIES) : null}
        {group === "account" ? selection("account", catalogues ? catalogues.funding_sources.map((option) => option.key) : ACCOUNTS) : null}
        {group === "document" ? selection("document", ["invoice", "receipt", "credit_note"]) : null}
        {group === "fiscal" ? selection("fiscal", ["b01", "b02", "e31", "e32"]) : null}
      </section> : null}
    </div>;
  const footer = <div className={phone ? `${styles.footer} ${styles.phoneFooter}` : styles.footer}><button type="button" className={styles.clear} onClick={() => { setDraft(emptyPreviewFilters()); setDraftKind("all"); setAmountInvalid({ min: false, max: false }); setAmountReset((value) => value + 1); }}>{t("business.transactions.layout.clear")}</button><button type="button" className={styles.apply} disabled={amountInvalid.min || amountInvalid.max || !validPreviewAmount(draft.amount, draft.currencies)} onClick={() => { apply(draft, draftKind); close(); }}>{word("apply")}</button></div>;
  return phone ? <BottomSheet isOpen onClose={close} title={word("title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={footer}>{body}</BottomSheet> : <>{body}{footer}</>;
}

export default function RecordsFiltersPreview({ options, value: filters, kind, onChange, catalogues }: { catalogues?: ReportFilterCatalogues; options: ReactNode; value: PreviewFilters; kind: Kind; onChange: (next: PreviewFilters, kind: Kind) => void }) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  useEffect(() => { if (wasOpen.current && !open) trigger.current?.focus(); wasOpen.current = open; }, [open]);
  const setFilters = (next: PreviewFilters, nextKind: Kind = kind) => onChange(next, nextKind);
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const active = activeFilterGroups(filters);
  const recordActive = kind !== "all" || Boolean(filters.recordFamilies?.length);
  const recordLabel = filters.recordFamilies?.length === 2 ? filters.recordFamilies.map((family) => t(`business.transactions.records.detail.${family === "sale" ? "venta" : "gasto"}`)).join(" · ") : t(`business.transactions.records.detail.${kind}`);
  const chipLabel = (group: FilterGroup) => group === "amount" && !filters.amount.min && !filters.amount.max ? word("currency") : word(`groups.${group}`);
  const valueLabel = (group: FilterGroup) => {
    if (group === "attachment") return word(`attachment.${filters.attachment}`);
    if (group === "amount") return [(filters.currencies ?? [filters.amount.currency]).join(", "), filters.amount.min ? `${word("amount.min")} ${filters.amount.min}` : "", filters.amount.max ? `${word("amount.max")} ${filters.amount.max}` : ""].filter(Boolean).join(" · ");
    return filters[group].map((value) => value === "unknown" ? t("business.transactions.unknown") : value === "no_comprobante" ? t("business.marks.sin_comprobante_chip") : value === "owner_funds" ? t("business.dossier.owner_funds") : group === "counterparty" ? catalogues?.counterparties.find((option) => option.key === value)?.labels.join(" / ") ?? value : group === "account" && catalogues ? catalogues.funding_sources.find((option) => option.key === value)?.label ?? value : group === "category" && catalogues ? value === "uncategorized" ? word("category.none") : t(`business.category.${value}`, { defaultValue: value }) : group === "review" ? t(`business.transactions.layout.overview.${value}.title`) : t(`business.transactions.layout.filters.${group}.${value}`, { defaultValue: value.toUpperCase() })).join(", ");
  };
  return <>
    {phone ? <><button ref={trigger} type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><ListFilter size={17} aria-hidden="true" /><span>{word("title")}</span>{active.length || recordActive ? <span className={styles.count}>{active.length + (recordActive ? 1 : 0)}</span> : null}<ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>{open ? <FilterEditor catalogues={catalogues} phone initial={filters} initialKind={kind} apply={setFilters} close={() => setOpen(false)} /> : null}</> : <RecordsPreviewPopover label={word("title")} icon={<ListFilter size={17} aria-hidden="true" />} count={active.length + (recordActive ? 1 : 0)}>
      {(close) => <FilterEditor catalogues={catalogues} initial={filters} initialKind={kind} apply={setFilters} close={close} />}
    </RecordsPreviewPopover>}
    <div className={styles.toolbarOptions}>{options}</div>
    {active.length || recordActive ? <div className={styles.chips} data-testid="records-preview-filter-chips">{recordActive ? <button type="button" className={styles.chip} aria-label={word("remove") + " " + word("record")} onClick={() => setFilters({ ...filters, recordFamilies: [] }, "all")}><span>{word("record")} · {recordLabel}</span><X size={14} aria-hidden="true" /></button> : null}{active.map((group) => <button key={group} type="button" className={styles.chip} aria-label={word("remove") + " " + chipLabel(group)} onClick={() => setFilters({ ...filters, [group]: emptyPreviewFilters()[group], ...(group === "amount" && filters.currencies ? { currencies: [] } : {}) })}><span>{chipLabel(group)} · {valueLabel(group)}</span><X size={14} aria-hidden="true" /></button>)}<button type="button" className={styles.clear} onClick={() => setFilters(emptyPreviewFilters(), "all")}>{t("business.transactions.layout.clear")}</button></div> : null}
  </>;
}
