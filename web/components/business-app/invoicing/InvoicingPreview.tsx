"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { ArrowDown, Check, ChevronLeft, ChevronRight, Clock3, FilePenLine, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness } from "../BusinessWorkspace";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { periodRange, type Period } from "../business-format";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import RecordsDatePreview from "../transacciones/RecordsDatePreview";
import { RecordsSummaryCards } from "../transacciones/RecordsResultsSummary";
import { pageLinks } from "../transacciones/records-pagination";
import { InvoiceDate, InvoiceMoney, useInvoiceWords } from "./InvoiceDocument";
import InvoiceEditor from "./InvoiceEditor";
import InvoiceDossier from "./InvoiceDossier";
import { CURRENCIES, invoiceAmounts, invoiceFixtures, invoiceReducer, invoiceState, matchesInvoice, newInvoice, type InvoiceCurrency, type InvoiceFilter, type InvoicePreview } from "./invoice-preview-model";
import overview from "../transacciones/records-overview-preview.module.css";
import styles from "./invoicing-preview.module.css";

const sessionInvoices = new Map<string, InvoicePreview[]>();
const FILTERS: readonly InvoiceFilter[] = ["all", "draft", "outstanding", "overdue", "paid"];
const CARDS = [{ key: "draft", icon: FilePenLine, tone: "approval" }, { key: "overdue", icon: Clock3, tone: "review" }, { key: "paid", icon: Check, tone: "export" }] as const;

export default function InvoicingPreview() {
  const { chosen } = useBusiness();
  return <InvoiceWorkspace key={chosen?.space_id ?? "own"} scope={chosen?.space_id ?? "own"} business={chosen?.name ?? ""} />;
}

function InvoiceWorkspace({ scope, business }: { scope: string; business: string }) {
  const { word, locale } = useInvoiceWords();
  const { isBelowTablet: phone } = useResponsiveLayout();
  const [invoices, dispatch] = useReducer(invoiceReducer, scope, key => sessionInvoices.get(key) ?? invoiceFixtures().map(invoice => ({ ...invoice, items: invoice.items.map(item => ({ ...item, description: word("sample_item") })) })));
  const [editing, setEditing] = useState<InvoicePreview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<InvoiceFilter>("all");
  const [currency, setCurrency] = useState<InvoiceCurrency | "all">("all");
  const [period, setPeriod] = useState<Period>(() => periodRange("all"));
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(25);
  const [density, setDensity] = useState<"compact" | "normal" | "comfortable">("normal");
  const [sort, setSort] = useState<"newest" | "oldest" | "customer">("newest");
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => { sessionInvoices.set(scope, invoices); }, [scope, invoices]);
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k" && !editing && !selectedId) { event.preventDefault(); event.stopImmediatePropagation(); search.current?.focus(); }
    };
    window.addEventListener("keydown", focusSearch, true);
    return () => window.removeEventListener("keydown", focusSearch, true);
  }, [editing, selectedId]);
  const choose = (value: InvoiceFilter) => { setFilter(value); setPage(1); };
  const inPeriod = invoices.filter(invoice => period.key === "all" || (invoice.issuedOn >= period.from && (!period.to || invoice.issuedOn <= period.to)));
  const normalize = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase(locale);
  const results = inPeriod.filter(invoice => matchesInvoice(invoice, filter) && (currency === "all" || invoice.currency === currency) && normalize(`${invoice.reference} ${invoice.customer.name} ${invoice.notes}`).includes(normalize(query))).sort((a, b) => sort === "customer" ? a.customer.name.localeCompare(b.customer.name, locale) || a.id.localeCompare(b.id) : (sort === "newest" ? b.issuedOn.localeCompare(a.issuedOn) : a.issuedOn.localeCompare(b.issuedOn)) || a.id.localeCompare(b.id));
  const pages = Math.max(1, Math.ceil(results.length / size));
  const shownPage = Math.min(page, pages);
  const rows = results.slice((shownPage - 1) * size, shownPage * size);
  const summary = (() => {
    const groups = new Map<string, { total: number; settled: number; balance: number }>();
    let unconfirmed = 0;
    for (const invoice of results) {
      const amount = invoiceAmounts(invoice);
      if (!amount || invoice.issuance !== "issued") { unconfirmed++; continue; }
      const previous = groups.get(invoice.currency) ?? { total: 0, settled: 0, balance: 0 };
      groups.set(invoice.currency, { total: previous.total + amount.total, settled: previous.settled + amount.paid, balance: previous.balance + amount.balance });
    }
    return { currencies: [...groups].map(([currency, amount]) => ({ currency, total: (amount.total / 100).toFixed(2), settled: (amount.settled / 100).toFixed(2), balance: (amount.balance / 100).toFixed(2) })), exclusions: { unconfirmed, personal: 0, unavailable: 0 } };
  })();
  const selected = invoices.find(invoice => invoice.id === selectedId);
  const customers = [...new Map(invoices.map(invoice => [invoice.customer.id, invoice.customer])).values()];
  if (editing) return <InvoiceEditor initial={editing} customers={customers} business={business} onClose={() => setEditing(null)} onSave={invoice => { dispatch({ type: "save", invoice: { ...invoice, customer: { ...invoice.customer, id: invoice.customer.id || crypto.randomUUID() } } }); setEditing(null); setSelectedId(invoice.id); }} />;
  return <section className={styles.workspace} data-testid="invoicing-preview">
    {phone ? <h2 className="mb-5 font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{word("title")}</h2> : null}
    <div className={overview.cards}>{CARDS.map(({ key, icon: Icon, tone }) => <button key={key} className={`${overview.card} ${overview[tone]}`} aria-pressed={filter === key} onClick={() => choose(filter === key ? "all" : key)}><span className={overview.heading}><Icon size={21} /><span>{word(key)}</span></span><span className={`${overview.count} font-display`}>{inPeriod.filter(invoice => matchesInvoice(invoice, key)).length}</span><span className={overview.description}>{word(`overview_${key}`)}</span></button>)}</div>
    <div className={styles.toolbar}>
      <ToolbarPicker label={word("views")} value={word(filter)}>{close => FILTERS.map(value => <button className={styles.option} key={value} onClick={() => { choose(value); close(); }}>{word(value)}{value === filter ? <Check size={16} /> : null}</button>)}</ToolbarPicker>
      <label className={styles.search}><Search size={17} aria-hidden="true" /><input ref={search} type="search" value={query} placeholder={word("search")} aria-label={word("search")} onChange={event => { setQuery(event.target.value); setPage(1); }} /></label>
      <RecordsDatePreview period={period} value={period} onChange={value => { setPeriod(value); setPage(1); }} />
      <ToolbarPicker label={word("filters")} value={word("filters")}>{close => <><p className={styles.pickerLabel}>{word("currency")}</p>{(["all", ...CURRENCIES] as const).map(value => <button key={value} className={styles.option} onClick={() => { setCurrency(value); setPage(1); close(); }}>{value === "all" ? word("all_currencies") : value}{currency === value ? <Check size={16} /> : null}</button>)}</>}</ToolbarPicker>
      <button className={`${primaryButtonClass} ${styles.create}`} aria-label={word("create")} onClick={() => setEditing(newInvoice(crypto.randomUUID(), `M-${String(invoices.length + 1).padStart(3, "0")}`))}><Plus size={18} /><span>{word("create")}</span></button>
      <ToolbarPicker label={word("settings")} value={word("settings")} icon={<SlidersHorizontal size={16} />} flip wide>{() => <div className={styles.settings}><p>{word("row_height")}</p><SegmentedControl label={word("row_height")} value={density} onChange={setDensity} fill segments={(["compact", "normal", "comfortable"] as const).map(key => ({ key, label: word(key) }))} /><p>{word("sort")}</p><SegmentedControl label={word("sort")} value={sort} onChange={value => { setSort(value); setPage(1); }} fill segments={(["newest", "oldest", "customer"] as const).map(key => ({ key, label: word(key) }))} /></div>}</ToolbarPicker>
    </div>
    {filter !== "all" || currency !== "all" ? <div className={styles.chips}>{filter !== "all" ? <button onClick={() => choose("all")}>{word(filter)}<X size={14} aria-label={word("clear")} /></button> : null}{currency !== "all" ? <button onClick={() => { setCurrency("all"); setPage(1); }}>{currency}<X size={14} aria-label={word("clear")} /></button> : null}</div> : null}
    {summary.currencies.length ? <RecordsSummaryCards summary={summary} kind="venta" /> : null}
    <div className={styles.tableFrame} data-density={density}>
      <table className={styles.table}><thead><tr><th>{word("invoice")}</th><th><button onClick={() => { setSort("customer"); setPage(1); }}>{word("customer")}{sort === "customer" ? <ArrowDown size={13} /> : null}</button></th><th><button onClick={() => { setSort(sort === "newest" ? "oldest" : "newest"); setPage(1); }}>{word("issue_date")}{sort !== "customer" ? <ArrowDown size={13} className={sort === "oldest" ? "rotate-180" : ""} /> : null}</button></th><th>{word("due_date")}</th><th className={styles.numeric}>{word("document_total")}</th><th className={styles.numeric}>{word("balance")}</th><th>{word("status")}</th></tr></thead><tbody>{rows.map(invoice => { const amount = invoiceAmounts(invoice); return <tr key={invoice.id} data-selected={selectedId === invoice.id} onClick={() => setSelectedId(invoice.id)}><td><button className={styles.rowLink} onClick={() => setSelectedId(invoice.id)}>{invoice.reference}</button></td><td title={invoice.customer.name}>{invoice.customer.name}</td><td><InvoiceDate date={invoice.issuedOn} /></td><td><InvoiceDate date={invoice.dueOn} /></td><td className={styles.numeric}>{amount ? <InvoiceMoney amount={amount.total} currency={invoice.currency} /> : "—"}</td><td className={styles.numeric}>{invoice.issuance === "issued" && amount ? <InvoiceMoney amount={amount.balance} currency={invoice.currency} /> : "—"}</td><td><span className={styles.badge} data-state={invoiceState(invoice)}>{word(`state_${invoiceState(invoice)}`)}</span></td></tr>; })}</tbody></table>
      <div className={styles.phoneList}>{rows.map(invoice => { const amount = invoiceAmounts(invoice); return <button key={invoice.id} onClick={() => setSelectedId(invoice.id)}><strong>{invoice.customer.name}</strong><span>{amount ? <InvoiceMoney amount={amount.total} currency={invoice.currency} /> : "—"}</span><span><span className={styles.badge} data-state={invoiceState(invoice)}>{word(`state_${invoiceState(invoice)}`)}</span></span><small>{word("due_short")} <InvoiceDate date={invoice.dueOn} /></small></button>; })}</div>
      {!rows.length ? <div className={styles.empty}><h3>{word("no_results")}</h3><button className={quietButtonClass} onClick={() => { setQuery(""); setCurrency("all"); choose("all"); setPeriod(periodRange("all")); }}>{word("clear_filters")}</button></div> : null}
      <footer className={styles.pagination}><span>{word("result_count", { from: results.length ? (shownPage - 1) * size + 1 : 0, to: Math.min(shownPage * size, results.length), count: results.length })}</span><ToolbarPicker label={word("page_size")} value={String(size)}>{close => [25, 50, 100].map(value => <button className={styles.option} key={value} onClick={() => { setSize(value); setPage(1); close(); }}>{value}</button>)}</ToolbarPicker><nav aria-label={word("pages")}><button aria-label={word("previous")} disabled={shownPage === 1} onClick={() => setPage(shownPage - 1)}><ChevronLeft size={17} /></button>{pageLinks(shownPage, pages).map((value, index) => value === "gap" ? <span key={`gap${index}`}>…</span> : <button key={value} aria-current={shownPage === value ? "page" : undefined} onClick={() => setPage(value)}>{value}</button>)}<button aria-label={word("next")} disabled={shownPage === pages} onClick={() => setPage(shownPage + 1)}><ChevronRight size={17} /></button></nav></footer>
    </div>
    <p className={styles.previewNote}>{word("preview_note")}</p>
    {selected ? <InvoiceDossier key={selected.id} invoice={selected} business={business} dispatch={dispatch} onClose={() => setSelectedId(null)} onEdit={() => { setEditing(selected); setSelectedId(null); }} /> : null}
  </section>;
}
