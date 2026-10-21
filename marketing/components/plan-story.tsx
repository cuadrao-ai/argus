"use client";

import { useEffect, useState } from "react";
import { ArrowRight, CalendarDays, Flag } from "lucide-react";
import type { BusinessLocale } from "./content";
import { accountSummary, budgetActual, exampleBudgets, exampleDate, exampleDebt, exampleExpectations, exampleGoal, exampleMoney, projectedCash } from "./owner-example";
import { OwnerStoryControls } from "./owner-story-controls";
import styles from "./owner-stories.module.css";

type PlanStep = "upcoming" | "budgets" | "outlook";
const copy = {
  es: {
    eyebrow: "02 / PLANEAR LO QUE SIGUE", title: "Que el próximo pago no te tome por sorpresa.", intro: "Ver lo que viene, poner límites y probar una decisión antes de tomarla. Estamos adaptando los planes de Cuadrao al trabajo del negocio.",
    steps: [
      { id: "upcoming", title: "Cobros y compromisos próximos", body: "Pagos con fecha, cuotas y cobros esperados en los próximos 30 días. Lo esperado no se suma al dinero recibido." },
      { id: "budgets", title: "Presupuestos, metas y deudas", body: "Compara lo gastado con tu presupuesto. Aparta una meta y sigue un plan de deuda sin perder de vista los compromisos." },
      { id: "outlook", title: "¿Y si el cobro se retrasa?", body: "Prueba cómo cambia la caja prevista. Una simulación cambia el plan que estás mirando, nunca los saldos registrados." },
    ],
    readiness: "Vista prevista · ejemplo", upcoming: "Próximos 30 días", horizon: "7 oct. a 5 nov. · solo DOP", expected: "Cobro esperado", scheduled: "Pago previsto", moneyNow: "Dinero registrado hoy", note: "Una fecha no confirma un pago. Cada cobro o salida necesitará su movimiento real.",
    budgets: "Presupuesto del ejemplo", category: "Categoría", planned: "Límite", actual: "Gastado", remaining: "Disponible", goal: "Meta", saved: "Reservado dentro del saldo", debt: "Plan de deuda", balance: "Pendiente", installment: "Cuota prevista", goalNote: "Reservar una meta no cuenta como gasto. La cuota ya aparece en los próximos pagos.",
    baseline: "Con el cobro el 12 de octubre", delay: "Si llega el 12 de noviembre", outlook: "Caja prevista al 5 de noviembre", effect: "Diferencia por el retraso", scenario: "Escenario hipotético", schedule: "Según las fechas del ejemplo", caution: "Proyección de estos compromisos, no un pronóstico completo. No incluye ventas nuevas ni gastos que aún no has registrado.", unchanged: "Dinero registrado sin cambios", action: "Revisar el cobro de La Ceiba", noSave: "Este escenario no guarda movimientos ni cambia fechas reales.",
  },
  en: {
    eyebrow: "02 / PLAN WHAT COMES NEXT", title: "See the next payment before it arrives.", intro: "See what is coming, set limits and try a decision before making it. We are adapting Cuadrao planning to the work of a business.",
    steps: [
      { id: "upcoming", title: "Upcoming money and commitments", body: "Dated payments, installments and expected income over the next 30 days. Expected money is separate from received money." },
      { id: "budgets", title: "Budgets, goals and debt", body: "Compare spending with your budget. Set money aside for a goal and follow a debt plan while keeping commitments in view." },
      { id: "outlook", title: "What if the customer pays late?", body: "Try how projected cash changes. A scenario changes the plan you are viewing, never your recorded balances." },
    ],
    readiness: "Planned view · sample", upcoming: "Next 30 days", horizon: "Oct 7 to Nov 5 · DOP only", expected: "Expected income", scheduled: "Scheduled payment", moneyNow: "Recorded money today", note: "A date does not confirm a payment. Each inflow or outflow will need its actual movement.",
    budgets: "Sample budget", category: "Category", planned: "Limit", actual: "Spent", remaining: "Remaining", goal: "Goal", saved: "Reserved within the balance", debt: "Debt plan", balance: "Outstanding", installment: "Planned installment", goalNote: "Reserving money for a goal is not spending. The installment is already in upcoming payments.",
    baseline: "Payment arrives on October 12", delay: "Payment arrives on November 12", outlook: "Projected cash on November 5", effect: "Difference from the delay", scenario: "Hypothetical scenario", schedule: "Using the sample dates", caution: "A projection of these commitments, not a complete forecast. It excludes new sales and expenses you have not yet recorded.", unchanged: "Recorded money stays unchanged", action: "Review the La Ceiba balance", noSave: "This scenario does not save movements or change actual dates.",
  },
} as const;

export function PlanStory({ locale }: { locale: BusinessLocale }) {
  const c = copy[locale];
  const [step, setStep] = useState<PlanStep>("upcoming");
  const [delayed, setDelayed] = useState(false);
  useEffect(() => {
    function openUpcoming() {
      if (window.location.hash === "#planificar") setStep("upcoming");
    }
    function onLink(event: MouseEvent) {
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (link?.getAttribute("href") === "#planificar") setStep("upcoming");
    }
    window.addEventListener("hashchange", openUpcoming);
    document.addEventListener("click", onLink);
    return () => { window.removeEventListener("hashchange", openUpcoming); document.removeEventListener("click", onLink); };
  }, []);
  const money = (amount: number) => exampleMoney(amount, "DOP", locale);
  const cash = accountSummary("DOP").cash;
  const projected = projectedCash(delayed);
  return <section className={`${styles.section} ${styles.planning}`} id="planificar" aria-labelledby="plan-title">
    <div className={styles.heading}><p className={styles.eyebrow}>{c.eyebrow}</p><h2 id="plan-title">{c.title}</h2><p>{c.intro}</p></div>
    <div className={styles.walkthrough}>
      <OwnerStoryControls id="plan" label={c.title} steps={c.steps} selected={step} onSelect={setStep} />
      <div className={styles.panel} id="plan-panel" data-state={step} role="tabpanel" aria-labelledby={`plan-tab-${step}`} tabIndex={0}>
        <div className={styles.panelTop}><span>Cuadrao / Plan</span><span>{c.readiness}</span></div>
        <div className={styles.panelBody} key={step}>
          {step === "upcoming" && <>
            <div className={styles.contextBar}><h3>{c.upcoming}</h3><CalendarDays size={20} aria-hidden="true" /></div><p className={styles.subtle}>{c.horizon}</p>
            <div className={styles.timeline}>{exampleExpectations.map((item) => <div className={styles.timelineRow} key={item.id}><span className={styles.date}>{exampleDate(item.date, locale)}</span><span><strong>{item.label[locale]}</strong><small>{item.status === "expected" ? c.expected : c.scheduled}</small></span><b>{item.direction === "in" ? "+" : "−"}{money(item.amount)}</b></div>)}</div>
            <div className={styles.totalLine}><span>{c.moneyNow}</span><strong>{money(cash)}</strong></div><p className={styles.finePrint}>{c.note}</p>
          </>}
          {step === "budgets" && <>
            <h3>{c.budgets}</h3><div className={styles.budgetTable} role="table" aria-label={c.budgets}>
              <div role="row"><span role="columnheader">{c.category}</span><span role="columnheader">{c.planned}</span><span role="columnheader">{c.actual}</span><span role="columnheader">{c.remaining}</span></div>
              {exampleBudgets.map((item) => <div role="row" key={item.label.es}><strong role="cell">{item.label[locale]}</strong><span role="cell" data-label={c.planned}>{money(item.limit)}</span><span role="cell" data-label={c.actual}>{money(budgetActual(item.movementIds))}</span><span role="cell" data-label={c.remaining}>{money(item.limit - budgetActual(item.movementIds))}</span></div>)}
            </div>
            <div className={styles.planPair}><div><span><Flag size={15} aria-hidden="true" />{c.goal}</span><h4>{exampleGoal.label[locale]}</h4><strong>{money(exampleGoal.saved)} <small>/ {money(exampleGoal.target)}</small></strong><progress value={exampleGoal.saved} max={exampleGoal.target} aria-label={exampleGoal.label[locale]} /><small>{c.saved}</small></div><div><span>{c.debt}</span><h4>{exampleDebt.label[locale]}</h4><strong>{money(exampleDebt.balance)}</strong><small>{c.balance}</small><p>{c.installment}<br /><b>{money(exampleDebt.installment)}</b> · {exampleDate(exampleDebt.date, locale)}</p></div></div>
            <p className={styles.finePrint}>{c.goalNote}</p>
          </>}
          {step === "outlook" && <>
            <div className={styles.scenarioChoices} role="group" aria-label={c.scenario}><button type="button" aria-pressed={!delayed} onClick={() => setDelayed(false)}>{c.baseline}</button><button type="button" aria-pressed={delayed} onClick={() => setDelayed(true)}>{c.delay}</button></div>
            <div className={styles.projection} aria-live="polite"><span>{delayed ? c.scenario : c.schedule}</span><strong>{money(projected)}</strong><p>{c.outlook}</p><div className={styles.cashTrack}><span style={{ width: `${projected / cash * 100}%` }} /></div><small>{c.effect} <b>{money(projected - projectedCash(false))}</b></small></div>
            <div className={styles.totalLine}><span>{c.unchanged}</span><strong>{money(cash)}</strong></div><p className={styles.finePrint}>{c.caution}</p><a className={styles.textButton} href="#la-idea">{c.action}<ArrowRight size={16} aria-hidden="true" /></a><p className={styles.finePrint}>{c.noSave}</p>
          </>}
        </div>
      </div>
    </div>
  </section>;
}
