"use client";

// Inicio's setup guide: Lucas's sketch (temp/home-setup/index.html) in React. The server owns the steps, which are
// required and whether each is done (GET /business/setup); this renders them and counts only what it was sent.
// Each step opens in place; its action is the live form that does the work, or the Negocio tab that holds it.

import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import WhatsAppLinkModal from "@/components/settings/WhatsAppLinkModal";
import { readStored, writeStored } from "@/lib/browser-storage";
import type { BusinessSetupStep, BusinessSetupStepKey } from "@/lib/business-setup-api";
import { useBusiness } from "../BusinessWorkspace";
import { BusinessEmailAddress } from "../BusinessEmailDeliveries";
import BusinessInvitationForm from "../BusinessInvitationForm";
import ReceiptReadingControl from "../ReceiptReadingControl";
import { formatBusinessName } from "../business-format";
import { primaryButtonClass, quietButtonClass } from "../business-ui";
import { setupOpen, type useBusinessSetup } from "./useBusinessSetup";
import styles from "./setup-guide.module.css";

const COLLAPSED_KEY = "cuadrao:setup_guide_collapsed:v1";

/**
 * A brand-new Business (nothing required done past its creation) opens with the guide expanded; one under way opens
 * it collapsed. The person's own choice wins and is kept per person and Business on this device.
 */
export function guideStartsCollapsed(steps: readonly BusinessSetupStep[]): boolean {
  return steps.some((step) => step.required && step.done && step.key !== "created");
}

function storedChoices(): Record<string, boolean> {
  try {
    const parsed: unknown = JSON.parse(readStored(COLLAPSED_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? (parsed as Record<string, boolean>) : {};
  } catch { return {}; }
}

function useCollapsed(scope: string, fallback: boolean): [boolean, (next: boolean) => void] {
  const [choice, setChoice] = useState<boolean | undefined>(() => storedChoices()[scope]);
  const choose = (next: boolean) => {
    setChoice(next);
    writeStored(COLLAPSED_KEY, JSON.stringify({ ...storedChoices(), [scope]: next }));
  };
  return [choice ?? fallback, choose];
}

const Check = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>;

/** The open step: what is true now and the one way to change it. */
function StepPanel({ step: { key: step, done }, onChanged }: { step: BusinessSetupStep; onChanged: () => void }) {
  const { t } = useTranslation();
  const { chosen, records, openPanel } = useBusiness();
  const [dossier, setDossier] = useState<"team" | "whatsapp" | null>(null);
  const close = () => { setDossier(null); onChanged(); };
  const name = formatBusinessName(chosen?.name, t("business.overview.title"));
  const datos = () => openPanel({ kind: "business", tab: "datos" });
  const copy = (key: string) => <p className={styles.copy}>{t(`business.home_setup.steps.${step}.${key}`)}</p>;
  const action = (label: string, run: () => void, quiet = false) => <div className={styles.actions}><button type="button" data-testid={`home-setup-action-${step}`} className={quiet ? quietButtonClass : primaryButtonClass} onClick={run}>{label}</button></div>;
  if (step === "created") {
    const country = records.workspace?.country;
    return <>
      <dl className={styles.summary}>
        <dt>{t("workspace_setup_preview.business_name")}</dt><dd>{name}</dd>
        <dt>{t("workspace_setup_preview.operating_country")}</dt>
        <dd>{country ? t(`workspace_setup_preview.country_${country.toLowerCase()}`, { defaultValue: country }) : t("business.home_setup.missing")}</dd>
      </dl>
      {action(t("business.home_setup.steps.created.action"), datos, true)}
    </>;
  }
  if (step === "fiscal_identity") return <>{copy("body")}{action(t("business.home_setup.steps.fiscal_identity.action"), datos)}</>;
  if (step === "receiving_address") return <BusinessEmailAddress />;
  if (step === "receipt_reading") return <ReceiptReadingControl variant="inline" />;
  if (step === "team") {
    return <>
      {copy("body")}
      {action(t("business.home_setup.steps.team.action"), () => setDossier("team"))}
      {dossier === "team" ? <BusinessInvitationForm onClose={close} /> : null}
    </>;
  }
  return <WhatsAppStep name={name} linked={done} onOpen={() => setDossier("whatsapp")}>{dossier === "whatsapp" ? <WhatsAppLinkModal onClose={close} /> : null}</WhatsAppStep>;
}

/** WhatsApp names the Business it links to and whether it is linked; the link itself happens in its dossier. */
function WhatsAppStep({ name, linked, onOpen, children }: { name: string; linked: boolean; onOpen: () => void; children: ReactNode }) {
  const { t } = useTranslation();
  return <section className={styles.connection} aria-label={t("business.home_setup.steps.whatsapp.title")}>
    <div>
      <p className={styles.destination}>{name}</p>
      <p className={styles.status} data-connected={linked} role="status">{t(linked ? "business.home_setup.steps.whatsapp.linked" : "business.home_setup.steps.whatsapp.unlinked")}</p>
    </div>
    <button type="button" data-testid="home-setup-action-whatsapp" className={linked ? quietButtonClass : primaryButtonClass} onClick={onOpen}>{t(linked ? "business.home_setup.steps.whatsapp.manage" : "business.home_setup.steps.whatsapp.action")}</button>
    {children}
  </section>;
}

/**
 * The guide: a header that collapses it (title, the `n / n` ring of required steps done, Ocultar or Mostrar), then
 * the server's steps on one rail. Nothing renders while the answer is unknown, for someone who may not configure
 * the Business, or once every required step is done.
 */
export function SetupGuide({ setup: { steps, refresh } }: { setup: ReturnType<typeof useBusinessSetup> }) {
  const { chosen, userId } = useBusiness();
  if (!setupOpen(steps)) return null;
  return <Guide key={chosen?.space_id ?? "none"} steps={steps} scope={`${userId ?? "anon"}:${chosen?.space_id ?? "none"}`} refresh={refresh} />;
}

function Guide({ steps, scope, refresh }: { steps: readonly BusinessSetupStep[]; scope: string; refresh: () => void }) {
  const { t } = useTranslation();
  const id = useId();
  const [collapsed, setCollapsed] = useCollapsed(scope, guideStartsCollapsed(steps));
  const [open, setOpen] = useState<BusinessSetupStepKey | null>(null);
  const required = steps.filter((step) => step.required);
  const done = required.filter((step) => step.done).length;
  return (
    <section className={styles.guide} data-testid="home-setup" data-collapsed={collapsed}>
      <h2 className="m-0">
        <button type="button" className={styles.head} aria-expanded={!collapsed} aria-controls={`${id}-body`} data-testid="home-setup-toggle" onClick={() => setCollapsed(!collapsed)}>
          <span className={styles.title}>{t("business.home_setup.title")}</span>
          <span className={styles.progress} data-testid="home-setup-progress">
            <svg className={styles.ring} viewBox="0 0 44 44" aria-hidden="true">
              <circle className={styles.ringTrack} cx="22" cy="22" r="19" />
              <circle className={styles.ringFill} cx="22" cy="22" r="19" pathLength={100} style={{ strokeDashoffset: 100 - (done / required.length) * 100 }} />
            </svg>
            <span className={styles.count} aria-hidden="true">{t("business.home_setup.progress", { done, total: required.length })}</span>
            <span className={styles.visuallyHidden}>{t("business.home_setup.progress_description", { done, total: required.length })}</span>
          </span>
          <span className={styles.hide} aria-hidden="true">{t(collapsed ? "business.home_setup.show" : "business.home_setup.hide")}</span>
          <svg className={styles.chevron} viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        </button>
      </h2>
      <div id={`${id}-body`} className={styles.body} hidden={collapsed}>
        <ol className={styles.rail} aria-label={t("business.home_setup.list_label")}>
          {steps.map((step, index) => {
            // Required steps are numbered in order; an optional one is a dot, as the sketch draws a step it does not count.
            const number = steps.slice(0, index + 1).filter((item) => item.required).length;
            const isOpen = open === step.key;
            const state = step.done ? t("business.home_setup.completed") : step.required ? null : t("business.home_setup.optional");
            const classes = [styles.item, isOpen ? styles.open : "", step.done ? styles.done : "", step.required ? "" : styles.extra].filter(Boolean).join(" ");
            return (
              <li key={step.key} className={classes} data-testid={`home-setup-step-${step.key}`} data-done={step.done || undefined}>
                <button type="button" className={styles.step} aria-expanded={isOpen} aria-controls={`${id}-${step.key}`} aria-current={isOpen ? "step" : undefined} onClick={() => setOpen(isOpen ? null : step.key)}>
                  <span className={styles.node} aria-hidden="true">{step.done ? <Check /> : step.required ? number : "·"}</span>
                  <span className={styles.label}>{t(`business.home_setup.steps.${step.key}.title`)}</span>
                  {state ? <span className={`${styles.state} ${step.done ? styles.completed : ""}`}>{state}</span> : null}
                  <svg className={styles.stepChevron} viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
                </button>
                <div id={`${id}-${step.key}`} className={styles.panel} hidden={!isOpen}>
                  {isOpen ? <StepPanel step={step} onChanged={refresh} /> : null}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
