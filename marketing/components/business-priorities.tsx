"use client";

import { useState } from "react";
import { ArrowDown, ArrowUpRight, CircleDashed, MessageSquare, FileText, Receipt, Wallet } from "lucide-react";
import type { BusinessLocale } from "./content";
import { formatSampleMoney } from "./sample-data";
import { priorityAmount, priorityCopy, priorityName, samplePriorities } from "./sample-priorities";
import styles from "./business-priorities.module.css";

const icons = { collection: Wallet, payable: Receipt, document: FileText };

export function BusinessPriorities({ locale, onOpenInvoice }: { locale: BusinessLocale; onOpenInvoice: () => void }) {
  const c = priorityCopy[locale];
  const [selectedId, setSelectedId] = useState(samplePriorities[0].id);
  const selected = samplePriorities.find((priority) => priority.id === selectedId)!;
  const detail = c[selected.kind];
  const collection = samplePriorities.find((priority) => priority.kind === "collection")!;
  return (
    <section className={styles.overview} id="el-producto" aria-labelledby="overview-title">
      <div className={styles.heading}>
        <p>01 / {locale === "es" ? "EL NEGOCIO, A LA VISTA" : "YOUR BUSINESS, IN VIEW"}</p>
        <h2 id="overview-title">{c.title}</h2>
        <p>{c.intro}</p>
      </div>
      <div className={styles.workspace}>
        <div className={styles.masthead}><span>{locale === "es" ? "Pendientes al comenzar" : "Open items at the start"}</span><span>{samplePriorities.length} {c.count}</span></div>
        <div className={styles.records}>
          <div className={styles.list} role="group" aria-label={c.title}>
            <div className={styles.listHeader}><span>{locale === "es" ? "Registro y estado" : "Record and status"}</span><span>{locale === "es" ? "Monto" : "Amount"}</span></div>
            {samplePriorities.map((priority) => {
              const Icon = icons[priority.kind];
              const text = c[priority.kind];
              return <button className={styles.row} type="button" key={priority.id} aria-pressed={selectedId === priority.id} aria-controls="priority-detail" onClick={() => setSelectedId(priority.id)}>
                <span className={styles.icon}><Icon size={19} aria-hidden="true" /></span>
                <span className={styles.rowText}><small>{text.label}</small><strong>{priorityName(priority, locale)}</strong><span>{text.status}</span></span>
                <span className={styles.rowAmount}>{formatSampleMoney(priorityAmount(priority), locale)}<ArrowUpRight size={17} aria-hidden="true" /></span>
              </button>;
            })}
          </div>
          <div id="priority-detail" className={styles.detail} role="region" aria-label={c.detail} aria-live="polite" aria-atomic="true">
            <div className={styles.detailContent} key={selected.id}>
              <span className={styles.status}><CircleDashed size={15} aria-hidden="true" />{detail.status}</span>
              <h3>{priorityName(selected, locale)}</h3>
              <p className={styles.amount}>{formatSampleMoney(priorityAmount(selected), locale)}</p>
              <p className={styles.amountLabel}>{detail.label}</p>
              <div className={styles.payment}>
                {selected.kind === "collection" && <><span>{c.collection.payment}</span><strong>{formatSampleMoney(selected.story.payment, locale)}</strong></>}
              </div>
              {selected.kind === "payable" && <dl className={styles.payableFacts}><div><dt>{locale === "es" ? "Cuenta del proveedor" : "Supplier record"}</dt><dd>{selected.id.replace("supplier-", "")}</dd></div><div><dt>{locale === "es" ? "Vencimiento" : "Due date"}</dt><dd>{locale === "es" ? "Mañana" : "Tomorrow"}</dd></div></dl>}
              <p className={styles.reason}>{detail.reason}</p>
              <div className={styles.next}><span>{c.next}</span><p>{detail.next}</p></div>
              {selected.kind === "collection" && <a className={styles.invoiceLink} href="#la-idea" onClick={onOpenInvoice}>{c.collection.action}<ArrowDown size={17} aria-hidden="true" /></a>}
              {selected.kind === "document" && <a className={styles.invoiceLink} href="#gastos-documentos">{locale === "es" ? "Ver cómo reunir el comprobante" : "See how to attach the receipt"}<ArrowDown size={17} aria-hidden="true" /></a>}
            </div>
          </div>
        </div>
        <div className={styles.assistant} aria-labelledby="assistant-title">
          <div className={styles.assistantLabel}><MessageSquare size={18} aria-hidden="true" /><h3 id="assistant-title">{locale === "es" ? "Preguntar, con los registros a mano." : "Ask, with the records at hand."}</h3><small>{locale === "es" ? "Asistente previsto" : "Planned assistant"}</small></div>
          <div className={styles.assistantExchange}><p>{locale === "es" ? "¿Qué me falta por cobrar?" : "What is still to collect?"}</p><div><p>{locale === "es" ? `En este ejemplo, ${priorityName(collection, locale)} tiene ${formatSampleMoney(priorityAmount(collection), locale)} pendientes. La factura es de ${formatSampleMoney(collection.story.invoice.amount, locale)} y tiene un abono de ${formatSampleMoney(collection.story.payment, locale)}.` : `In this example, ${priorityName(collection, locale)} has ${formatSampleMoney(priorityAmount(collection), locale)} outstanding. The invoice is ${formatSampleMoney(collection.story.invoice.amount, locale)} with a ${formatSampleMoney(collection.story.payment, locale)} payment recorded.`}</p><a href="#priority-detail" onClick={() => setSelectedId(collection.id)}>{locale === "es" ? `Ver la cuenta · Factura ${collection.story.invoice.id}` : `View the account · Invoice ${collection.story.invoice.id}`}<ArrowUpRight size={15} aria-hidden="true" /></a></div></div>
        </div>
        <p className={styles.caption}>{c.preview}</p>
      </div>
    </section>
  );
}
