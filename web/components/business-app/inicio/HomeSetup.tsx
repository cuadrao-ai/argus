"use client";

// Configurar negocio: a small card at the foot of the sidebar and the dossier it opens. The server owns the steps,
// which are required and whether each is done (GET /business/setup); this renders them and counts only what it was
// sent.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, Check, FileArrowUp, IdentificationCard, Scan, UsersThree, type Icon } from "@phosphor-icons/react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { BusinessSetupStep, BusinessSetupStepKey } from "@/lib/business-setup-api";
import { useBusiness, type BusinessPanelState } from "../BusinessWorkspace";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { FOCUS_RING } from "../foundation/presentation";
import { setupOpen, useBusinessSetup } from "./useBusinessSetup";

const STEP_ICON: Record<BusinessSetupStepKey, Icon> = { created: Briefcase, fiscal_identity: IdentificationCard, receiving_address: CHANNEL_ICON.email, receipt_reading: Scan, first_document: FileArrowUp, team: UsersThree, whatsapp: CHANNEL_ICON.whatsapp };
// The first document opens Agregar's own upload, not a Negocio tab.
const STEP_TARGET: Record<Exclude<BusinessSetupStepKey, "first_document">, BusinessPanelState> = {
  created: { kind: "business", tab: "datos" }, fiscal_identity: { kind: "business", tab: "datos" }, receiving_address: { kind: "business", tab: "correo" },
  receipt_reading: { kind: "business", tab: "correo" }, team: { kind: "business", tab: "equipo" }, whatsapp: { kind: "business", tab: "correo" },
};
const MUTED = "text-[#56635e] dark:text-white/70";

/** A neutral ring with `done/total` in its center (Guide readiness rules). Decorative: its owner names the progress. */
function ProgressRing({ done, total, size = 44 }: { done: number; total: number; size?: number }) {
  const stroke = size > 60 ? 5 : 3;
  const r = (size - stroke) / 2 - 1;
  const c = 2 * Math.PI * r;
  return (
    <span aria-hidden="true" className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="absolute inset-0">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-black/10 dark:stroke-white/15" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${total ? (done / total) * c : 0} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} className="stroke-[#172b26] dark:stroke-white" />
      </svg>
      <span className={`font-medium tabular-nums text-[#172b26] dark:text-white ${size > 60 ? "font-display text-[21px]" : "text-[12px]"}`}>{done}/{total}</span>
    </span>
  );
}

function StepCard({ step, onOpen }: { step: BusinessSetupStep; onOpen: (step: BusinessSetupStep) => void }) {
  const { t } = useTranslation();
  const StepIcon = STEP_ICON[step.key];
  return (
    <button type="button" data-testid={`home-setup-step-${step.key}`} data-done={step.done ? "" : undefined} onClick={() => onOpen(step)}
      className={`block w-full rounded-item border border-[color:var(--surface-divider)] px-4 py-3 text-left transition-colors duration-[80ms] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] ${step.done ? "bg-[color:var(--surface-header)]" : "bg-white dark:bg-[#1f2225]"} ${FOCUS_RING}`}>
      <span className="flex items-center gap-2.5">
        <StepIcon size={20} aria-hidden="true" className={`shrink-0 ${step.done ? MUTED : "text-[#172b26] dark:text-white"}`} />
        <span className={`min-w-0 flex-1 text-[16px] font-medium ${step.done ? MUTED : "text-[#172b26] dark:text-white"}`}>{t(`business.home_setup.steps.${step.key}.title`)}</span>
        {step.done ? <Check size={18} weight="bold" aria-label={t("common.done")} className="shrink-0 text-[var(--cuadrao-green)]" /> : null}
      </span>
      <span className={`mt-1 block text-[14px] ${MUTED}`}>{t(`business.home_setup.steps.${step.key}.body`)}</span>
    </button>
  );
}

/**
 * The dossier: no header bar, a close X, a large centered ring, the title and one lead line, then the steps as cards:
 * open required ones first, then the optional ones under "Opcional", and every finished step last, muted, with a
 * check. A phone shows it as a full sheet.
 */
export function SetupDossier({ steps, onClose }: { steps: readonly BusinessSetupStep[]; onClose: () => void }) {
  const { openPanel, actions, chosen } = useBusiness();
  const { t } = useTranslation();
  const required = steps.filter((step) => step.required);
  const done = required.filter((step) => step.done).length;
  const open = steps.filter((step) => !step.done);
  const optional = open.filter((step) => !step.required);
  const finished = steps.filter((step) => step.done);
  const upload = chosen?.role !== "accountant" ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  const go = (step: BusinessSetupStep) => {
    onClose();
    if (step.key === "first_document") upload?.run();
    else openPanel(STEP_TARGET[step.key]);
  };
  return (
    <AdaptivePanel bare title={t("business.home_setup.title")} onClose={onClose} closeLabel={t("common.close")} width="md" snaps={["full"]} initialSnap="full">
      <div data-testid="home-setup-panel" className="px-5 pb-6 pt-8">
        <div className="flex flex-col items-center text-center">
          <span role="img" aria-label={t("business.home_setup.ring_label", { done, total: required.length })}><ProgressRing done={done} total={required.length} size={88} /></span>
          <p aria-hidden="true" className="mt-4 font-display text-[21px] font-medium text-[#172b26] dark:text-white">{t("business.home_setup.title")}</p>
          <p className={`mt-1 text-[16px] ${MUTED}`}>{t("business.home_setup.lead")}</p>
        </div>
        <div className="mt-6 space-y-3">
          {open.filter((step) => step.required).map((step) => <StepCard key={step.key} step={step} onOpen={go} />)}
          {optional.length ? <h3 className={`pt-3 text-[14px] font-medium ${MUTED}`}>{t("business.home_setup.optional")}</h3> : null}
          {optional.map((step) => <StepCard key={step.key} step={step} onOpen={go} />)}
          {finished.length ? <div data-testid="home-setup-finished" className="space-y-3 pt-3">{finished.map((step) => <StepCard key={step.key} step={step} onOpen={go} />)}</div> : null}
        </div>
      </div>
    </AdaptivePanel>
  );
}

/**
 * The sidebar's setup card, just above the Cuadrao mark: the ring, "Configurar negocio" and the steps left; on the
 * closed rail, the ring alone. Only someone who may manage the Business sees it, only while a required step is open,
 * for the selected Business; it leaves when the last required step is done. It stays highlighted while its dossier
 * is open.
 */
export function SidebarSetup({ collapsed }: { collapsed: boolean }) {
  const steps = useBusinessSetup();
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  if (!setupOpen(steps)) return null;
  const required = steps.filter((step) => step.required);
  const done = required.filter((step) => step.done).length;
  const ring = t("business.home_setup.ring_label", { done, total: required.length });
  const tone = open
    ? "border-[#2f5a49]/30 bg-[#e3ebe1] dark:border-white/20 dark:bg-white/10"
    : collapsed ? "border-transparent hover:bg-[#e3ebe1]/60 dark:hover:bg-white/5" : "border-[color:var(--surface-divider)] bg-white hover:bg-[#e3ebe1]/60 dark:bg-[#1f2225] dark:hover:bg-white/5";
  return (
    <>
      <button type="button" data-testid="sidebar-setup" data-open={open ? "true" : undefined} aria-haspopup="dialog" aria-expanded={open} aria-label={ring} onClick={() => setOpen(true)}
        className={`mb-2 flex w-full items-center gap-3 overflow-hidden rounded-item border text-left transition-colors duration-200 ${collapsed ? "justify-center p-0.5" : "px-2.5 py-2"} ${tone} ${FOCUS_RING}`}>
        <ProgressRing done={done} total={required.length} />
        {collapsed ? null : (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px] font-medium text-[#172b26] dark:text-white">{t("business.home_setup.title")}</span>
            <span className={`block truncate text-[13px] ${MUTED}`}>{t("business.home_setup.remaining", { count: required.length - done })}</span>
          </span>
        )}
      </button>
      {open ? <SetupDossier steps={steps} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
