"use client";

// Inicio's setup guide. The server owns the steps, which are required and whether each is done (GET /business/setup);
// this renders them and counts only what it was sent.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, Check, FileArrowUp, IdentificationCard, Scan, UsersThree, type Icon } from "@phosphor-icons/react";
import { ChevronRight } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { BusinessSetupStep, BusinessSetupStepKey } from "@/lib/business-setup-api";
import { useBusiness, type BusinessPanelState } from "../BusinessWorkspace";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { FOCUS_RING } from "../foundation/presentation";
import { cardClass, quietButtonClass } from "../business-ui";
import { setupOpen } from "./useBusinessSetup";

const STEP_ICON: Record<BusinessSetupStepKey, Icon> = { created: Briefcase, fiscal_identity: IdentificationCard, receiving_address: CHANNEL_ICON.email, receipt_reading: Scan, first_document: FileArrowUp, team: UsersThree, whatsapp: CHANNEL_ICON.whatsapp };
// The first document opens Agregar's own upload, not a Negocio tab.
const STEP_TARGET: Record<Exclude<BusinessSetupStepKey, "first_document">, BusinessPanelState> = {
  created: { kind: "business", tab: "datos" }, fiscal_identity: { kind: "business", tab: "datos" }, receiving_address: { kind: "business", tab: "correo" },
  receipt_reading: { kind: "business", tab: "correo" }, team: { kind: "business", tab: "equipo" }, whatsapp: { kind: "business", tab: "correo" },
};
// The shared Business card (cardClass), without its padding. Read at render: business-ui sits in an import cycle.
const surface = () => cardClass.replace(/\bp-5\b/, "").trim();
const MUTED = "text-[#56635e] dark:text-white/70";
const ROW = `flex min-h-11 w-full items-center gap-3 rounded-item px-4 py-4 text-left transition-colors duration-[80ms] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] ${FOCUS_RING}`;

/**
 * Where the guide stands: a Business with no required step done past its creation leads Inicio with its steps;
 * one already under way keeps a compact entry beside the work. Null once setup is complete: no guide at all.
 */
export function setupPlacement(steps: readonly BusinessSetupStep[] | null): "lead" | "entry" | null {
  if (!setupOpen(steps)) return null;
  return steps.some((step) => step.required && step.done && step.key !== "created") ? "entry" : "lead";
}

/** A compact neutral ring with `n / n` in its center (Guide readiness rules). */
function ProgressRing({ done, total, label }: { done: number; total: number; label: string }) {
  const r = 19; const c = 2 * Math.PI * r;
  return (
    <span role="img" aria-label={label} className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center">
      <svg viewBox="0 0 44 44" className="absolute inset-0" aria-hidden="true">
        <circle cx="22" cy="22" r={r} fill="none" strokeWidth="3" className="stroke-black/10 dark:stroke-white/15" />
        <circle cx="22" cy="22" r={r} fill="none" strokeWidth="3" strokeLinecap="round" strokeDasharray={`${(done / total) * c} ${c}`} transform="rotate(-90 22 22)" className="stroke-[#172b26] dark:stroke-white" />
      </svg>
      <span aria-hidden="true" className="text-[12px] font-medium tabular-nums">{done}/{total}</span>
    </span>
  );
}

function StepRow({ step, onOpen }: { step: BusinessSetupStep; onOpen: (step: BusinessSetupStep) => void }) {
  const { t } = useTranslation();
  const StepIcon = STEP_ICON[step.key];
  const title = t(`business.home_setup.steps.${step.key}.title`);
  if (step.done) {
    // A finished step is a quiet row: muted title and a check, no description.
    return (
      <button type="button" data-testid={`home-setup-step-${step.key}`} data-done="" onClick={() => onOpen(step)} className={`${ROW} ${MUTED}`}>
        <StepIcon size={20} aria-hidden="true" className="shrink-0" />
        <span className="min-w-0 flex-1 text-[16px]">{title}</span>
        <Check size={18} weight="bold" aria-label={t("business.home_setup.progress", { done: 1, total: 1 })} className="shrink-0 text-[var(--cuadrao-green)]" />
      </button>
    );
  }
  return (
    <button type="button" data-testid={`home-setup-step-${step.key}`} onClick={() => onOpen(step)} className={`${surface()} ${ROW} !px-4 !py-4`}>
      <StepIcon size={20} aria-hidden="true" className="shrink-0 self-start text-[#172b26] dark:text-white" />
      <span className="min-w-0 flex-1"><span className="block text-[16px] font-medium">{title}</span><span className={`mt-0.5 block text-[14px] ${MUTED}`}>{t(`business.home_setup.steps.${step.key}.body`)}</span></span>
      <ChevronRight aria-hidden="true" className={`h-4 w-4 shrink-0 ${MUTED}`} />
    </button>
  );
}

/** Setup lives apart from the work: the lead card or a compact entry on Inicio, every step in a side panel (a full sheet on a phone). */
export function GuidedSetup({ steps, placement }: { steps: readonly BusinessSetupStep[]; placement: "lead" | "entry" }) {
  const { openPanel, actions, chosen } = useBusiness();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const required = steps.filter((step) => step.required);
  const optional = steps.filter((step) => !step.required);
  const done = required.filter((step) => step.done).length;
  const progress = t("business.home_setup.progress", { done, total: required.length });
  const title = t("business.home_setup.title");
  const upload = chosen?.role !== "accountant" ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  const go = (step: BusinessSetupStep) => {
    setOpen(false);
    if (step.key === "first_document") upload?.run();
    else openPanel(STEP_TARGET[step.key]);
  };
  const panel = open ? (
    <AdaptivePanel title={title} summary={progress} onClose={() => setOpen(false)} closeLabel={t("common.close")} width="md" snaps={["full"]} initialSnap="full">
      <div className="space-y-3 px-5 pb-6 pt-2" data-testid="home-setup-panel">
        <p className={`text-[16px] ${MUTED}`}>{t("business.home_setup.lead")}</p>
        {required.map((step) => <StepRow key={step.key} step={step} onOpen={go} />)}
        {optional.length ? <h3 className={`pt-3 text-[14px] font-medium ${MUTED}`}>{t("business.home_setup.optional")}</h3> : null}
        {optional.map((step) => <StepRow key={step.key} step={step} onOpen={go} />)}
      </div>
    </AdaptivePanel>
  ) : null;
  if (placement === "lead") {
    // A brand-new Business: setup is the main job, so it leads Inicio with its open steps.
    return (
      <section className={`${surface()} p-5`} data-testid="home-setup-new">
        <div className="flex items-start gap-4">
          <span className="min-w-0 flex-1"><h3 className="font-display text-[21px] font-medium">{title}</h3><p className={`mt-1 text-[16px] ${MUTED}`}>{t("business.home_setup.lead")}</p></span>
          <ProgressRing done={done} total={required.length} label={progress} />
        </div>
        <div className="mt-4 space-y-3">{required.filter((step) => !step.done).map((step) => <StepRow key={step.key} step={step} onOpen={go} />)}</div>
        <button type="button" className={`${quietButtonClass} mt-2 text-[14px]`} onClick={() => setOpen(true)}>{t("business.home_setup.see_all")}</button>
        {panel}
      </section>
    );
  }
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} data-testid="home-setup-entry" aria-haspopup="dialog" className={`${surface()} flex min-h-14 w-full items-center gap-3 px-3 py-[5px] text-left transition-colors duration-[80ms] hover:bg-white dark:hover:bg-[#25292c] ${FOCUS_RING}`}>
        <ProgressRing done={done} total={required.length} label={progress} />
        {/* One line: the ring carries "n de 4" (and its label), the steps left sit by the chevron. */}
        <span className="min-w-0 flex-1 truncate text-[16px] font-medium">{title}</span>
        <span className={`shrink-0 text-[14px] ${MUTED}`}>{t("business.home_setup.remaining", { count: required.length - done })}</span>
        <ChevronRight aria-hidden="true" className={`h-4 w-4 shrink-0 ${MUTED}`} />
      </button>
      {panel}
    </>
  );
}
