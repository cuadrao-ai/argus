"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/Switch";
import type { BusinessWorkspaceInfo, ReceiptReading } from "@/lib/business-api";
import { getChosenGrant } from "@/lib/business-grant";
import { normalizeEnabledLanguage, resolveLanguage } from "@/lib/language-features";
import { useBusiness } from "./BusinessWorkspace";
import { useBusinessConsent } from "./business-consent-context";
import { quietButtonClass, secondaryButtonClass } from "./business-ui";
import { showToast } from "./foundation/toasts";

/** The reading setting the workspace answered, only while that answer is the chosen Business's. */
export function workspaceReading({ workspace, workspaceGrant }: { workspace: BusinessWorkspaceInfo | null; workspaceGrant?: string | null }): ReceiptReading | null {
  return workspaceGrant === getChosenGrant() ? workspace?.receipt_reading ?? null : null;
}

type ReadingState = {
  reading: ReceiptReading | null;
  failed: boolean;
  canSet: boolean;
  /** The words to agree to are open under the row. They close with a saved change, and when the Business or language changes under them. */
  consentOpen: boolean;
  setConsentOpen: (open: boolean) => void;
  change: (enabled: boolean) => Promise<void>;
};

/**
 * The Business's reading setting and its one way to change it. `reading` is null while the setting is unknown,
 * so a failed load never claims reading is off.
 */
export function useReceiptReading(onChanged?: (next: ReceiptReading) => void): ReadingState {
  const { source, reload, chosen, records, revision } = useBusiness();
  const consent = useBusinessConsent();
  const { i18n } = useTranslation();
  const language = normalizeEnabledLanguage(i18n.resolvedLanguage ?? resolveLanguage({}));
  const businessKey = chosen?.space_id ?? "own";
  const generation = useRef(0);
  const mutation = useRef<AbortController | null>(null);
  useLayoutEffect(() => {
    generation.current += 1;
    return () => { generation.current += 1; mutation.current?.abort(); };
  }, [source, businessKey, language]);
  const committedRevision = useRef(revision);
  useLayoutEffect(() => { committedRevision.current = revision; }, [revision]);
  const snapshot = workspaceReading(records);
  // A saved answer stands until a workspace read that started after it answers.
  const [saved, setReading] = useState<{ value: ReceiptReading; answeredAt: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  useEffect(() => {
    setReading(null);
    setConsentOpen(false);
    setFailed(false);
  }, [source, language, businessKey]);
  const reading = consent.accepted && snapshot ? (saved && (records.workspaceRevision ?? -1) <= saved.answeredAt ? saved.value : snapshot) : null;
  const change = async (enabled: boolean) => {
    if (!source.setReceiptReading || !reading?.can_change) return;
    const current = generation.current;
    const controller = new AbortController();
    mutation.current = controller;
    setFailed(false);
    try {
      const next = await source.setReceiptReading(reading, enabled, language, controller.signal);
      if (generation.current !== current || controller.signal.aborted) return;
      setReading({ value: next, answeredAt: committedRevision.current });
      setConsentOpen(false);
      reload();
      onChanged?.(next);
    } catch (error) {
      if (generation.current === current && !controller.signal.aborted) setFailed(true);
      throw error;
    } finally {
      if (mutation.current === controller) mutation.current = null;
    }
  };
  return { reading, failed, canSet: Boolean(source.setReceiptReading), consentOpen, setConsentOpen, change };
}

/**
 * Document reading on one surface. `variant="inline"` is Ajustes: the switch beside the full words the owner
 * agrees to, and the only place reading turns off. Everywhere else it is the row that turns reading on in place.
 */
export default function ReceiptReadingControl({ variant = "notice", pending = false }: { variant?: "notice" | "inline"; pending?: boolean }) {
  const { t } = useTranslation();
  const isInline = variant === "inline";
  const state = useReceiptReading(() => {
    if (!isInline) showToast({ kind: "success", text: t("business.activity.turned_on") });
  });
  if (isInline) return <InlineReading reading={state.reading} failed={state.failed} onChange={state.canSet ? state.change : undefined} />;
  return <ReceiptReadingOption state={state} pending={pending} className="mb-4" />;
}

/**
 * The one row that turns reading on where the person is. It shows only while reading is off: nothing while the
 * setting is unknown, so a failed load never claims reading is off, and nothing once reading is on. A Business
 * that agreed before turns it on with the switch. The first time, the switch opens the server's words under the
 * row and their one confirm turns it on. `pending` holds the row's space while the list under it loads.
 */
export function ReceiptReadingOption({ state, className = "", pending = false }: { state: ReadingState; className?: string; pending?: boolean }) {
  const { t } = useTranslation();
  const { reading, failed, change, consentOpen, setConsentOpen } = state;
  const [confirming, setConfirming] = useState(false);
  if (!reading || reading.enabled) return null;
  const help = !reading.can_change
    ? t("business.activity.owner_only")
    : reading.available ? t("business.intake.reading_help_on") : t("business.activity.unavailable");
  const turnOn = () => change(true);
  const confirm = async () => {
    setConfirming(true);
    try { await turnOn(); } catch { /* The row says it failed and offers the retry. */ } finally { setConfirming(false); }
  };
  return (
    <div data-testid="receipt-reading-control" data-surface-block="reading" data-enabled="false" aria-hidden={pending || undefined} style={pending ? { visibility: "hidden" } : undefined} className={className}>
      <div className="flex min-h-16 items-center justify-between gap-4 py-2.5">
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[14px] font-medium text-[#172b26] dark:text-white">{t("business.activity.switch_label")}</span>
          <span className="text-[12.5px] leading-[17px] text-[#56635e] dark:text-white/70">{help}</span>
        </span>
        <Switch
          testId="receipt-reading-switch"
          label={t("business.activity.switch_label")}
          checked={false}
          disabled={!reading.can_change || !state.canSet || !reading.available || confirming}
          onChange={() => (reading.consented_at ? turnOn() : setConsentOpen(!consentOpen))}
        />
      </div>
      {consentOpen ? (
        <div data-testid="receipt-reading-consent" className="flex flex-col items-start gap-3 pb-3">
          <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{reading.disclosure}</p>
          <button type="button" disabled={confirming} onClick={() => void confirm()} className={secondaryButtonClass}>{t("common.confirm")}</button>
        </div>
      ) : null}
      {failed ? (
        <div role="alert" className="flex flex-wrap items-center gap-x-3 pb-2.5 text-[12.5px] leading-[17px] text-[#9e2f39] dark:text-[#ec9aa0]">
          <p>{t("business.activity.error")}</p>
          <button type="button" onClick={() => void turnOn().catch(() => undefined)} className={quietButtonClass}>{t("common.retry")}</button>
        </div>
      ) : null}
    </div>
  );
}

export function InlineReading({reading, failed = false, onChange}: {reading: Pick<ReceiptReading,"enabled"|"can_change"|"available"|"disclosure"> | null; failed?: boolean; onChange?: (enabled: boolean) => Promise<void>}) {
  const {t} = useTranslation();
  return <div data-testid="receipt-reading-inline" data-enabled={reading ? String(reading.enabled) : "unknown"}>
    <div className="flex items-center justify-between gap-4">
      <h2 className="text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.activity.switch_label")}</h2>
      {reading ? <Switch label={t("business.activity.switch_label")} testId="receipt-reading-switch" checked={reading.enabled} disabled={!reading.can_change || !onChange || (!reading.enabled && !reading.available)} onChange={onChange ?? (() => {})} /> : <span className="text-[14px] text-[#56635e] dark:text-white/70">{t("business.activity.state_unknown")}</span>}
    </div>
    {reading?.disclosure ? <p className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{reading.disclosure}</p> : null}
    {reading && !reading.enabled && !reading.available ? <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70">{t("business.activity.unavailable")}</p> : null}
    {failed ? <div role="alert" className="mt-2 flex flex-wrap items-center gap-2 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]"><p>{t("business.activity.error")}</p><button type="button" className={quietButtonClass} onClick={() => void onChange?.(!reading?.enabled).catch(() => undefined)}>{t("common.retry")}</button></div> : null}
  </div>;
}
