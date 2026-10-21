"use client";

import { useState } from "react";
import { ArrowLeft, ArrowRight, Bell, Check, FileText, Search } from "lucide-react";
import type { BusinessLocale } from "./content";
import { exampleDate, exampleExpectations, exampleMoney, exampleMovements } from "./owner-example";
import { sampleInvoiceStory } from "./sample-data";
import { sampleExpenseStory } from "./sample-priorities";
import { OwnerStoryControls } from "./owner-story-controls";
import styles from "./owner-stories.module.css";

type WorkStep = "capture" | "assistant" | "search" | "updates";
type InputMethod = "manual" | "text" | "voice" | "photo" | "file";
type ReviewState = "preview" | "review" | "confirmed";
const inputMethods: readonly InputMethod[] = ["manual", "text", "voice", "photo", "file"];
const copy = {
  es: {
    eyebrow: "03 / REGISTRAR, ENCONTRAR Y RESOLVER", title: "Menos cosas en la cabeza. Más contexto a mano.", intro: "Anotar como te resulte más fácil, encontrar lo que buscas y decidir con ayuda. El asistente propone; tú revisas antes de confirmar.",
    steps: [
      { id: "capture", title: "De una idea a un registro", body: "Manual, texto, voz, foto o archivo, incluidos estados de cuenta. Revisa el monto, la categoría y el espacio antes de confirmar." },
      { id: "assistant", title: "Una respuesta. Un siguiente paso.", body: "Pregunta por un cobro. Revisa la factura que explica la respuesta y una acción propuesta sobre ese mismo registro." },
      { id: "search", title: "Encuentra el contexto completo", body: "Busca un cliente, monto o documento. Abre el registro y vuelve a tus resultados sin empezar de nuevo." },
      { id: "updates", title: "Vuelve por algo que importa", body: "Un vencimiento, un dato pendiente o una revisión. Cada aviso debe llevarte al asunto que puedes resolver." },
    ],
    readiness: "Vista prevista · ejemplo", manual: "Manual", text: "Texto", voice: "Voz", photo: "Foto", file: "Archivo", source: "Entrada de ejemplo", transcript: "Transcripción de ejemplo; no usa el micrófono.", entry: "Pagué {amount} de internet del local con mi tarjeta personal.", methodNote: "Estos controles muestran entradas previstas. No suben archivos ni envían datos a un modelo.",
    review: "Revisar propuesta", concept: "Concepto", amount: "Monto en RD$", category: "Categoría", utilities: "Servicios", supplies: "Materiales", unclassified: "Sin clasificar", paidFrom: "Pagado desde", personal: "Dinero personal", space: "Negocio", confirm: "Confirmar ejemplo", confirmed: "Ejemplo confirmado en esta vista.", noSave: "No se guardó un movimiento real. Los saldos del ejemplo no cambian.", replay: "Repetir ejemplo", reviewed: "Propuesta editable", original: "El texto original queda a mano para comparar.",
    question: "¿Qué me falta por cobrar?", answer: "En este ejemplo, Comercial La Ceiba tiene un saldo pendiente de", from: "Factura", received: "Abono recibido", sourceLink: "Ver factura y abono", propose: "Proponer un recordatorio", reminder: "Revisar el cobro de Comercial La Ceiba", date: "Fecha del recordatorio", note: "Nota", reminderConfirm: "Confirmar recordatorio de ejemplo", reminderSaved: "Recordatorio preparado en esta vista.", noReminder: "No se programó ninguna notificación ni se contactó al cliente.",
    search: "Buscar en el ejemplo", placeholder: "La Ceiba, internet, 2800…", results: "resultados", back: "Volver a resultados", noResults: "No hay resultados en estos registros de ejemplo.", record: "Registro", document: "Documento", status: "Estado", missing: "Comprobante pendiente", linked: "Documento de ejemplo", opened: "Registro seleccionado", money: "Monto", invoice: "Factura", receipt: "Recibo de transporte", sourceReview: "Ver el documento en contexto", current: "Pendientes del ejemplo", due: "Pago al proveedor", dueBody: "Vence el 7 de octubre. Revisa la fecha y el compromiso antes de pagar.", dueAction: "Ver próximos pagos", missingBody: "El gasto de transporte necesita su comprobante.", missingAction: "Revisar documento", reviewTitle: "Tu propuesta, antes de guardar", reviewBody: "El asistente deja la acción lista para que la revises.", reviewAction: "Ver propuesta", noNotifications: "Avisos ilustrativos. No se enviaron notificaciones.",
  },
  en: {
    eyebrow: "03 / RECORD, FIND AND RESOLVE", title: "Less to remember. More context at hand.", intro: "Record information your way, find what you need and get help deciding. The assistant proposes; you review before confirming.",
    steps: [
      { id: "capture", title: "From a thought to a record", body: "Manual entry, text, voice, photo or file, including statements. Review the amount, category and space before confirming." },
      { id: "assistant", title: "An answer. A next step.", body: "Ask about a payment. Review the invoice behind the answer and a proposed action on that same record." },
      { id: "search", title: "Find the whole context", body: "Search a customer, amount or document. Open the record and return to your results without starting again." },
      { id: "updates", title: "Come back for something useful", body: "A due date, a missing detail or a review. Each update should lead to something you can resolve." },
    ],
    readiness: "Planned view · sample", manual: "Manual", text: "Text", voice: "Voice", photo: "Photo", file: "File", source: "Sample input", transcript: "Sample transcript; no microphone is used.", entry: "I paid {amount} for the shop internet with my personal card.", methodNote: "These controls show planned inputs. They do not upload files or send data to a model.",
    review: "Review proposal", concept: "Description", amount: "Amount in RD$", category: "Category", utilities: "Utilities", supplies: "Supplies", unclassified: "Unclassified", paidFrom: "Paid from", personal: "Personal money", space: "Business", confirm: "Confirm example", confirmed: "Example confirmed in this view.", noSave: "No actual movement was saved. Sample balances stay unchanged.", replay: "Replay example", reviewed: "Editable proposal", original: "The original text stays available to compare.",
    question: "What am I still owed?", answer: "In this example, Comercial La Ceiba has an outstanding balance of", from: "Invoice", received: "Payment received", sourceLink: "View invoice and payment", propose: "Propose a reminder", reminder: "Review the Comercial La Ceiba balance", date: "Reminder date", note: "Note", reminderConfirm: "Confirm sample reminder", reminderSaved: "Reminder prepared in this view.", noReminder: "No notification was scheduled and the customer was not contacted.",
    search: "Search the example", placeholder: "La Ceiba, internet, 2800…", results: "results", back: "Back to results", noResults: "No matches in these sample records.", record: "Record", document: "Document", status: "Status", missing: "Receipt needed", linked: "Sample document", opened: "Selected record", money: "Amount", invoice: "Invoice", receipt: "Transport receipt", sourceReview: "View the document in context", current: "Sample open items", due: "Supplier payment", dueBody: "Due October 7. Check the date and commitment before paying.", dueAction: "View upcoming payments", missingBody: "The transport expense needs its receipt.", missingAction: "Review document", reviewTitle: "Your proposal, before saving", reviewBody: "The assistant prepares the action for you to review.", reviewAction: "View proposal", noNotifications: "Illustrative updates. No notifications were sent.",
  },
} as const;

export function WorkStory({ locale }: { locale: BusinessLocale }) {
  const c = copy[locale];
  const [step, setStep] = useState<WorkStep>("capture");
  const [method, setMethod] = useState<InputMethod>("text");
  const [captureState, setCaptureState] = useState<ReviewState>("preview");
  const [reminderState, setReminderState] = useState<ReviewState>("preview");
  const personalExpense = exampleMovements.find((item) => item.account === "personal")!;
  const [description, setDescription] = useState<string>(personalExpense.label[locale]);
  const [amount, setAmount] = useState(String(personalExpense.amount));
  const [category, setCategory] = useState("utilities");
  const [reminderDate, setReminderDate] = useState<string>(exampleExpectations.find((item) => item.direction === "in")!.date);
  const [reminderNote, setReminderNote] = useState<string>(c.reminder);
  const [query, setQuery] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);
  const money = (value: number) => exampleMoney(value, "DOP", locale);
  const outstanding = sampleInvoiceStory.invoice.amount - sampleInvoiceStory.payment;
  const records = [
    ...exampleMovements.map((item) => ({ id: item.id, label: item.label[locale], amount: item.amount, type: c.record, status: item.id === sampleExpenseStory.expense.id ? c.missing : item.account === "personal" ? c.personal : c.record, href: item.id === sampleExpenseStory.expense.id ? "#gastos-documentos" : item.account === "personal" ? "#money-tab-separation" : "#money-tab-movements" })),
    { id: "invoice-1024", label: `${c.invoice} 1024 · ${sampleInvoiceStory.customerName}`, amount: sampleInvoiceStory.invoice.amount, type: c.document, status: `${c.received} ${money(sampleInvoiceStory.payment)} · ${money(outstanding)} ${locale === "es" ? "pendiente" : "outstanding"}`, href: "#la-idea" },
    { id: sampleExpenseStory.receipt.id, label: sampleExpenseStory.receipt.filename, amount: sampleExpenseStory.expense.amount, type: c.document, status: c.linked, href: "#gastos-documentos" },
  ];
  const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const matches = records.filter((record) => normalize(`${record.label} ${record.id} ${record.amount}`).includes(normalize(query.trim())));
  const selected = records.find((record) => record.id === selectedRecord);
  return <section className={styles.section} id="registrar-encontrar" aria-labelledby="work-title">
    <div className={styles.heading}><p className={styles.eyebrow}>{c.eyebrow}</p><h2 id="work-title">{c.title}</h2><p>{c.intro}</p></div>
    <div className={styles.walkthrough}>
      <OwnerStoryControls id="work" label={c.title} steps={c.steps} selected={step} onSelect={setStep} />
      <div className={styles.panel} id="work-panel" data-state={step} role="tabpanel" aria-labelledby={`work-tab-${step}`} tabIndex={0}>
        <div className={styles.panelTop}><span>Cuadrao / {c.space}</span><span>{c.readiness}</span></div>
        <div className={styles.panelBody} key={step}>
          {step === "capture" && <>
            <div className={styles.inputMethods} role="group" aria-label={c.source}>{inputMethods.map((item) => <button type="button" key={item} aria-pressed={method === item} onClick={() => { setMethod(item); setCaptureState("preview"); }}>{c[item]}</button>)}</div>
            <div className={styles.sourceNote}><span>{c.source} · {c[method]}</span>{method === "file" || method === "photo" ? <><FileText size={23} aria-hidden="true" /><strong>internet-octubre.{method === "file" ? "pdf" : "jpg"}</strong><p>{personalExpense.label[locale]} · {money(personalExpense.amount)}</p></> : <p>“{c.entry.replace("{amount}", new Intl.NumberFormat(locale === "es" ? "es-DO" : "en-US").format(personalExpense.amount))}”</p>}{method === "voice" && <small>{c.transcript}</small>}</div>
            {captureState === "preview" ? <button type="button" className={styles.actionButton} onClick={() => setCaptureState("review")}>{c.review}<ArrowRight size={16} aria-hidden="true" /></button> : captureState === "review" ? <form className={styles.reviewForm} onSubmit={(event) => { event.preventDefault(); setCaptureState("confirmed"); }}>
              <h3>{c.reviewed}</h3><label htmlFor="capture-description">{c.concept}<input id="capture-description" value={description} onChange={(event) => setDescription(event.target.value)} required maxLength={100} /></label><div className={styles.formPair}><label htmlFor="capture-amount">{c.amount}<input id="capture-amount" type="number" min="0.01" step="0.01" required value={amount} onChange={(event) => setAmount(event.target.value)} /></label><label htmlFor="capture-category">{c.category}<select id="capture-category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="utilities">{c.utilities}</option><option value="supplies">{c.supplies}</option><option value="unclassified">{c.unclassified}</option></select></label></div><p className={styles.finePrint}>{c.space} · {c.paidFrom} {c.personal.toLowerCase()}. {c.original}</p><button className={styles.actionButton} type="submit">{c.confirm}<Check size={16} aria-hidden="true" /></button>
            </form> : <div className={styles.confirmation} role="status"><Check size={22} aria-hidden="true" /><h3>{c.confirmed}</h3><p>{description} · {money(Number(amount))}</p><p>{c.noSave}</p><button className={styles.textButton} type="button" onClick={() => setCaptureState("preview")}>{c.replay}</button></div>}
            <p className={styles.finePrint}>{c.methodNote}</p>
          </>}
          {step === "assistant" && <>
            <p className={styles.question}>{c.question}</p><div className={styles.answer}><span>Cuadrao</span><p>{c.answer} <strong>{money(outstanding)}.</strong></p><div className={styles.recordRow}><span>{c.from} 1024</span><b>{money(sampleInvoiceStory.invoice.amount)}</b></div><div className={styles.recordRow}><span>{c.received}</span><b>{money(sampleInvoiceStory.payment)}</b></div><a className={styles.textButton} href="#la-idea">{c.sourceLink}<ArrowRight size={16} aria-hidden="true" /></a></div>
            {reminderState === "preview" ? <button type="button" className={styles.actionButton} onClick={() => setReminderState("review")}>{c.propose}<Bell size={16} aria-hidden="true" /></button> : reminderState === "review" ? <form className={styles.reviewForm} onSubmit={(event) => { event.preventDefault(); setReminderState("confirmed"); }}><h3>{c.reviewed}</h3><label htmlFor="reminder-date">{c.date}<input id="reminder-date" type="date" value={reminderDate} required min="2026-10-06" onChange={(event) => setReminderDate(event.target.value)} /></label><label htmlFor="reminder-note">{c.note}<input id="reminder-note" value={reminderNote} required maxLength={160} onChange={(event) => setReminderNote(event.target.value)} /></label><button className={styles.actionButton} type="submit">{c.reminderConfirm}<Check size={16} aria-hidden="true" /></button></form> : <div className={styles.confirmation} role="status"><h3>{c.reminderSaved}</h3><p>{exampleDate(reminderDate, locale)} · {reminderNote}</p><p>{c.noReminder}</p><button type="button" className={styles.textButton} onClick={() => setReminderState("review")}>{c.review}</button></div>}
          </>}
          {step === "search" && <>
            {selected ? <><button id="search-back" type="button" className={styles.textButton} onClick={() => { setSelectedRecord(null); requestAnimationFrame(() => document.getElementById("record-search")?.focus()); }}><ArrowLeft size={16} aria-hidden="true" />{c.back}</button><div className={styles.searchDetail}><span>{c.opened} · {selected.id}</span><h3>{selected.label}</h3><strong>{money(selected.amount)}</strong><div className={styles.recordRow}><span>{c.status}</span><b>{selected.status}</b></div><a href={selected.href} className={styles.textButton}>{selected.type === c.document ? c.sourceReview : locale === "es" ? "Ver su contexto" : "View its context"}<ArrowRight size={16} aria-hidden="true" /></a></div></> : <><label className={styles.searchLabel} htmlFor="record-search">{c.search}<span><Search size={18} aria-hidden="true" /><input id="record-search" value={query} placeholder={c.placeholder} onChange={(event) => setQuery(event.target.value)} /></span></label><p className={styles.subtle} aria-live="polite">{matches.length} {c.results}</p><div className={styles.searchResults}>{matches.map((record) => <button type="button" key={record.id} onClick={() => { setSelectedRecord(record.id); requestAnimationFrame(() => document.getElementById("search-back")?.focus()); }}><span><strong>{record.label}</strong><small>{record.type} · {record.id}</small></span><b>{money(record.amount)}</b><ArrowRight size={15} aria-hidden="true" /></button>)}</div>{matches.length === 0 && <p className={styles.empty}>{c.noResults}</p>}</>}
          </>}
          {step === "updates" && <><h3>{c.current}</h3><div className={styles.updates}><article><Bell size={19} aria-hidden="true" /><h4>{c.due}</h4><p>{c.dueBody}</p><a className={styles.textButton} href="#planificar">{c.dueAction}<ArrowRight size={16} aria-hidden="true" /></a></article><article><FileText size={19} aria-hidden="true" /><h4>{c.missing}</h4><p>{c.missingBody}</p><a className={styles.textButton} href="#gastos-documentos">{c.missingAction}<ArrowRight size={16} aria-hidden="true" /></a></article><article><Check size={19} aria-hidden="true" /><h4>{c.reviewTitle}</h4><p>{c.reviewBody}</p><button type="button" className={styles.textButton} onClick={() => { setStep("assistant"); setReminderState("review"); requestAnimationFrame(() => document.getElementById("reminder-date")?.focus()); }}>{c.reviewAction}<ArrowRight size={16} aria-hidden="true" /></button></article></div><p className={styles.finePrint}>{c.noNotifications}</p></>}
        </div>
      </div>
    </div>
  </section>;
}
