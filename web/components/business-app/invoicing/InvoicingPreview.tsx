"use client";

import { useEffect, useReducer, useRef, useState, useSyncExternalStore } from "react";
import { ArrowDown, Check, ChevronLeft, ChevronRight, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import { currencySymbol } from "@/lib/money-entry";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness } from "../BusinessWorkspace";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { periodRange, todayIso, type Period } from "../business-format";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import RecordsDatePreview from "../transacciones/RecordsDatePreview";
import { pageLinks } from "../transacciones/records-pagination";
import { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import InvoiceEditor from "./InvoiceEditor";
import InvoiceDossier from "./InvoiceDossier";
import { CURRENCIES, invoiceSettlement, invoicePreviewSeed, invoiceReducer, invoiceState, matchesInvoice, newInvoice, validDraft, type InvoiceCurrency, type InvoiceFilter, type InvoicePreview } from "./invoice-preview-model";
import CustomersView from "./CustomersView";
import CustomerDossier from "./CustomerDossier";
import { customerReducer, seedCustomers, type BusinessCustomer } from "./customer-preview-model";
import InvoiceStageTabs from "./InvoiceStageTabs";
import InvoiceResultsSummary from "./InvoiceResultsSummary";
import { summarizeInvoiceResults } from "./invoice-results-summary";
import WorkspaceEmptyState, { invoiceEmptyKind } from "./WorkspaceEmptyState";
import SchedulesView from "./SchedulesView";
import ScheduleDossier from "./ScheduleDossier";
import { scheduleReducer, type InvoiceSchedule } from "./schedule-preview-model";
import styles from "./invoicing-preview.module.css";

const sessionInvoices = new Map<string, { invoices: InvoicePreview[]; customers: BusinessCustomer[]; schedules: InvoiceSchedule[] }>();
const subscribeLocation = (notify: () => void) => { window.addEventListener("popstate", notify); return () => window.removeEventListener("popstate", notify); };
const locationSnapshot = () => new URLSearchParams(window.location.search).get("invoicePreview") ?? "";
const serverLocation = () => "";

export default function InvoicingPreview() {
  const { chosen } = useBusiness();
  const variant = useSyncExternalStore(subscribeLocation, locationSnapshot, serverLocation);
  const scope = `${chosen?.space_id ?? "own"}:${variant}`;
  return <InvoiceWorkspace key={scope} scope={scope} variant={variant} business={chosen?.name ?? ""} />;
}

function InvoiceWorkspace({ scope, business, variant }: { scope: string; business: string; variant: string }) {
  const { word, locale } = useInvoiceWords();
  const { openPanel } = useBusiness();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const [invoices, dispatch] = useReducer(invoiceReducer, scope, key => sessionInvoices.get(key)?.invoices ?? invoicePreviewSeed(variant, word("fixture_correction_reason")).map(invoice => ({ ...invoice, items: invoice.items.map(item => ({ ...item, description: word("sample_item") })) })));
  const [customers, dispatchCustomer] = useReducer(customerReducer, scope, key => sessionInvoices.get(key)?.customers ?? seedCustomers(invoices));
  const [schedules, dispatchSchedule] = useReducer(scheduleReducer, scope, key => sessionInvoices.get(key)?.schedules ?? []);
  const [section, setSection] = useState<"invoices" | "customers" | "schedules">("invoices");
  const [schedulePanel, setSchedulePanel] = useState<{ id: string } | { draft: InvoiceSchedule } | null>(null);
  const [customerPanel, setCustomerPanel] = useState<{ id: string } | { draft: BusinessCustomer } | null>(null);
  const [editing, setEditing] = useState<InvoicePreview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<InvoiceFilter>("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [currency, setCurrency] = useState<InvoiceCurrency | "all">("all");
  const [period, setPeriod] = useState<Period>(() => periodRange("all"));
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(25);
  const [density, setDensity] = useState<"compact" | "normal" | "comfortable">("normal");
  const [sort, setSort] = useState<"newest" | "oldest" | "customer">("newest");
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => { sessionInvoices.set(scope, { invoices, customers, schedules }); }, [scope, invoices, customers, schedules]);
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && section === "invoices" && !editing && !selectedId && !customerPanel) { event.preventDefault(); event.stopImmediatePropagation(); search.current?.focus(); }
    };
    window.addEventListener("keydown", focusSearch, true);
    return () => window.removeEventListener("keydown", focusSearch, true);
  }, [editing, selectedId, section, customerPanel]);
  const choose = (value: InvoiceFilter) => { setFilter(value); setOverdueOnly(false); setPage(1); };
  const inPeriod = invoices.filter(invoice => period.key === "all" || (invoice.issuedOn >= period.from && (!period.to || invoice.issuedOn <= period.to)));
  const normalize = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase(locale);
  const results = inPeriod.filter(invoice => matchesInvoice(invoice, overdueOnly && filter === "outstanding" ? "overdue" : filter) && (currency === "all" || invoice.currency === currency) && normalize(`${invoice.reference} ${invoice.customer.name} ${invoice.notes}`).includes(normalize(query))).sort((a, b) => sort === "customer" ? a.customer.name.localeCompare(b.customer.name, locale) || a.id.localeCompare(b.id) : (sort === "newest" ? b.issuedOn.localeCompare(a.issuedOn) : a.issuedOn.localeCompare(b.issuedOn)) || a.id.localeCompare(b.id));
  const pages = Math.max(1, Math.ceil(results.length / size));
  const shownPage = Math.min(page, pages);
  const rows = results.slice((shownPage - 1) * size, shownPage * size);
  const emptyKind = invoiceEmptyKind(invoices.length, invoices.filter(invoice => matchesInvoice(invoice, filter)).length, results.length);
  const summary = summarizeInvoiceResults(results, currency, filter);
  const selected = invoices.find(invoice => invoice.id === selectedId);
  const customerSelected = customerPanel && ("draft" in customerPanel ? customerPanel.draft : customers.find(customer => customer.id === customerPanel.id));
  const scheduleSelected = schedulePanel && ("draft" in schedulePanel ? schedulePanel.draft : schedules.find(schedule => schedule.id === schedulePanel.id));
  const addCustomer = () => { setSelectedId(null); setCustomerPanel({ draft: { id: crypto.randomUUID(), name: "", email: "", address: "", taxId: "", status: "active" } }); };
  const create = () => { setCustomerPanel(null); setSelectedId(null); setEditing(newInvoice(crypto.randomUUID(), `M-${String(invoices.length + 1).padStart(3, "0")}`)); };
  const createSchedule = () => {
    const template = invoices.find(invoice => invoice.issuance === "draft" && validDraft(invoice) && customers.some(customer => customer.id === invoice.customer.id && customer.status === "active")) ?? newInvoice(crypto.randomUUID(), "");
    setSchedulePanel({ draft: { id: crypto.randomUUID(), name: "", customerId: template.customer.id, template: structuredClone(template), frequency: "monthly", anchorDate: todayIso(), status: "active", mode: "draft" } });
  };
  return <section className={styles.workspace} data-testid="invoicing-preview">
    {phone ? <h2 className="mb-5 font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{word("title")}</h2> : null}
    <div className={styles.workspaceSwitch}><SegmentedControl label={word("title")} value={section} disabled={!!editing || !!customerPanel || !!schedulePanel} onChange={value => { setSelectedId(null); setSection(value); }} segments={[{ key: "invoices", label: word("invoices_tab") }, { key: "customers", label: word("customers_tab") }, { key: "schedules", label: word("schedules_tab") }]} /></div>
    {section === "schedules" ? <SchedulesView panelOpen={!!schedulePanel} schedules={schedules} customers={customers} onCreate={createSchedule} onSelect={id => setSchedulePanel({ id })} onStatus={(id, status) => dispatchSchedule({ type: "status", id, status })} /> : section === "customers" ? <CustomersView customers={customers} invoices={invoices} schedules={schedules} panelOpen={!!customerPanel || !!selectedId || !!editing} onAdd={addCustomer} onSelect={id => { setSelectedId(null); setCustomerPanel({ id }); }} /> : <>
    <InvoiceStageTabs value={filter} invoices={inPeriod} onChange={choose} />
    <div role="tabpanel" id="invoice-stage-results" aria-labelledby={`invoice-stage-${filter}`} tabIndex={0}>
    {invoices.length ? <>
    <InvoiceResultsSummary key={summary.currencies.map(group => group.currency).join(",")} currencies={summary.currencies} />
    <div className={styles.toolbar}>
      <label className={styles.search}><Search size={17} aria-hidden="true" /><input ref={search} type="search" value={query} placeholder={word("search")} aria-label={word("search")} onChange={event => { setQuery(event.target.value); setPage(1); }} /></label>
      <RecordsDatePreview period={period} value={period} onChange={value => { setPeriod(value); setPage(1); }} />
      <ToolbarPicker label={word("filters")} value={word("filters")}>{close => <><p className={styles.pickerLabel}>{word("currency")}</p>{(["all", ...CURRENCIES] as const).map(value => <button key={value} className={styles.option} onClick={() => { setCurrency(value); setPage(1); close(); }}>{value === "all" ? word("all_currencies") : value}{currency === value ? <Check size={16} /> : null}</button>)}</>}</ToolbarPicker>
      <button className={`${primaryButtonClass} ${styles.create}`} aria-label={word("create")} onClick={create}><Plus size={18} /><span>{word("create")}</span></button>
      <ToolbarPicker label={word("settings")} value={word("settings")} icon={<SlidersHorizontal size={16} />} flip wide>{() => <div className={styles.settings}><p>{word("row_height")}</p><SegmentedControl label={word("row_height")} value={density} onChange={setDensity} fill segments={(["compact", "normal", "comfortable"] as const).map(key => ({ key, label: word(key) }))} /><p>{word("sort")}</p><SegmentedControl label={word("sort")} value={sort} onChange={value => { setSort(value); setPage(1); }} fill segments={(["newest", "oldest", "customer"] as const).map(key => ({ key, label: word(key) }))} /></div>}</ToolbarPicker>
    </div>
    {filter === "outstanding" ? <div className={styles.chips}><button aria-pressed={overdueOnly} onClick={() => { setOverdueOnly(!overdueOnly); setPage(1); }}>{word("overdue")} <span>{inPeriod.filter(invoice => matchesInvoice(invoice, "overdue")).length}</span>{overdueOnly ? <X size={14} aria-hidden="true" /> : null}</button></div> : null}
    {currency !== "all" ? <div className={styles.chips}><button onClick={() => { setCurrency("all"); setPage(1); }}>{currency}<X size={14} aria-label={word("clear")} /></button></div> : null}
    <div className={styles.tableFrame} data-density={density}>
      <table className={styles.table}><thead><tr><th>{word("invoice")}</th><th><button onClick={() => { setSort("customer"); setPage(1); }}>{word("customer")}{sort === "customer" ? <ArrowDown size={13} /> : null}</button></th><th><button onClick={() => { setSort(sort === "newest" ? "oldest" : "newest"); setPage(1); }}>{word("issue_date")}{sort !== "customer" ? <ArrowDown size={13} className={sort === "oldest" ? "rotate-180" : ""} /> : null}</button></th><th>{word("due_date")}</th><th>{word("currency")}</th><th className={styles.numeric}>{word("document_total")}</th><th className={styles.numeric}>{word("balance")}</th><th>{word("status")}</th></tr></thead><tbody>{rows.map(invoice => { const amount = invoiceSettlement(invoice); return <tr key={invoice.id} data-selected={selectedId === invoice.id} onClick={() => setSelectedId(invoice.id)}><td><button className={styles.rowLink} onClick={() => setSelectedId(invoice.id)}>{invoice.reference}</button></td><td title={invoice.customer.name}>{invoice.customer.name}</td><td><InvoiceDate date={invoice.issuedOn} /></td><td><InvoiceDate date={invoice.dueOn} /></td><td>{currencySymbol(invoice.currency)}</td><td className={styles.numeric}>{amount ? <InvoiceMoney numberOnly amount={amount.total} currency={invoice.currency} /> : "-"}</td><td className={styles.numeric}>{invoice.issuance === "issued" && amount ? <InvoiceMoney numberOnly amount={amount.balance} currency={invoice.currency} /> : "-"}</td><td><span className={styles.badge} data-state={invoiceState(invoice)}>{word(`state_${invoiceState(invoice)}`)}</span></td></tr>; })}</tbody></table>
      <div className={styles.phoneList}>{rows.map(invoice => { const amount = invoiceSettlement(invoice); return <button key={invoice.id} onClick={() => setSelectedId(invoice.id)}><strong>{invoice.customer.name}</strong><span>{amount ? <InvoiceMoney amount={amount.total} currency={invoice.currency} /> : "-"}</span><span><span className={styles.badge} data-state={invoiceState(invoice)}>{word(`state_${invoiceState(invoice)}`)}</span></span><small>{word("due_short")} <InvoiceDate date={invoice.dueOn} /></small></button>; })}</div>
      {!rows.length ? <WorkspaceEmptyState compact art="invoice" title={word(emptyKind === "stage" ? `empty_stage_${filter}` : "no_results")} description={word(emptyKind === "stage" ? `empty_stage_${filter}_help` : "no_results_help")} action={emptyKind === "filtered" ? <button className={quietButtonClass} onClick={() => { setQuery(""); setCurrency("all"); setOverdueOnly(false); setPage(1); setPeriod(periodRange("all")); }}>{word("clear_filters")}</button> : undefined} /> : null}
      <footer className={styles.pagination}><span>{word("result_count", { from: results.length ? (shownPage - 1) * size + 1 : 0, to: Math.min(shownPage * size, results.length), count: results.length })}</span><ToolbarPicker label={word("page_size")} value={String(size)}>{close => [25, 50, 100].map(value => <button className={styles.option} key={value} onClick={() => { setSize(value); setPage(1); close(); }}>{value}</button>)}</ToolbarPicker><nav aria-label={word("pages")}><button aria-label={word("previous")} disabled={shownPage === 1} onClick={() => setPage(shownPage - 1)}><ChevronLeft size={17} /></button>{pageLinks(shownPage, pages).map((value, index) => value === "gap" ? <span key={`gap${index}`}>…</span> : <button key={value} aria-current={shownPage === value ? "page" : undefined} onClick={() => setPage(value)}>{value}</button>)}<button aria-label={word("next")} disabled={shownPage === pages} onClick={() => setPage(shownPage + 1)}><ChevronRight size={17} /></button></nav></footer>
    </div>
    </> : <WorkspaceEmptyState title={word("first_invoice")} description={word("first_invoice_help")} action={<button className={primaryButtonClass} onClick={create}><Plus size={18} />{word("create")}</button>} />}
    </div>
    <div className={styles.readiness}><span>{word("readiness_unknown")}</span><button className={quietButtonClass} onClick={() => openPanel({ kind: "business", tab: "datos" })}>{word("readiness_settings")}</button></div>
    </>}
    {customerSelected ? <CustomerDossier key={customerSelected.id} customer={customerSelected} isNew={!!customerPanel && "draft" in customerPanel} invoices={invoices} schedules={schedules} onSchedule={id => { setCustomerPanel(null); setSection("schedules"); setSchedulePanel({ id }); }} onClose={() => setCustomerPanel(null)} onSave={customer => { dispatchCustomer({ type: "save", customer }); setCustomerPanel({ id: customer.id }); }} onStatus={dispatchCustomer} onInvoice={id => { setCustomerPanel(null); setSelectedId(id); }} /> : null}
    {scheduleSelected ? <ScheduleDossier key={scheduleSelected.id} initial={scheduleSelected} isNew={!!schedulePanel && "draft" in schedulePanel} customers={customers} invoices={invoices} onAddCustomer={customer => dispatchCustomer({ type: "save", customer })} onClose={() => setSchedulePanel(null)} onSave={schedule => { dispatchSchedule({ type: "save", schedule }); setSchedulePanel(null); }} /> : null}
    {editing ? <InvoiceEditor initial={editing} customers={customers} onAddCustomer={customer => dispatchCustomer({ type: "save", customer })} business={business} onClose={() => setEditing(null)} onSave={invoice => { dispatch({ type: "save", invoice }); setEditing(null); setSelectedId(invoice.id); }} /> : null}
    {selected ? <InvoiceDossier key={selected.id} invoice={selected} business={business} dispatch={dispatch} onClose={() => setSelectedId(null)} onEdit={() => { setEditing(selected); setSelectedId(null); }} /> : null}
  </section>;
}
