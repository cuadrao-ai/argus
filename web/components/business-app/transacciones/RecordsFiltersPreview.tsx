"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, Banknote, Building2, CheckCheck, FileText, ListFilter, Paperclip, ReceiptText, Tag, Users, X, type LucideIcon } from "lucide-react";
import { createPortal } from "react-dom";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import BottomSheet from "@/components/ui/BottomSheet";
import MoneyInput from "@/components/money/MoneyInput";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import RecordsFilterSelection from "./RecordsFilterSelection";
import { activeFilterGroups, emptyPreviewFilters, FILTER_GROUPS, validPreviewAmount, type FilterGroup, type PreviewFilters } from "./records-filter-preview-model";
import { SAMPLE_EXPENSE_TYPES } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import { REPORT_DOCUMENT_KINDS, type DgiiChoice } from "@/lib/business-reports-api";
import styles from "./records-filter-preview.module.css";

export type ReportFilterCatalogues = { counterparties: { key: string; labels: string[] }[]; expense_types: DgiiChoice[]; funding_sources: { key: string; label: string | null; kind: string | null }[] };
const ICONS: Record<FilterGroup, LucideIcon> = { fiscal_data: CheckCheck, review: CheckCheck, attachment: Paperclip, amount: Banknote, counterparty: Users, expense_type: Tag, account: Building2, document: FileText, fiscal: ReceiptText };
const COUNTERPARTIES = ["Estación Ruta 3", "Nube Hosting", "Comedor Doña Ana"];
const ACCOUNTS = ["checking", "card", "owner"];
/** The tipo de gasto choices: every type the records carry, then `missing` for a purchase that still needs one. */
const expenseTypeValues = (types: readonly DgiiChoice[]) => [...types.map((choice) => choice.code), "missing"];

function FilterEditor({ initial, apply, close, phone = false, catalogues, purchase, initialGroup = "fiscal_data" }: { purchase: boolean; initialGroup?: FilterGroup | "filters"; catalogues?: ReportFilterCatalogues; phone?: boolean; initial: PreviewFilters; apply: (next: PreviewFilters) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [draft, setDraft] = useState(initial);
  const [amountInvalid, setAmountInvalid] = useState({ min: false, max: false });
  const [amountReset, setAmountReset] = useState(0);
  const [group, setGroup] = useState<FilterGroup>(initialGroup === "filters" ? "fiscal_data" : initialGroup);
  const groups = FILTER_GROUPS.filter((key) => key !== "review" && (purchase || key !== "expense_type"));
  const [query, setQuery] = useState("");
  const [choosingGroup, setChoosingGroup] = useState(phone && initialGroup === "filters");
  const rail = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const navigated = useRef(false);
  useEffect(() => {
    if (!phone || !navigated.current) return;
    if (choosingGroup) rail.current?.querySelector<HTMLButtonElement>(`[data-group="${group}"]`)?.focus();
    else back.current?.focus();
  }, [phone, choosingGroup, group]);
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const groupLabel = (key: FilterGroup) => key === "expense_type" ? t("business.dossier.placeholder.expense_type") : word(`groups.${key}`);
  const expenseTypes = catalogues?.expense_types ?? SAMPLE_EXPENSE_TYPES;
  const labelFor = (kind: FilterGroup, value: string): string => value === "unknown" ? t("business.transactions.unknown") : value === "no_comprobante" ? t("business.marks.sin_comprobante_chip") : value === "owner_funds" ? t("business.dossier.owner_funds") : kind === "counterparty" ? catalogues?.counterparties.find((option) => option.key === value)?.labels[0] ?? value : kind === "account" && catalogues ? catalogues.funding_sources.find((option) => option.key === value)?.label ?? value : kind === "expense_type" ? value === "missing" ? t("business.dossier.standing.missing") : expenseTypes.find((choice) => choice.code === value)?.label ?? value : kind === "review" ? t(`business.transactions.layout.overview.${value}.title`) : t(`business.transactions.layout.filters.${kind}.${value}`, { defaultValue: value.toUpperCase() });
  const selection = (kind: "review" | "counterparty" | "expense_type" | "account" | "document" | "fiscal", values: string[]) => <RecordsFilterSelection options={values.map((value) => ({ value, label: labelFor(kind, value) }))} selected={draft[kind]} query={query} onChange={(selected) => setDraft({ ...draft, [kind]: selected })} />;
  const searchable = group === "counterparty" || group === "expense_type" || group === "account";
  const body = <div className={phone ? styles.phonePanel : styles.panel}>
      {!phone || choosingGroup ? <div ref={rail} className={styles.rail} role={phone ? undefined : "tablist"} aria-label={word("title")} aria-orientation={phone ? undefined : "vertical"} onKeyDown={(event) => {
        if (phone) return;
        const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
        if (!step && event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? groups.length - 1 : (groups.indexOf(group) + step + groups.length) % groups.length;
        setGroup(groups[next]); setQuery("");
        event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
      }}>
        {groups.map((key) => { const Icon = ICONS[key]; return <button key={key} type="button" data-group={key} role={phone ? undefined : "tab"} tabIndex={phone || group === key ? 0 : -1} aria-selected={phone ? undefined : group === key} className={styles.group} onClick={() => { navigated.current = true; setGroup(key); setQuery(""); setChoosingGroup(false); }}><Icon size={17} aria-hidden="true" /><span>{groupLabel(key)}</span>{activeFilterGroups(draft).includes(key) ? <span aria-hidden="true" className={styles.count}>•</span> : null}{phone ? <ChevronRight size={16} aria-hidden="true" /> : null}</button>; })}
      </div> : null}
      {!phone || !choosingGroup ? <section className={styles.editor} role={phone ? undefined : "tabpanel"} aria-label={groupLabel(group)}>
        {phone ? <button ref={back} type="button" className={styles.clear} onClick={() => setChoosingGroup(true)}><ArrowLeft size={18} aria-hidden="true" />{word("back")}</button> : null}
        <h3 className={styles.heading}>{groupLabel(group)}</h3>
        {searchable ? <input type="search" className={`${styles.input} ${styles.search}`} aria-label={word("search")} placeholder={word("search")} value={query} onChange={(event) => setQuery(event.target.value)} /> : null}
        {group === "fiscal_data" ? ([null, "complete", "missing"] as const).map((value) => <label key={value ?? "all"} className={styles.choice}><input type="radio" name="fiscal-data" checked={draft.fiscal_data === value && draft.review.length === 0} onChange={() => setDraft({ ...draft, fiscal_data: value, review: [] })} /><span>{word(`fiscal_data.${value ?? "all"}`)}</span></label>) : null}
        {group === "attachment" ? <>{(["any", "with", "without"] as const).map((value) => <label key={value} className={styles.choice}><input type="radio" name="preview-attachment" checked={draft.attachment === value} onChange={() => setDraft({ ...draft, attachment: value })} /><span>{word(`attachment.${value}`)}</span></label>)}<p className={styles.hint}>{word("attachment.hint")}</p></> : null}
        {group === "amount" ? <>
          <div className={styles.fields}>{(["min", "max"] as const).map((key) => <label key={`${key}:${amountReset}`} className={styles.field}><span>{word(`amount.${key}`)}</span><MoneyInput label={word(`amount.${key}`)} currency={draft.amount.currency} allowZero value={draft.amount[key] || null} onValueChange={({ value, invalid }) => { setDraft((current) => ({ ...current, amount: { ...current.amount, [key]: value ?? "" } })); setAmountInvalid((current) => ({ ...current, [key]: invalid })); }} /></label>)}</div>
          {!validPreviewAmount(draft.amount) ? <p role="alert" className={styles.error}>{word("amount.invalid")}</p> : null}
        </> : null}
        {group === "counterparty" ? selection("counterparty", catalogues ? catalogues.counterparties.map((option) => option.key) : COUNTERPARTIES) : null}
        {group === "expense_type" ? selection("expense_type", expenseTypeValues(expenseTypes)) : null}
        {group === "account" ? selection("account", catalogues ? catalogues.funding_sources.map((option) => option.key) : ACCOUNTS) : null}
        {group === "document" ? selection("document", [...REPORT_DOCUMENT_KINDS]) : null}
        {group === "fiscal" ? selection("fiscal", ["b01", "b02", "e31", "e32"]) : null}
      </section> : null}
    </div>;
  const footer = <div className={phone ? `${styles.footer} ${styles.phoneFooter}` : styles.footer}><button type="button" className={styles.clear} disabled={activeFilterGroups(draft).length === 0 && !amountInvalid.min && !amountInvalid.max} onClick={() => { setDraft(emptyPreviewFilters(draft.amount.currency)); setAmountInvalid({ min: false, max: false }); setAmountReset((value) => value + 1); }}>{t("business.transactions.layout.clear")}</button><button type="button" className={styles.apply} disabled={amountInvalid.min || amountInvalid.max || !validPreviewAmount(draft.amount)} onClick={() => { const keys = catalogues ? catalogues.counterparties.map((option) => option.key) : COUNTERPARTIES; apply({ ...draft, counterparty: keys.length > 0 && keys.every((key) => draft.counterparty.includes(key)) ? [] : draft.counterparty }); close(); }}>{word("apply")}</button></div>;
  return phone ? <BottomSheet isOpen onClose={close} title={word("title")} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen footer={footer}>{body}</BottomSheet> : <>{body}{footer}</>;
}

export default function RecordsFiltersPreview({ options, value: filters, onChange, catalogues, purchase = true }: { purchase?: boolean; catalogues?: ReportFilterCatalogues; options: ReactNode; value: PreviewFilters; onChange: (next: PreviewFilters) => void }) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const [editor, setEditor] = useState<"amount" | "filters" | null>(null);
  const open = editor !== null;
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const [position, setPosition] = useState({ left: 16, top: 100, width: 660, maxHeight: 500 });
  const close = () => setEditor(null);
  const place = useCallback(() => {
    const rect = opener.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(660, window.innerWidth - 32);
    const top = Math.min(rect.bottom + 8, Math.max(16, window.innerHeight - 336));
    setPosition({ left: Math.max(16, Math.min(rect.left, window.innerWidth - width - 16)), top, width, maxHeight: window.innerHeight - top - 16 });
  }, []);
  const openEditor = (button: HTMLButtonElement, group: "amount" | "filters") => {
    if (editor === group && opener.current === button) { close(); return; }
    opener.current = button; place(); setEditor(group);
  };
  const id = useId();
  useEffect(() => {
    if (!open || phone) return;
    panel.current?.querySelector<HTMLElement>("button, input")?.focus();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, phone, place]);
  useOverlayLayer({ isOpen: open && !phone, overlayId: id, containerRef: panel, onEscape: close, onOutsidePointerDown: (event) => { if (!opener.current?.contains(event.target as Node)) close(); } });
  const wasOpen = useRef(false);
  useEffect(() => { if (wasOpen.current && !open) opener.current?.focus(); wasOpen.current = open; }, [open]);
  const setFilters = onChange;
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const active = activeFilterGroups(filters);
  const canClear = active.length > 0;
  const chipLabel = (group: FilterGroup) => group === "expense_type" ? t("business.dossier.placeholder.expense_type") : word(`groups.${group}`);
  const expenseTypes = catalogues?.expense_types ?? SAMPLE_EXPENSE_TYPES;
  const valueLabel = (group: FilterGroup) => {
    if (group === "fiscal_data") return word(`fiscal_data.${filters.fiscal_data}`);
    if (group === "counterparty") return String(filters.counterparty.length);
    if (group === "attachment") return word(`attachment.${filters.attachment}`);
    if (group === "amount") return [filters.amount.currency, filters.amount.min ? `${word("amount.min")} ${filters.amount.min}` : "", filters.amount.max ? `${word("amount.max")} ${filters.amount.max}` : ""].filter(Boolean).join(" · ");
    return filters[group].map((value) => value === "unknown" ? t("business.transactions.unknown") : value === "no_comprobante" ? t("business.marks.sin_comprobante_chip") : value === "owner_funds" ? t("business.dossier.owner_funds") : group === "account" && catalogues ? catalogues.funding_sources.find((option) => option.key === value)?.label ?? value : group === "expense_type" ? value === "missing" ? t("business.dossier.standing.missing") : expenseTypes.find((choice) => choice.code === value)?.label ?? value : group === "review" ? t(`business.transactions.layout.overview.${value}.title`) : t(`business.transactions.layout.filters.${group}.${value}`, { defaultValue: value.toUpperCase() })).join(", ");
  };
  return <>
    <button type="button" className={styles.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={(event) => openEditor(event.currentTarget, "filters")}><ListFilter size={17} aria-hidden="true" /><span>{word("title")}</span>{active.length > 0 ? <span className={styles.count}>{active.length}</span> : null}<ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} /></button>
    {editor !== null ? phone ? <FilterEditor purchase={purchase} key={editor} catalogues={catalogues} phone initialGroup={editor} initial={filters} apply={setFilters} close={close} /> : createPortal(<div ref={panel} role="dialog" aria-label={word("title")} className={styles.popover} style={position}><FilterEditor purchase={purchase} key={editor} catalogues={catalogues} initialGroup={editor} initial={filters} apply={setFilters} close={close} /></div>, document.body) : null}
    <div className={styles.toolbarOptions}>{options}</div>
    <div className={styles.chips} data-testid="records-preview-filter-chips">{active.map((group) => <button key={group} type="button" className={styles.chip} aria-label={group === "amount" ? undefined : word("remove") + " " + chipLabel(group)} aria-haspopup={group === "amount" ? "dialog" : undefined} onClick={(event) => group === "amount" ? openEditor(event.currentTarget, "amount") : setFilters({ ...filters, [group]: emptyPreviewFilters(filters.amount.currency)[group] })}><span>{group === "counterparty" ? t("business.transactions.layout.filters.counterparty_short", { count: filters.counterparty.length }) : `${chipLabel(group)} · ${valueLabel(group)}`}</span>{group !== "amount" ? <X size={14} aria-hidden="true" /> : null}</button>)}{canClear ? <button type="button" className={styles.clear} onClick={() => setFilters(emptyPreviewFilters(filters.amount.currency))}>{t("business.transactions.layout.clear")}</button> : null}</div>
  </>;
}
