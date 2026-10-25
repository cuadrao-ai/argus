"use client";

import { useState, type ReactNode } from "react";
import { Banknote, Building2, CheckCheck, FileText, Folder, ListFilter, Paperclip, ReceiptText, Users, X, type LucideIcon } from "lucide-react";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { activeFilterGroups, emptyPreviewFilters, FILTER_GROUPS, validPreviewAmount, type FilterGroup, type PreviewFilters, type ReviewFilter } from "./records-filter-preview-model";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

const ICONS: Record<FilterGroup, LucideIcon> = { review: CheckCheck, attachment: Paperclip, amount: Banknote, counterparty: Users, category: Folder, account: Building2, document: FileText, fiscal: ReceiptText };
const COUNTERPARTIES = ["Estación Ruta 3", "Nube Hosting", "Comedor Doña Ana"];
const CATEGORIES = ["none", "transport", "other", "dining"];
const ACCOUNTS = ["checking", "card", "owner"];
const toggle = (values: string[], value: string): string[] => values.includes(value) ? values.filter((item) => item !== value) : [...values, value];

function FilterEditor({ initial, apply, close }: { initial: PreviewFilters; apply: (next: PreviewFilters) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [draft, setDraft] = useState(initial);
  const [group, setGroup] = useState<FilterGroup>("review");
  const [query, setQuery] = useState("");
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const groupLabel = (key: FilterGroup) => word(`groups.${key}`);
  const labelFor = (kind: FilterGroup, value: string): string => kind === "counterparty" ? value : kind === "review" ? t(`business.transactions.layout.overview.${value}.title`) : word(`${kind}.${value}`);
  const selection = (kind: "review" | "counterparty" | "category" | "account" | "document" | "fiscal", values: string[]) => <div className={styles.options}>{values.filter((value) => labelFor(kind, value).toLocaleLowerCase().includes(query.toLocaleLowerCase())).map((value) => <label key={value} className={styles.choice}>
    <input type="checkbox" checked={draft[kind].includes(value as ReviewFilter)} onChange={() => setDraft({ ...draft, [kind]: toggle(draft[kind], value) })} />
    <span>{labelFor(kind, value)}</span>
  </label>)}</div>;
  const searchable = group === "counterparty" || group === "category" || group === "account";
  return <>
    <div className={styles.panel}>
      <div className={styles.rail} role="tablist" aria-label={word("title")} aria-orientation="vertical" onKeyDown={(event) => {
        const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
        if (!step && event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? FILTER_GROUPS.length - 1 : (FILTER_GROUPS.indexOf(group) + step + FILTER_GROUPS.length) % FILTER_GROUPS.length;
        setGroup(FILTER_GROUPS[next]); setQuery("");
        event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
      }}>
        {FILTER_GROUPS.map((key) => { const Icon = ICONS[key]; return <button key={key} type="button" role="tab" tabIndex={group === key ? 0 : -1} aria-selected={group === key} className={styles.group} onClick={() => { setGroup(key); setQuery(""); }}><Icon size={17} aria-hidden="true" /><span>{groupLabel(key)}</span>{activeFilterGroups(draft).includes(key) ? <span aria-hidden="true" className={styles.count}>•</span> : null}</button>; })}
      </div>
      <section className={styles.editor} role="tabpanel" aria-label={groupLabel(group)}>
        <h3 className={styles.heading}>{groupLabel(group)}</h3>
        {searchable ? <input type="search" className={`${styles.input} ${styles.search}`} aria-label={word("search")} placeholder={word("search")} value={query} onChange={(event) => setQuery(event.target.value)} /> : null}
        {group === "review" ? selection("review", ["review", "approval", "export"]) : null}
        {group === "attachment" ? <>{(["any", "with", "without"] as const).map((value) => <label key={value} className={styles.choice}><input type="radio" name="preview-attachment" checked={draft.attachment === value} onChange={() => setDraft({ ...draft, attachment: value })} /><span>{word(`attachment.${value}`)}</span></label>)}<p className={styles.hint}>{word("attachment.hint")}</p></> : null}
        {group === "amount" ? <>
          <p className={styles.hint}>{word("amount.currency")}</p>
          <div className={styles.currencies}>{(["DOP", "USD", "EUR"] as const).map((currency) => <button key={currency} type="button" className={styles.currency} aria-pressed={draft.amount.currency === currency} onClick={() => setDraft({ ...draft, amount: { ...draft.amount, currency } })}>{currency}</button>)}</div>
          <div className={styles.fields}>{(["min", "max"] as const).map((key) => <label key={key} className={styles.field}><span>{word(`amount.${key}`)}</span><input type="text" inputMode="decimal" disabled={!draft.amount.currency} className={styles.input} value={draft.amount[key]} placeholder="0.00" onChange={(event) => setDraft({ ...draft, amount: { ...draft.amount, [key]: event.target.value } })} /></label>)}</div>
          {!draft.amount.currency ? <p className={styles.hint}>{word("amount.choose_currency")}</p> : null}
          {!validPreviewAmount(draft.amount) ? <p role="alert" className={styles.error}>{word("amount.invalid")}</p> : null}
        </> : null}
        {group === "counterparty" ? selection("counterparty", COUNTERPARTIES) : null}
        {group === "category" ? selection("category", CATEGORIES) : null}
        {group === "account" ? selection("account", ACCOUNTS) : null}
        {group === "document" ? selection("document", ["invoice", "receipt", "credit_note"]) : null}
        {group === "fiscal" ? selection("fiscal", ["b01", "b02", "e31", "e32"]) : null}
      </section>
    </div>
    <div className={styles.footer}><button type="button" className={styles.clear} onClick={() => setDraft(emptyPreviewFilters())}>{t("business.transactions.layout.clear")}</button><button type="button" className={styles.apply} disabled={!validPreviewAmount(draft.amount)} onClick={() => { apply(draft); close(); }}>{word("apply")}</button></div>
  </>;
}

export default function RecordsFiltersPreview({ options, value, onChange }: { options: ReactNode; value?: PreviewFilters; onChange?: (next: PreviewFilters) => void }) {
  const { t } = useTransaccionesWords();
  const [localFilters, setLocalFilters] = useState<PreviewFilters>(emptyPreviewFilters);
  const filters = value ?? localFilters;
  const setFilters = (next: PreviewFilters) => { if (onChange) onChange(next); else setLocalFilters(next); };
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const active = activeFilterGroups(filters);
  const valueLabel = (group: FilterGroup) => {
    if (group === "attachment") return word(`attachment.${filters.attachment}`);
    if (group === "amount") return [filters.amount.currency, filters.amount.min ? `${word("amount.min")} ${filters.amount.min}` : "", filters.amount.max ? `${word("amount.max")} ${filters.amount.max}` : ""].filter(Boolean).join(" · ");
    return filters[group].map((value) => group === "counterparty" ? value : group === "review" ? t(`business.transactions.layout.overview.${value}.title`) : word(`${group}.${value}`)).join(", ");
  };
  return <>
    <RecordsPreviewPopover label={word("title")} icon={<ListFilter size={17} aria-hidden="true" />} count={active.length}>
      {(close) => <FilterEditor initial={filters} apply={setFilters} close={close} />}
    </RecordsPreviewPopover>
    <div className={styles.toolbarOptions}>{options}</div>
    {active.length ? <div className={styles.chips} data-testid="records-preview-filter-chips">{active.map((group) => <button key={group} type="button" className={styles.chip} aria-label={word("remove") + " " + word(`groups.${group}`)} onClick={() => setFilters({ ...filters, [group]: emptyPreviewFilters()[group] })}><span>{word(`groups.${group}`)} · {valueLabel(group)}</span><X size={14} aria-hidden="true" /></button>)}<button type="button" className={styles.clear} onClick={() => setFilters(emptyPreviewFilters())}>{t("business.transactions.layout.clear")}</button></div> : null}
  </>;
}
