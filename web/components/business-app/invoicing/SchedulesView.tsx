"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, Search } from "lucide-react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { useLendListSearch, useSearchInBar } from "../foundation/list-search";
import { InvoiceDate, useInvoiceWords } from "./InvoiceDocument";
import type { BusinessCustomer } from "./customer-preview-model";
import { nextOccurrence, type InvoiceSchedule } from "./schedule-preview-model";
import WorkspaceEmptyState from "./WorkspaceEmptyState";
import styles from "./invoicing-preview.module.css";

export default function SchedulesView({ schedules, customers, panelOpen, onCreate, onSelect, onStatus }: { schedules: InvoiceSchedule[]; customers: BusinessCustomer[]; panelOpen: boolean; onCreate: () => void; onSelect: (id: string) => void; onStatus: (id: string, status: InvoiceSchedule["status"]) => void }) {
  const { word, locale } = useInvoiceWords();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<InvoiceSchedule["status"]>("active");
  const search = useRef<HTMLInputElement>(null);
  const searchInBar = useSearchInBar();
  useLendListSearch("schedules", searchInBar ? { query, setQuery } : null);
  // With the search in the top bar, ⌘K is the bar's.
  useEffect(() => {
    if (searchInBar) return;
    const focus = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); event.stopImmediatePropagation(); if (!panelOpen) search.current?.focus(); } };
    window.addEventListener("keydown", focus, true);
    return () => window.removeEventListener("keydown", focus, true);
  }, [panelOpen, searchInBar]);
  const rows = schedules.filter(schedule => schedule.status === status && `${schedule.name} ${customers.find(customer => customer.id === schedule.customerId)?.name ?? ""}`.toLocaleLowerCase(locale).includes(query.trim().toLocaleLowerCase(locale)));
  return <div data-testid="schedules-view">
    <div className={styles.toolbar}>{searchInBar ? null : <label className={styles.search}><Search size={17} /><input ref={search} type="search" aria-label={word("schedules_search")} placeholder={word("schedules_search")} value={query} onChange={event => setQuery(event.target.value)} /></label>}<SegmentedControl label={word("status")} value={status} onChange={setStatus} segments={(["active", "paused"] as const).map(key => ({ key, label: word(`schedules_${key}`), count: schedules.filter(schedule => schedule.status === key).length }))} /><button className={`${primaryButtonClass} ${styles.create}`} disabled={panelOpen} onClick={onCreate}><Plus size={18} />{word("schedules_create")}</button></div>
    {rows.length ? <div className={styles.tableFrame}><table className={styles.table}><thead><tr><th>{word("schedules_name")}</th><th>{word("customer")}</th><th>{word("schedules_next")}</th><th>{word("schedules_frequency")}</th><th>{word("schedules_action")}</th><th><span className="sr-only">{word("schedules_controls")}</span></th></tr></thead><tbody>{rows.map(schedule => { const customer = customers.find(item => item.id === schedule.customerId); return <tr key={schedule.id} onClick={() => !panelOpen && onSelect(schedule.id)}><td><button className={styles.rowLink} onClick={() => !panelOpen && onSelect(schedule.id)}>{schedule.name}</button></td><td>{customer?.name || "-"}{customer?.status === "archived" ? <small className={styles.cellDetail}>{word("customers_archived")}</small> : null}</td><td>{schedule.status === "active" && customer?.status === "active" ? <InvoiceDate date={nextOccurrence(schedule)} /> : "-"}</td><td>{word(`schedules_${schedule.frequency}`)}</td><td>{word("schedules_mode_draft")}</td><td><button className={quietButtonClass} onClick={event => { event.stopPropagation(); onStatus(schedule.id, status === "active" ? "paused" : "active"); }} disabled={panelOpen || customer?.status !== "active" && status === "paused"}>{word(status === "active" ? "schedules_pause" : "schedules_resume")}</button></td></tr>; })}</tbody></table><div className={styles.schedulePhone}>{rows.map(schedule => <article key={schedule.id}><button onClick={() => !panelOpen && onSelect(schedule.id)}><strong>{schedule.name}</strong><span>{customers.find(customer => customer.id === schedule.customerId)?.name}</span><small>{word(`schedules_${schedule.frequency}`)} · {word("schedules_mode_draft")}</small><small>{word("schedules_next")} {schedule.status === "active" && customers.find(customer => customer.id === schedule.customerId)?.status === "active" ? <InvoiceDate date={nextOccurrence(schedule)} /> : "-"}</small></button><button className={quietButtonClass} disabled={panelOpen || status === "paused" && customers.find(customer => customer.id === schedule.customerId)?.status !== "active"} onClick={() => onStatus(schedule.id, status === "active" ? "paused" : "active")}>{word(status === "active" ? "schedules_pause" : "schedules_resume")}</button></article>)}</div></div> : <WorkspaceEmptyState compact={schedules.length > 0} art="schedule" title={word(query ? "schedules_no_matches" : status === "paused" ? "schedules_no_paused" : schedules.length ? "schedules_no_active" : "schedules_empty")} description={word(query ? "no_results_help" : status === "paused" ? "schedules_no_paused_help" : schedules.length ? "schedules_no_active_help" : "schedules_empty_help")} action={query ? <button className={quietButtonClass} onClick={() => setQuery("")}>{word("clear_search")}</button> : status === "active" && schedules.length ? <button className={quietButtonClass} onClick={() => setStatus("paused")}>{word("schedules_view_paused")}</button> : status === "active" ? <button className={primaryButtonClass} disabled={panelOpen} onClick={onCreate}><Plus size={18} />{word("schedules_create")}</button> : undefined} />}
    {schedules.length ? <p className={styles.previewNote}>{word("schedules_local")}</p> : null}
  </div>;
}
