"use client";

import { useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Link2 } from "lucide-react";
import type { BusinessLocale } from "./content";
import { accountSummary, exampleAccounts, exampleDebt, exampleMoney, exampleMovements, movementCashEffect, type ExampleCurrency } from "./owner-example";
import { OwnerStoryControls } from "./owner-story-controls";
import styles from "./owner-stories.module.css";

type MoneyStep = "position" | "movements" | "separation";
const copy = {
  es: {
    title: "Saber dónde estás. Antes de decidir.", intro: "El dinero disponible, lo que entró, lo que gastaste y lo que aún debes. Cada cifra con los registros que la explican.",
    steps: [
      { id: "position", title: "Una vista de tu dinero", body: "Cuentas y caja, ingresos, gastos y deudas. Los pesos y los dólares conservan su propia cuenta." },
      { id: "movements", title: "De la cifra al movimiento", body: "Mira qué cambió. Un aporte de la dueña aumenta la caja, pero no se convierte en una venta." },
      { id: "separation", title: "Lo personal, por su lado", body: "Si pagas algo del negocio con tu dinero, quedan dos registros relacionados. Cada espacio conserva sus cuentas." },
    ],
    eyebrow: "01 / ENTENDER TU DINERO", readiness: "Vista prevista · datos ficticios", date: "Al 6 de octubre de 2026", cash: "Dinero registrado", opening: "Saldo al iniciar el ejemplo", change: "Cambio registrado", income: "Ingresos cobrados", expenses: "Gastos del negocio", debt: "Deuda pendiente", detail: "Ver movimientos", noFeed: "Saldos del ejemplo. No hay conexión bancaria ni conversión entre monedas.",
    movement: "Movimiento", impact: "Efecto en caja", personal: "Pagado personalmente", ownerContribution: "Aporte, no venta", ownerWithdrawal: "Retiro, no gasto", expense: "Gasto", payment: "Cobro", cashExplain: "El gasto del negocio pagado personalmente no reduce la caja del negocio.",
    separationTitle: "Un pago, dos contextos.", business: "Negocio", personalSpace: "Personal", businessEntry: "Gasto del local pagado por la dueña", personalEntry: "Salida personal para el negocio", pairNote: "Dos registros vinculados. El gasto pertenece al negocio; el dinero salió de la cuenta personal. No se mezcla con el consumo personal.",
    ownerTitle: "También el dinero que pones y retiras", ownerNote: "Aportes y retiros conservan su motivo y su relación entre espacios. No inflan las ventas ni los gastos operativos.",
  },
  en: {
    title: "Know where you stand. Then decide.", intro: "Available money, what came in, what you spent and what you still owe. Each number connected to the records behind it.",
    steps: [
      { id: "position", title: "One view of your money", body: "Accounts and cash, income, expenses and debt. Pesos and dollars keep their own balances." },
      { id: "movements", title: "From a number to its records", body: "See what changed. An owner contribution increases cash without becoming a sale." },
      { id: "separation", title: "Keep personal money separate", body: "Pay a business cost with your money and keep two linked records. Each space keeps its own accounts." },
    ],
    eyebrow: "01 / UNDERSTAND YOUR MONEY", readiness: "Planned view · fictional data", date: "As of October 6, 2026", cash: "Recorded money", opening: "Opening sample balance", change: "Recorded change", income: "Income received", expenses: "Business expenses", debt: "Outstanding debt", detail: "View movements", noFeed: "Sample balances. No bank connection or currency conversion.",
    movement: "Movement", impact: "Cash effect", personal: "Paid personally", ownerContribution: "Contribution, not a sale", ownerWithdrawal: "Withdrawal, not an expense", expense: "Expense", payment: "Payment received", cashExplain: "The personally paid cost is a business expense, but does not reduce business cash.",
    separationTitle: "One payment, two contexts.", business: "Business", personalSpace: "Personal", businessEntry: "Shop expense paid by the owner", personalEntry: "Personal money paid for the business", pairNote: "Two linked records. The business owns the expense; the money left the personal account. It stays separate from personal consumption.",
    ownerTitle: "The money you put in and take out, too", ownerNote: "Contributions and withdrawals retain their purpose and link between spaces. They do not inflate sales or operating expenses.",
  },
} as const;

export function MoneyStory({ locale }: { locale: BusinessLocale }) {
  const c = copy[locale];
  const [step, setStep] = useState<MoneyStep>("position");
  const [currency, setCurrency] = useState<ExampleCurrency>("DOP");
  useEffect(() => {
    function openLinkedView() {
      if (window.location.hash === "#money-tab-movements") setStep("movements");
      if (window.location.hash === "#money-tab-separation") setStep("separation");
    }
    openLinkedView();
    function onLink(event: MouseEvent) {
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (link?.getAttribute("href") === "#money-tab-movements") setStep("movements");
      if (link?.getAttribute("href") === "#money-tab-separation") setStep("separation");
    }
    window.addEventListener("hashchange", openLinkedView);
    document.addEventListener("click", onLink);
    return () => { window.removeEventListener("hashchange", openLinkedView); document.removeEventListener("click", onLink); };
  }, []);
  const summary = accountSummary(currency);
  const money = (amount: number) => exampleMoney(amount, currency, locale);
  const personallyPaid = exampleMovements.find((item) => item.account === "personal")!;
  return <section className={styles.section} id="el-producto" aria-labelledby="money-title">
    <div className={styles.heading}><p className={styles.eyebrow}>{c.eyebrow}</p><h2 id="money-title">{c.title}</h2><p>{c.intro}</p></div>
    <div className={styles.walkthrough}>
      <OwnerStoryControls id="money" label={c.title} steps={c.steps} selected={step} onSelect={setStep} />
      <div className={`${styles.panel} ${styles.moneyPanel}`} id="money-panel" data-state={step} role="tabpanel" aria-labelledby={`money-tab-${step}`} tabIndex={0}>
        <div className={styles.panelTop}><span>Cuadrao / {c.business}</span><span>{c.readiness}</span></div>
        <div className={styles.panelBody} key={step}>
          {step !== "separation" && <div className={styles.contextBar}><span>{c.date}</span><div className={styles.segmented} role="group" aria-label={locale === "es" ? "Moneda del ejemplo" : "Sample currency"}>{exampleAccounts.map((account) => <button type="button" key={account.currency} aria-pressed={currency === account.currency} onClick={() => setCurrency(account.currency)}>{account.currency}</button>)}</div></div>}
          {step === "position" && <>
            <div className={styles.balance}><span>{c.cash}</span><strong>{money(summary.cash)}</strong><small>{exampleAccounts.find((account) => account.currency === currency)!.label[locale]}</small></div>
            <div className={styles.reconciliation}><span>{c.opening}<b>{money(summary.opening)}</b></span><span>{c.change}<b>+{money(summary.change)}</b></span></div>
            <div className={styles.metrics}><div><ArrowDownLeft size={18} aria-hidden="true" /><span>{c.income}</span><strong>{money(summary.income)}</strong></div><div><ArrowUpRight size={18} aria-hidden="true" /><span>{c.expenses}</span><strong>{money(summary.expenses)}</strong></div><div><span>{c.debt}</span><strong>{money(currency === "DOP" ? exampleDebt.balance : 0)}</strong></div></div>
            <button className={styles.textButton} type="button" onClick={() => setStep("movements")}>{c.detail}<ArrowUpRight size={16} aria-hidden="true" /></button>
            <p className={styles.finePrint}>{c.noFeed}</p>
          </>}
          {step === "movements" && <>
            <div className={styles.tableHeading}><span>{c.movement}</span><span>{c.impact}</span></div>
            <div className={styles.recordList}>{exampleMovements.filter((item) => item.currency === currency).map((item) => <div className={styles.recordRow} key={item.id}><span><strong>{item.label[locale]}</strong><small>{item.account === "personal" ? c.personal : item.kind === "owner-contribution" ? c.ownerContribution : item.kind === "owner-withdrawal" ? c.ownerWithdrawal : item.kind === "income" ? c.payment : c.expense}</small></span><b>{movementCashEffect(item) > 0 ? "+" : ""}{money(movementCashEffect(item))}</b></div>)}</div>
            {currency === "USD" ? <p className={styles.empty}>{locale === "es" ? "Sin movimientos en dólares en este ejemplo. El saldo inicial se mantiene." : "No dollar movements in this example. The opening balance stays unchanged."}</p> : <p className={styles.finePrint}>{c.cashExplain}</p>}
            <div className={styles.totalLine}><span>{c.cash}</span><strong>{money(summary.cash)}</strong></div>
          </>}
          {step === "separation" && <>
            <h3>{c.separationTitle}</h3><p className={styles.panelLead}>{personallyPaid.label[locale]} · {exampleMoney(personallyPaid.amount, personallyPaid.currency, locale)}</p>
            <div className={styles.linkedSpaces}><div><span>{c.business}</span><strong>{c.businessEntry}</strong><small>{personallyPaid.id}</small><b>{exampleMoney(personallyPaid.amount, personallyPaid.currency, locale)}</b></div><Link2 size={22} aria-hidden="true" /><div><span>{c.personalSpace}</span><strong>{c.personalEntry}</strong><small>{personallyPaid.account === "personal" ? personallyPaid.linkedId : ""}</small><b>−{exampleMoney(personallyPaid.amount, personallyPaid.currency, locale)}</b></div></div>
            <p className={styles.finePrint}>{c.pairNote}</p><div className={styles.inset}><h4>{c.ownerTitle}</h4>{exampleMovements.filter((item) => item.kind === "owner-contribution" || item.kind === "owner-withdrawal").map((item) => <div className={styles.recordRow} key={item.id}><span>{item.label[locale]}</span><b>{movementCashEffect(item) > 0 ? "+" : ""}{exampleMoney(movementCashEffect(item), item.currency, locale)}</b></div>)}<p>{c.ownerNote}</p></div>
          </>}
        </div>
      </div>
    </div>
  </section>;
}
