"use client";
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Search, SlidersHorizontal } from "lucide-react";
import * as api from "@/lib/business-invoices-api";
import { browserAuthGeneration } from "@/lib/browser-auth-generation";
import { currencySymbol } from "@/lib/money-entry";
import { getChosenGrant, subscribeChosenGrant } from "@/lib/business-grant";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { useBusiness } from "../BusinessWorkspace";
import { formatAmount, periodRange, type Period } from "../business-format";
import RecordsDatePreview from "../transacciones/RecordsDatePreview";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import { pageLinks } from "../transacciones/records-pagination";
import InvoiceResultsSummary from "./InvoiceResultsSummary";
import WorkspaceEmptyState from "./WorkspaceEmptyState";
import InvoiceEditor from "./InvoiceEditor";
import InvoiceUnavailableBlocks from "./InvoiceUnavailableBlocks";
import InvoiceSetupCards from "./InvoiceSetupCards";
import CustomerForm from "./CustomerForm";
import InvoiceDocument, { InvoiceDate, useInvoiceWords } from "./InvoiceDocument";
import { invoiceReference } from "./invoice-reference";
import { createInvoiceCommandController, type CommandState, type InvoiceCommandController } from "./invoice-command-controller";
import { blankInvoiceDraft, customerForEditor, draftFromEditor, invoiceForEditor } from "./invoice-editor-adapter";
import type { BusinessCustomer } from "./customer-preview-model";
import type { InvoicePreview } from "./invoice-preview-model";
import styles from "./invoicing-preview.module.css";

export type InvoiceCapabilities = { prepare: boolean; issue: boolean; download: boolean };
export type InvoiceWorkspaceTransport = Pick<typeof api, "listInvoices" | "listCustomers" | "getInvoice" | "getCustomer" | "saveInvoice" | "saveCustomer" | "prepareInvoice" | "submitInvoice" | "getInvoiceOperation" | "downloadInvoiceArtifact">;
const liveTransport: InvoiceWorkspaceTransport = api;
const scopeKey = (scope: api.InvoiceScope) => JSON.stringify([scope.userId, scope.businessId, scope.grantId]);
export default function ConnectedInvoicingWorkspace(props: { scope: api.InvoiceScope; business: string; capabilities: InvoiceCapabilities; transport?: InvoiceWorkspaceTransport }) {
  const scope = useMemo(() => ({ userId: props.scope.userId, businessId: props.scope.businessId, grantId: props.scope.grantId }), [props.scope.userId, props.scope.businessId, props.scope.grantId]);
  return <ConnectedInvoiceCanvas key={scopeKey(scope)} {...props} scope={scope} />;
}
function statusOf(invoice: api.SavedInvoice) {
  const operation = invoice.operation;
  if (!operation) return "draft";
  if (operation.state.submission === "unknown" || operation.state.reconciliation === "conflict") return "uncertain_stage";
  if (operation.state.legal === "ACCEPTED" || operation.state.legal === "ACCEPTED_WITH_OBSERVATIONS") return "issued";
  if (operation.state.legal === "REJECTED") return "rejected";
  if (operation.state.submission === "prepared") return "prepare_state";
  return "processing";
}
function InvoiceStatusBadge({ invoice }: { invoice: api.SavedInvoice }) {
  const { t } = useTranslation();
  const state = statusOf(invoice);
  return <span className={styles.badge} data-state={state === "uncertain_stage" ? "uncertain" : state}>{t(`business.invoicing.${state}`)}</span>;
}
function CommandStatus({ state, retry, reload }: { state: CommandState; retry: () => void; reload: () => void }) {
  const { t } = useTranslation();
  if (state.kind === "idle" || state.kind === "disposed") return null;
  if (state.kind === "pending") return <p role="status">{t("business.invoicing.saving")}</p>;
  if (state.kind === "saved") return <p role="status">{t(`business.invoicing.${state.result.kind === "customer" ? "customer_saved" : "saved"}`)}</p>;
  return <div role="alert" className={styles.notice}><p>{t(`business.invoicing.${state.failure}`)}</p>{state.retryable ? <button type="button" className={quietButtonClass} onClick={retry}>{t("business.invoicing.retry")}</button> : state.failure === "conflict" ? <button type="button" className={quietButtonClass} onClick={reload}>{t("business.invoicing.reload")}</button> : null}</div>;
}
function ConnectedInvoiceCanvas({ scope, business, capabilities, transport = liveTransport }: { scope: api.InvoiceScope; business: string; capabilities: InvoiceCapabilities; transport?: InvoiceWorkspaceTransport }) {
  const { word, locale, t } = useInvoiceWords();
  const { openPanel } = useBusiness();
  const tabsId = useId();
  const stages = ["all", "draft", "issued", "processing", "rejected", "uncertain"] as const;
  const [generation] = useState(browserAuthGeneration);
  const liveScope = useSyncExternalStore(subscribeChosenGrant, () => `${getChosenGrant()}:${browserAuthGeneration()}`, () => `${scope.grantId}:${generation}`);
  const scopeActive = liveScope === `${scope.grantId}:${generation}`;
  const [section, setSection] = useState<"invoices" | "customers">("invoices");
  const [query, setQuery] = useState<api.InvoiceQuery>({ page: 1, page_size: 25, search: "", stage: "all", sort: "newest" });
  const [period, setPeriod] = useState<Period>(periodRange("all"));
  const [density, setDensity] = useState<"compact" | "normal" | "comfortable">("normal");
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerQuery, setCustomerQuery] = useState<Pick<api.InvoiceQuery, "page" | "page_size" | "search"> & { archived: boolean }>({ page: 1, page_size: 25, search: "", archived: false });
  const [invoices, setInvoices] = useState<api.InvoicePage | null>(null);
  const [customers, setCustomers] = useState<api.CustomerPage | null>(null);
  const [pickerStatus, setPickerStatus] = useState<"pending" | "failed" | "ready">("ready");
  const [pickerCustomers, setPickerCustomers] = useState<api.SavedCustomer[]>([]);
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(false), [accessLost, setAccessLost] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<api.SavedInvoice | null>(null);
  const [editing, setEditing] = useState<{ id: string | null; data: api.InvoiceDraft; version: number | null } | null>(null);
  const [customerEditing, setCustomerEditing] = useState<{ record: api.SavedCustomer | null; initial: BusinessCustomer } | null>(null);
  const [commandState, setCommandState] = useState<CommandState>({ kind: "idle" });
  const [customerDirty, setCustomerDirty] = useState(false), [leavingCustomer, setLeavingCustomer] = useState(false);
  const [conflictReviewed, setConflictReviewed] = useState(false), [downloadFailed, setDownloadFailed] = useState(false), [issuanceUnavailable, setIssuanceUnavailable] = useState(false);
  const controller = useRef<InvoiceCommandController | null>(null);
  const readAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    const commands = createInvoiceCommandController(scope, undefined, { invoice: transport.saveInvoice, customer: transport.saveCustomer, prepare: transport.prepareInvoice, submit: transport.submitInvoice });
    controller.current = commands; setCommandState(commands.getSnapshot());
    const unsubscribe = commands.subscribe(() => {
      const state = commands.getSnapshot(); setCommandState(state);
      if (state.kind === "failed") setConflictReviewed(false);
      if (state.kind === "failed" && state.failure === "unavailable") setIssuanceUnavailable(true);
      if (state.kind === "saved") {
        if (state.result.kind === "invoice") { setSelected(state.result.record); setEditing(null); }
        else setCustomerEditing({ record: state.result.record, initial: customerForEditor(state.result.record) });
        setRefresh(value => value + 1);
      }
    });
    const restored = commands.getSnapshot();
    if (restored.kind === "failed" && restored.command?.kind === "invoice") setEditing({ id: restored.command.id, data: restored.command.body.data, version: restored.command.body.expected_version });
    if (restored.kind === "failed" && restored.command?.kind === "customer") {
      const data = restored.command.body.data;
      setCustomerEditing({ record: null, initial: { id: restored.command.id ?? "new", name: data.name, email: data.email, address: data.address, taxId: data.tax_id, status: restored.command.body.archived ? "archived" : "active" } });
    }
    return () => { unsubscribe(); commands.dispose(); readAbort.current?.abort(); };
  }, [scope, transport]);
  useEffect(() => {
    const abort = new AbortController();
    if (!scopeActive) return () => abort.abort();
    setLoading(true); setLoadError(false);
    const load = section === "invoices" ? transport.listInvoices(scope, query, abort.signal).then(value => { if (!abort.signal.aborted) setInvoices(value); }) : transport.listCustomers(scope, customerQuery, abort.signal).then(value => { if (!abort.signal.aborted) setCustomers(value); });
    void load.catch(error => { if (!abort.signal.aborted) { setLoadError(true); if (error instanceof api.InvoiceProblem && [401, 403].includes(error.status)) setAccessLost(true); } }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [scope, scopeActive, transport, query, customerQuery, section, refresh]);
  useEffect(() => {
    const abort = new AbortController();
    if (editing && scopeActive) {
      setPickerStatus("pending"); setPickerCustomers([]);
      void transport.listCustomers(scope, { page: 1, page_size: 25, search: customerSearch }, abort.signal).then(result => { if (!abort.signal.aborted) { setPickerCustomers(result.items); setPickerStatus("ready"); } }).catch(error => { if (!abort.signal.aborted) { setPickerStatus("failed"); if (error instanceof api.InvoiceProblem && [401, 403].includes(error.status)) setAccessLost(true); } });
    }
    return () => abort.abort();
  }, [scope, scopeActive, editing, customerSearch, transport, refresh]);
  const blocked = !scopeActive || accessLost || commandState.kind === "disposed" || commandState.kind === "failed" && (commandState.retryable || commandState.failure === "access" || commandState.failure === "storage" || commandState.failure === "conflict" && !conflictReviewed);
  const busy = commandState.kind === "pending";
  const reload = async () => {
    if (customerEditing?.record) {
      const abort = new AbortController(); readAbort.current?.abort(); readAbort.current = abort;
      try { const record = await transport.getCustomer(scope, customerEditing.record.id, abort.signal); if (!abort.signal.aborted) { setCustomerEditing(current => current ? { ...current, record } : null); setConflictReviewed(true); } }
      catch (error) { if (!abort.signal.aborted) { setLoadError(true); if (error instanceof api.InvoiceProblem && [401, 403].includes(error.status)) setAccessLost(true); } }
      return;
    }
    if (!editing?.id && !selected?.id) { setRefresh(value => value + 1); return; }
    const abort = new AbortController(); readAbort.current?.abort(); readAbort.current = abort;
    try {
      const record = await transport.getInvoice(scope, editing?.id ?? selected!.id, abort.signal);
      if (!abort.signal.aborted) { setSelected(record); if (editing) setEditing(current => current ? { ...current, version: record.version } : null); setConflictReviewed(true); setRefresh(value => value + 1); }
    } catch (error) { if (!abort.signal.aborted) { setLoadError(true); if (error instanceof api.InvoiceProblem && [401, 403].includes(error.status)) setAccessLost(true); } }
  };
  const status = <CommandStatus state={commandState} retry={() => void controller.current?.retry()} reload={() => void reload()} />;
  const openInvoice = async (id: string) => {
    const abort = new AbortController(); readAbort.current?.abort(); readAbort.current = abort;
    try { const record = await transport.getInvoice(scope, id, abort.signal); if (!abort.signal.aborted) { setSelected(record); setEditing(null); } }
    catch (error) { if (!abort.signal.aborted) { setLoadError(true); if (error instanceof api.InvoiceProblem && [401, 403].includes(error.status)) setAccessLost(true); } }
  };
  const saveDraft = (draft: InvoicePreview) => {
    if (!editing || blocked || busy) return;
    void controller.current?.submit({ kind: "invoice", id: editing.id, key: crypto.randomUUID(), body: { data: draftFromEditor(draft, editing.data, pickerCustomers), expected_version: editing.version } });
  };
  const saveCustomer = (draft: BusinessCustomer) => {
    if (!customerEditing || blocked || busy) return;
    const previous = customerEditing.record;
    const data: api.CustomerInput = { name: draft.name, email: draft.email, tax_id: draft.taxId, address: draft.address, phone: previous?.data.phone ?? "", notes: previous?.data.notes ?? "" };
    void controller.current?.submit({ kind: "customer", id: previous?.id ?? null, key: crypto.randomUUID(), body: { data, archived: draft.status === "archived", expected_version: previous?.version ?? null } });
  };
  const download = async (record: api.SavedInvoice, kind: "xml" | "pdf") => {
    setDownloadFailed(false); const abort = new AbortController(); readAbort.current?.abort(); readAbort.current = abort;
    try {
      const blob = await transport.downloadInvoiceArtifact(scope, record, kind, abort.signal);
      if (abort.signal.aborted || getChosenGrant() !== scope.grantId || browserAuthGeneration() !== generation) return;
      const url = URL.createObjectURL(blob), anchor = document.createElement("a"); anchor.href = url; anchor.download = `fiscal.${kind}`; anchor.click(); URL.revokeObjectURL(url);
    } catch (error) { if (!abort.signal.aborted) { setDownloadFailed(true); if (error instanceof api.InvoiceProblem && [401, 403].includes(error.status)) setAccessLost(true); } }
  };
  if (!scopeActive || accessLost || commandState.kind === "disposed" || commandState.kind === "failed" && commandState.failure === "access") return <p role="alert">{t("business.invoicing.access")}</p>;
  const count = section === "invoices" ? invoices?.total ?? null : customers?.total ?? null;
  const page = section === "invoices" ? query.page : customerQuery.page;
  const pageSize = section === "invoices" ? query.page_size : customerQuery.page_size;
  const setPage = (value: number) => section === "invoices" ? setQuery(current => ({ ...current, page: value })) : setCustomerQuery(current => ({ ...current, page: value }));
  const pages = count === null ? 1 : Math.max(1, Math.ceil(count / pageSize));
  const invoiceHasFilters = Boolean(query.search || query.currency || query.date_from || query.date_to);
  const invoiceFirstEmpty = !loading && !loadError && invoices?.total === 0 && query.stage === "all" && !invoiceHasFilters && query.page === 1;
  const customerFirstEmpty = !loading && !loadError && customers?.total === 0 && !customerQuery.search && !customerQuery.archived && customerQuery.page === 1;
  const editingReference = editing?.id && selected?.id === editing.id ? invoiceReference(selected, t, locale) : "";
  const startCustomer = () => setCustomerEditing({ record: null, initial: { id: "new", name: "", email: "", taxId: "", address: "", status: "active" } });
  const startInvoice = () => { setSelected(null); setEditing({ id: null, version: null, data: blankInvoiceDraft() }); };
  const invoiceCreate = <button className={primaryButtonClass} disabled={!capabilities.prepare || blocked || busy} onClick={startInvoice}><Plus size={18} />{word("create")}</button>;
  const customerCreate = <button className={primaryButtonClass} disabled={!capabilities.prepare || blocked || busy} onClick={startCustomer}><Plus size={18} />{word("customers_add")}</button>;
  return <section className={styles.workspace} data-testid="connected-invoicing-workspace">
    <div className={styles.workspaceSwitch}><SegmentedControl label={word("title")} value={section} onChange={setSection} segments={[{ key: "invoices", label: word("invoices_tab") }, { key: "customers", label: word("customers_tab") }]} /></div>
    {editing || customerEditing ? null : status}
    {section === "invoices" ? <div className={styles.stageTabs} role="tablist" aria-label={word("views")}>{stages.map((stage, index) => <button key={stage} id={`${tabsId}-${stage}`} type="button" role="tab" aria-controls={`${tabsId}-results`} tabIndex={query.stage === stage ? 0 : -1} aria-selected={query.stage === stage} onKeyDown={event => { const next = event.key === "Home" ? 0 : event.key === "End" ? stages.length - 1 : event.key === "ArrowRight" ? (index + 1) % stages.length : event.key === "ArrowLeft" ? (index + stages.length - 1) % stages.length : null; if (next === null) return; event.preventDefault(); setQuery(current => ({ ...current, stage: stages[next], page: 1 })); document.getElementById(`${tabsId}-${stages[next]}`)?.focus(); }} onClick={() => setQuery(current => ({ ...current, stage, page: 1 }))}>{t(`business.invoicing.${stage === "uncertain" ? "uncertain_stage" : stage}`)}{stage === "all" ? null : <span>{loading || loadError || !invoices ? "-" : invoices.stage_counts[stage] ?? 0}</span>}</button>)}</div> : null}
    <div className={styles.toolbar}><label className={styles.search}><Search size={17} aria-hidden="true" /><input type="search" maxLength={200} aria-label={word(section === "invoices" ? "search" : "customers_search")} placeholder={word(section === "invoices" ? "search" : "customers_search")} value={section === "invoices" ? query.search : customerQuery.search} onChange={event => section === "invoices" ? setQuery(current => ({ ...current, search: event.target.value, page: 1 })) : setCustomerQuery(current => ({ ...current, search: event.target.value, page: 1 }))} /></label>
      {section === "invoices" ? <><RecordsDatePreview period={period} value={period} onChange={next => { setPeriod(next); setQuery(current => ({ ...current, page: 1, date_from: next.key === "all" ? undefined : next.from, date_to: next.key === "all" ? undefined : next.to ?? undefined })); }} /><ToolbarPicker label={word("currency")} value={query.currency ?? word("all_currencies")}>{close => ([undefined, "DOP", "USD", "EUR"] as const).map(currency => <button type="button" key={currency ?? "all"} className={styles.option} onClick={() => { setQuery(current => ({ ...current, currency, page: 1 })); close(); }}>{currency ?? word("all_currencies")}</button>)}</ToolbarPicker>{invoiceFirstEmpty ? null : <>{invoiceCreate}<ToolbarPicker label={word("settings")} value={word("settings")} icon={<SlidersHorizontal size={16} />} flip wide>{() => <div className={styles.settings}><p>{word("row_height")}</p><SegmentedControl label={word("row_height")} value={density} onChange={setDensity} fill segments={(["compact", "normal", "comfortable"] as const).map(key => ({ key, label: word(key) }))} /><p>{word("sort")}</p><SegmentedControl label={word("sort")} value={query.sort ?? "newest"} onChange={sort => setQuery(current => ({ ...current, sort, page: 1 }))} fill segments={(["newest", "oldest"] as const).map(key => ({ key, label: word(key) }))} /></div>}</ToolbarPicker></>}</> : <><button className={quietButtonClass} onClick={() => setCustomerQuery(current => ({ ...current, archived: !current.archived, page: 1 }))}>{word(customerQuery.archived ? "customers_archived" : "customers_active")}</button>{customerFirstEmpty ? null : customerCreate}</>}
    </div>
    {!loading && !loadError && section === "invoices" && query.stage === "all" && invoices ? <InvoiceResultsSummary currencies={invoices.summaries.map(group => ({ currency: group.currency, total: group.billed, settled: group.collected, balance: group.outstanding }))} /> : null}
    <div id={`${tabsId}-results`} role={section === "invoices" ? "tabpanel" : undefined} aria-labelledby={section === "invoices" ? `${tabsId}-${query.stage}` : undefined}>
    {loadError ? <div role="alert"><p>{t("business.invoicing.load_failed")}</p><button className={quietButtonClass} onClick={() => setRefresh(value => value + 1)}>{t("common.retry")}</button></div> : loading ? <p role="status">{t("common.loading")}</p> : section === "invoices" ? invoices?.items.length === 0 ? <>{invoiceFirstEmpty ? <InvoiceSetupCards disabled={!capabilities.prepare || blocked || busy} onBusiness={() => openPanel({ kind: "business", tab: "datos" })} onCustomer={startCustomer} onInvoice={startInvoice} /> : null}<WorkspaceEmptyState compact={!invoiceFirstEmpty} title={word(invoiceFirstEmpty ? "first_invoice" : "no_results")} description={word(invoiceFirstEmpty ? "first_invoice_help" : "no_results_help")} action={invoiceFirstEmpty ? invoiceCreate : invoiceHasFilters ? <button className={quietButtonClass} onClick={() => { setPeriod(periodRange("all")); setQuery(current => ({ ...current, search: "", currency: undefined, date_from: undefined, date_to: undefined, page: 1 })); }}>{word("clear_filters")}</button> : undefined} /></> : <div className={styles.tableFrame} data-density={density}><table className={styles.table}><thead><tr><th>{word("invoice")}</th><th>{word("customer")}</th><th>{word("issue_date")}</th><th>{word("due_date")}</th><th>{word("currency")}</th><th className={styles.numeric}>{word("document_total")}</th><th className={styles.numeric}>{word("balance")}</th><th>{word("status")}</th></tr></thead><tbody>{invoices?.items.map(record => <tr key={record.id} data-selected={selected?.id === record.id && !editing} onClick={() => void openInvoice(record.id)}><td><button className={styles.rowLink} onClick={event => { event.stopPropagation(); void openInvoice(record.id); }}>{invoiceReference(record, t, locale)}</button></td><td title={record.data.customer_input.name}>{record.data.customer_input.name || "-"}</td><td><InvoiceDate date={record.data.issued_on} /></td><td><InvoiceDate date={record.data.due_on} /></td><td>{currencySymbol(record.data.currency)}</td><td className={`${styles.numeric} cuadrao-amount tabular-nums`}>{record.amounts ? formatAmount(record.amounts.total, record.data.currency, locale) : "-"}</td><td className={styles.numeric}>-</td><td><InvoiceStatusBadge invoice={record} /></td></tr>)}</tbody></table><div className={styles.phoneList}>{invoices?.items.map(record => <button key={record.id} onClick={() => void openInvoice(record.id)}><strong>{record.data.customer_input.name || word("customer_placeholder")}</strong><span className="cuadrao-amount">{record.amounts ? `${currencySymbol(record.data.currency)} ${formatAmount(record.amounts.total, record.data.currency, locale)}` : "-"}</span><span><InvoiceStatusBadge invoice={record} /></span><small>{word("due_short")} <InvoiceDate date={record.data.due_on} /></small></button>)}</div></div> : customers?.items.length === 0 ? <WorkspaceEmptyState compact={!customerFirstEmpty} art="customer" title={word(customerQuery.search ? "customers_no_matches" : customerQuery.archived ? "customers_no_archived" : "customers_empty")} description={word(customerQuery.search ? "no_results_help" : customerQuery.archived ? "customers_archived_help" : "customers_empty_help")} action={customerFirstEmpty ? customerCreate : customerQuery.search ? <button className={quietButtonClass} onClick={() => setCustomerQuery(current => ({ ...current, search: "", page: 1 }))}>{word("clear_search")}</button> : undefined} /> : <div className={styles.tableFrame}><table className={`${styles.table} ${styles.customerTable}`}><thead><tr><th>{word("customer")}</th><th>{word("customers_last_activity")}</th><th>{word("customers_last_invoice")}</th><th>{word("customers_last_payment")}</th><th>{word("schedules_next")}</th></tr></thead><tbody>{customers?.items.map(record => <tr key={record.id}><td><button className={styles.rowLink} onClick={() => setCustomerEditing({ record, initial: customerForEditor(record) })}>{record.data.name}</button><small>{record.data.email || record.data.tax_id}</small></td><td>-</td><td>-</td><td>-</td><td>-</td></tr>)}</tbody></table><div className={styles.customerPhone}>{customers?.items.map(record => <button key={record.id} className={styles.customerRow} onClick={() => setCustomerEditing({ record, initial: customerForEditor(record) })}><span className={styles.customerIdentity}><strong>{record.data.name}</strong><small>{record.data.email || record.data.tax_id || word("customers_no_contact")}</small></span></button>)}</div></div>}
    </div>
    {count !== null && !loading && !loadError ? <footer className={styles.pagination}><span>{word("result_count", { from: count ? (page - 1) * pageSize + 1 : 0, to: Math.min(page * pageSize, count), count })}</span><ToolbarPicker flip label={word("page_size")} value={t("business.transactions.pagination.per_page", { count: pageSize })}>{close => ([25, 50, 100] as const).map(page_size => <button type="button" className={styles.option} key={page_size} onClick={() => { if (section === "invoices") setQuery(current => ({ ...current, page_size, page: 1 })); else setCustomerQuery(current => ({ ...current, page_size, page: 1 })); close(); }}>{t("business.transactions.pagination.per_page", { count: page_size })}</button>)}</ToolbarPicker><nav aria-label={word("pages")}>{pageLinks(page, pages).map((value, index) => value === "gap" ? <span key={`gap${index}`}>…</span> : <button key={value} disabled={loading} aria-current={page === value ? "page" : undefined} onClick={() => setPage(value)}>{value}</button>)}</nav></footer> : null}
    {editing ? <InvoiceEditor key={editing.id ?? "new"} initial={invoiceForEditor(editing.data, editing.id ?? "new", null, editingReference)} business={business} customers={pickerCustomers.map(customerForEditor)} onAddCustomer={() => undefined} onSave={saveDraft} onClose={() => setEditing(null)} connection={{ busy, blocked: blocked || !capabilities.prepare || Boolean(selected?.operation), amounts: selected?.amounts ?? null, savedInput: selected ? invoiceForEditor(selected.data, selected.id, null, invoiceReference(selected, t, locale)) : null, errorInput: commandState.kind === "failed" && commandState.command?.kind === "invoice" ? invoiceForEditor(commandState.command.body.data, editing.id ?? "new", null, editingReference) : null, fieldErrors: commandState.kind === "failed" ? commandState.fieldErrors : selected?.field_errors ?? {}, status: <>{status}{pickerStatus === "failed" ? <div role="alert"><p>{t("business.invoicing.load_failed")}</p><button type="button" className={quietButtonClass} onClick={() => setRefresh(value => value + 1)}>{t("common.retry")}</button></div> : null}</>, customerSearchStatus: pickerStatus, onCustomerSearch: setCustomerSearch }} /> : null}
    {customerEditing ? <AdaptivePanel title={word("customers_tab")} summary={business} dismissible={!busy} onClose={() => customerDirty ? setLeavingCustomer(true) : setCustomerEditing(null)} closeLabel={t("common.close")} width="record"><CustomerForm key={`${customerEditing.initial.id}:${customerEditing.initial.updatedAt ?? "new"}`} onDirty={setCustomerDirty} initial={customerEditing.initial} onSave={saveCustomer} connection={{ busy, blocked: blocked || !capabilities.prepare, status, fieldErrors: commandState.kind === "failed" ? commandState.fieldErrors : {}, errorInput: commandState.kind === "failed" && commandState.command?.kind === "customer" ? commandState.command.body.data : null }} />{customerEditing.record ? <button type="button" className={quietButtonClass} disabled={busy || blocked || customerDirty || !capabilities.prepare} onClick={() => { const record = customerEditing.record; if (record) void controller.current?.submit({ kind: "customer", id: record.id, key: crypto.randomUUID(), body: { data: record.data, expected_version: record.version, archived: !record.archived } }); }}>{t(customerEditing.record.archived ? "common.restore" : "common.archive")}</button> : null}</AdaptivePanel> : null}
    {leavingCustomer ? <AdaptivePanel title={word("unsaved")} closeLabel={t("common.close")} onClose={() => setLeavingCustomer(false)}><div className={styles.panelBody}><p>{word("leave_note")}</p><button className={quietButtonClass} onClick={() => setLeavingCustomer(false)}>{t("common.cancel")}</button><button className={primaryButtonClass} onClick={() => { setLeavingCustomer(false); setCustomerEditing(null); }}>{word("discard")}</button></div></AdaptivePanel> : null}
    {selected && !editing ? <AdaptivePanel title={selected.operation?.number ?? word("draft_title")} summary={business} width="record" onClose={() => setSelected(null)} closeLabel={t("common.close")}><div className={styles.panelBody}>
      {status}<p>{t(`business.invoicing.${statusOf(selected)}`)}</p>
      <InvoiceDocument invoice={invoiceForEditor(selected.data, selected.id, selected.operation, invoiceReference(selected, t, locale))} business={business} connection={{ amounts: selected.amounts }} />
      <InvoiceUnavailableBlocks />
      {!selected.operation ? <><button className={quietButtonClass} disabled={!capabilities.prepare || blocked || busy} onClick={() => setEditing({ id: selected.id, version: selected.version, data: selected.data })}>{word("edit_draft")}</button><button className={primaryButtonClass} disabled={!capabilities.prepare || blocked || busy || issuanceUnavailable || selected.data.currency !== "DOP" || Object.keys(selected.field_errors).length > 0} onClick={() => void controller.current?.submit({ kind: "prepare", id: selected.id, expected_version: selected.version })}>{t("business.invoicing.prepare")}</button>{issuanceUnavailable ? <p>{t("business.invoicing.issuance_unavailable")}</p> : <p>{t("business.invoicing.prepare_warning")}</p>}{selected.data.currency !== "DOP" ? <p>{t("business.invoicing.foreign_save_only")}</p> : Object.keys(selected.field_errors).length ? <p>{t("business.invoicing.prepare_blocked")}</p> : null}</> : <><button className={quietButtonClass} onClick={() => void reload()}>{t("business.invoicing.refresh_state")}</button>{selected.operation.state.submission === "prepared" ? <button className={primaryButtonClass} disabled={!capabilities.issue || blocked || busy || issuanceUnavailable} onClick={() => void controller.current?.submit({ kind: "submit", id: selected.id, operation_id: selected.operation!.id, payload_digest: selected.operation!.payload_digest })}>{t("business.invoicing.submit")}</button> : null}{issuanceUnavailable && selected.operation.state.submission === "prepared" ? <p>{t("business.invoicing.issuance_unavailable")}</p> : null}{(["xml", "pdf"] as const).map(kind => <button className={quietButtonClass} key={kind} disabled={!capabilities.download || selected.operation?.state[kind] !== "available"} onClick={() => void download(selected, kind)}>{word(`official_${kind}`)}</button>)}</>}
      {downloadFailed ? <p role="alert">{t("business.invoicing.download_failed")}</p> : null}
    </div></AdaptivePanel> : null}
  </section>;
}
