"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { ArrowRight, Check, CircleDashed, FileText, Link2, Receipt } from "lucide-react";
import type { BusinessLocale } from "./content";
import { formatSampleMoney } from "./sample-data";
import { sampleExpenseStory, samplePriorities, priorityName } from "./sample-priorities";
import styles from "./business-stories.module.css";

type ExpenseStep = "missing" | "review" | "linked";
const steps: readonly ExpenseStep[] = ["missing", "review", "linked"];
const copy = {
  es: {
    label: "DETALLE / GASTOS Y DOCUMENTOS", title: "El gasto ya está. Falta su respaldo.",
    intro: "Un recibo no debería perderse después de pagar. Recorre este ejemplo de cómo queremos reunirlo con el gasto que explica.",
    steps: {
      missing: ["Encuentra lo que falta", "El gasto de transporte está anotado. Su comprobante todavía no está junto al registro."],
      review: ["Revisa el documento", "Una foto o un archivo daría lugar a una propuesta. Revisa el original, el monto y el registro sugerido antes de confirmar."],
      linked: ["Déjalo organizado", "El comprobante queda junto al gasto existente. Adjuntarlo no cuenta el dinero por segunda vez."],
    },
    note: "Vista prevista · datos de ejemplo",
    manual: "Registro manual", missing: "Falta comprobante", review: "Propuesta por revisar", linked: "Comprobante relacionado",
    record: "Registro del gasto", receipt: "Recibo de transporte", supplier: "Proveedor", date: "Fecha", amount: "Monto", concept: "Concepto", source: "Documento de ejemplo, sin validez fiscal",
    intake: "Entrada prevista: foto o archivo. También podrás registrar el gasto manualmente.",
    retained: "El gasto permanece registrado. Falta reunir su evidencia.",
    compare: "Compara el original con la propuesta", match: "Registro existente sugerido", approval: "La persona revisa y confirma la relación.",
    organized: "Un gasto. Su comprobante. La misma cantidad.", noDuplicate: "El documento respalda el gasto registrado; no crea otro gasto.",
    accountant: "Revisar antes de cerrar el período.", accountantBody: "Reportes por período y un paquete de registros y documentos para compartir con tu contador. Lo que falta revisar debe seguir visible.",
    expenseCheck: "Gasto de transporte", completed: "Con comprobante", incomplete: "Comprobante por revisar", supplierCheck: "Pago al proveedor", pending: "Fecha por confirmar", prepNote: "Preparación prevista. Este ejemplo no exporta archivos ni completa una revisión contable.",
    next: "Ver siguiente paso", replay: "Volver al inicio", pendingLink: "Volver a los pendientes",
  },
  en: {
    label: "DETAIL / EXPENSES AND DOCUMENTS", title: "The expense is there. Its receipt is missing.",
    intro: "A receipt should not get lost after you pay. Explore how we plan to keep it with the expense it explains.",
    steps: {
      missing: ["Find what is missing", "The transport expense is recorded. Its receipt is not with the record yet."],
      review: ["Review the document", "A photo or file would become a proposal. Check the original, amount and suggested record before confirming."],
      linked: ["Keep it organized", "The receipt stays with the existing expense. Attaching it does not count the money a second time."],
    },
    note: "Planned view · sample data",
    manual: "Manual record", missing: "Receipt needed", review: "Proposal to review", linked: "Receipt linked",
    record: "Expense record", receipt: "Transport receipt", supplier: "Supplier", date: "Date", amount: "Amount", concept: "Description", source: "Sample document, not valid for tax purposes",
    intake: "Planned input: photo or file. Manual expense entry will also be available.",
    retained: "The expense stays recorded. Its evidence still needs to be gathered.",
    compare: "Compare the original with the proposal", match: "Suggested existing record", approval: "The person reviews and confirms the link.",
    organized: "One expense. Its receipt. The same amount.", noDuplicate: "The document supports the recorded expense; it does not create another one.",
    accountant: "Review before closing the period.", accountantBody: "Period reports and a package of records and documents to share with your accountant. Items still needing review should stay visible.",
    expenseCheck: "Transport expense", completed: "Receipt attached", incomplete: "Receipt needs review", supplierCheck: "Supplier payment", pending: "Date to confirm", prepNote: "Planned preparation. This example does not export files or complete an accounting review.",
    next: "View next step", replay: "Back to the start", pendingLink: "Back to open items",
  },
} as const;

export function ExpenseStory({ locale }: { locale: BusinessLocale }) {
  const c = copy[locale];
  const [step, setStep] = useState<ExpenseStep>("missing");
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const example = sampleExpenseStory;
  const supplierPayment = samplePriorities.find((priority) => priority.kind === "payable")!;
  const money = formatSampleMoney(example.expense.amount, locale);
  const reference = example.expense.id.replace("expense-", "");
  const status = c[step];
  function onKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === "ArrowDown" || event.key === "ArrowRight" ? (index + 1) % steps.length
      : event.key === "ArrowUp" || event.key === "ArrowLeft" ? (index + steps.length - 1) % steps.length
      : event.key === "Home" ? 0 : event.key === "End" ? steps.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    setStep(steps[next]);
    buttons.current[next]?.focus();
  }
  return <section className={styles.expense} id="gastos-documentos" aria-labelledby="expense-title">
    <div className={styles.expenseHeading}><p className={styles.index}>{c.label}</p><h2 id="expense-title">{c.title}</h2><p>{c.intro}</p></div>
    <div className={styles.walkthrough}>
      <div className={styles.explanation}>
        <div className={styles.stepList} role="tablist" aria-orientation="vertical" aria-label={c.title}>
          {steps.map((item, index) => <button type="button" role="tab" key={item} id={`expense-tab-${item}`} aria-controls="expense-panel" aria-selected={step === item} tabIndex={step === item ? 0 : -1} ref={(node) => { buttons.current[index] = node; }} onClick={() => setStep(item)} onKeyDown={(event) => onKey(event, index)}>
            <span className={styles.stepNumber}>{String(index + 1).padStart(2, "0")}</span>
            <span><strong>{c.steps[item][0]}</strong><small>{c.steps[item][1]}</small></span>
          </button>)}
        </div>
        <p className={styles.intake}><FileText size={18} aria-hidden="true" />{c.intake}</p>
      </div>
      <div className={styles.example} id="expense-panel" role="tabpanel" aria-labelledby={`expense-tab-${step}`} tabIndex={0} data-step={step}>
        <div className={styles.exampleTop}><span>{c.record} · {reference}</span><span>{step === "linked" ? <Check size={14} aria-hidden="true" /> : <CircleDashed size={14} aria-hidden="true" />}{status}</span></div>
        <div className={styles.exampleBody} key={step}>
          {step === "missing" ? <div className={styles.missingRecord}>
            <span className={styles.recordIcon}><Receipt size={24} strokeWidth={1.4} aria-hidden="true" /></span>
            <small>{c.manual}</small><h3>{example.expense.expense[locale]}</h3><p className={styles.expenseAmount}>{money}</p>
            <dl><div><dt>{c.date}</dt><dd>{example.receipt.date[locale]}</dd></div><div><dt>{c.concept}</dt><dd>{example.expense.expense[locale]}</dd></div></dl>
            <div className={styles.emptyReceipt}><FileText size={22} aria-hidden="true" /><span>{c.missing}<small>{c.retained}</small></span></div>
          </div> : <>
            <p className={styles.panelLead}>{step === "review" ? c.compare : c.organized}</p>
            <div className={styles.documentPair}>
              <div className={styles.receiptPaper}>
                <FileText size={21} aria-hidden="true" /><small>{c.receipt}</small><h3>{example.receipt.supplier}</h3><span>{example.receipt.id}</span>
                <dl><div><dt>{c.date}</dt><dd>{example.receipt.date[locale]}</dd></div><div><dt>{c.concept}</dt><dd>{example.expense.expense[locale]}</dd></div></dl>
                <p>{money}</p><small className={styles.fiscalNote}>{c.source}</small>
              </div>
              <div className={styles.proposal}>
                <span>{step === "review" ? c.review : c.linked}</span>
                <dl><div><dt>{c.supplier}</dt><dd>{example.receipt.supplier}</dd></div><div><dt>{c.date}</dt><dd>{example.receipt.date[locale]}</dd></div><div><dt>{c.amount}</dt><dd>{money}</dd></div></dl>
                <div className={styles.linkedRecord}><Link2 size={17} aria-hidden="true" /><small>{step === "review" ? c.match : c.record}</small><strong>{example.expense.expense[locale]} · {reference}</strong><span>{money}</span></div>
              </div>
            </div>
            <p className={styles.reviewNote}>{step === "review" ? c.approval : c.noDuplicate}</p>
          </>}
        </div>
        <div className={styles.exampleBottom}><span>{c.note}</span><button type="button" onClick={() => setStep(steps[(steps.indexOf(step) + 1) % steps.length])}>{step === "linked" ? c.replay : c.next}<ArrowRight size={17} aria-hidden="true" /></button></div>
      </div>
    </div>
    <div className={styles.preparation} id="preparar-registros">
      <div><h3>{c.accountant}</h3><p>{c.accountantBody}</p><small>{c.prepNote}</small></div>
      <div className={styles.reviewList}>
        <div><span>{step === "linked" ? <Check size={17} aria-hidden="true" /> : <CircleDashed size={17} aria-hidden="true" />}<strong>{c.expenseCheck}</strong><small>{money}</small></span><span>{step === "linked" ? c.completed : step === "missing" ? c.missing : c.incomplete}</span></div>
        <div><span><CircleDashed size={17} aria-hidden="true" /><strong>{c.supplierCheck}</strong><small>{priorityName(supplierPayment, locale)}</small></span><span>{c.pending}</span></div>
        <a href="#el-producto">{c.pendingLink}<ArrowRight size={16} aria-hidden="true" /></a>
      </div>
    </div>
  </section>;
}
