"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Switch } from "@/components/ui/Switch";
import type { BusinessWorkspaceInfo, ReceiptReading } from "@/lib/business-api";
import { getChosenGrant } from "@/lib/business-grant";
import { normalizeEnabledLanguage, resolveLanguage } from "@/lib/language-features";
import { useBusiness } from "./BusinessWorkspace";
import { useBusinessConsent } from "./business-consent-context";
import { primaryButtonClass, quietButtonClass } from "./business-ui";
import { FOCUS_RING } from "./foundation/presentation";
import { showToast } from "./foundation/toasts";

/** The reading setting the workspace answered, only while that answer is the chosen Business's. */
export function workspaceReading({ workspace, workspaceGrant }: { workspace: BusinessWorkspaceInfo | null; workspaceGrant?: string | null }): ReceiptReading | null {
  return workspaceGrant === getChosenGrant() ? workspace?.receipt_reading ?? null : null;
}

type ReadingState = {
  reading: ReceiptReading | null;
  failed: boolean;
  canSet: boolean;
  /** The server disclosure is open for confirmation. They close with a saved change, and when the Business or language changes under them. */
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
  const showConsent = (open: boolean) => {
    setFailed(false);
    setConsentOpen(open);
  };
  return { reading, failed, canSet: Boolean(source.setReceiptReading), consentOpen, setConsentOpen: showConsent, change };
}

/**
 * Document reading on one surface. `variant="inline"` is Ajustes: the switch beside the full words the owner
 * agrees to, and the only place reading turns off. Everywhere else it is the notice that turns reading on in place.
 */
export default function ReceiptReadingControl({ variant = "notice", pending = false }: { variant?: "notice" | "inline"; pending?: boolean }) {
  const { t } = useTranslation();
  const isInline = variant === "inline";
  const state = useReceiptReading(() => {
    if (!isInline) showToast({ kind: "success", text: t("business.activity.turned_on") });
  });
  if (isInline) return <InlineReading reading={state.reading} failed={state.failed} onChange={state.canSet ? state.change : undefined} />;
  return <ReceiptReadingNotice state={state} pending={pending} />;
}

/**
 * Turning reading on where the person is, for a setting that is known and off. A Business that agreed before
 * turns it on at once. The first time, `start` opens the server's words and their one confirm turns it on.
 */
function useTurnOn({ reading, change, canSet, consentOpen, setConsentOpen }: ReadingState) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  if (!reading || reading.enabled) return null;
  const save = async () => {
    setSaving(true);
    try { await change(true); } catch { /* The surface says it failed and offers the retry. */ } finally { setSaving(false); }
  };
  return {
    reading,
    help: !reading.can_change
      ? t("business.activity.owner_only")
      : reading.available ? t("business.intake.reading_help_on") : t("business.activity.unavailable"),
    disabled: !reading.can_change || !canSet || !reading.available || saving,
    saving,
    save,
    start: () => reading.consented_at ? save() : setConsentOpen(!consentOpen),
  };
}

/** On a surface that saves in place, keep the retry beside the control. */
function TurnOnError({ retry, disabled }: { retry: () => Promise<void>; disabled: boolean }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="flex flex-wrap items-center gap-x-3 pb-2.5 text-[12.5px] leading-[17px] text-[#9e2f39] dark:text-[#ec9aa0]">
      <p>{t("business.activity.error")}</p>
      <button type="button" disabled={disabled} onClick={() => void retry()} className={quietButtonClass}>{t("common.retry")}</button>
    </div>
  );
}

const helpClass = "text-[12.5px] leading-[17px] text-[var(--segment-text)]";
const titleClass = "text-[14px] font-medium text-[var(--segment-text-strong)]";
const noticeButtonClass = `inline-flex min-h-9 shrink-0 items-center justify-center rounded-full border border-[#172b26]/25 bg-white px-4 text-[14px] font-medium text-[#172b26] transition-colors hover:bg-[#F7F5EE] active:bg-[#EFEDE6] ${FOCUS_RING} disabled:opacity-40 dark:border-white/20 dark:bg-[#1f2225] dark:text-white dark:hover:bg-white/[0.06] dark:active:bg-white/10`;

/**
 * The upload panel's row that turns reading on with the switch. It shows only while reading is off: nothing
 * while the setting is unknown, so a failed load never claims reading is off, and nothing once reading is on.
 */
export function ReceiptReadingOption({ state, className = "" }: { state: ReadingState; className?: string }) {
  const { t } = useTranslation();
  const turn = useTurnOn(state);
  if (!turn) return null;
  return (
    <div data-testid="receipt-reading-control" data-surface-block="reading" data-enabled="false" className={className}>
      <div className="flex min-h-16 items-center justify-between gap-4 py-2.5">
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className={titleClass}>{t("business.activity.switch_label")}</span>
          <span className={helpClass}>{turn.help}</span>
        </span>
        <Switch
          testId="receipt-reading-switch"
          label={t("business.activity.switch_label")}
          checked={false}
          disabled={turn.disabled}
          onChange={turn.start}
        />
      </div>
      {state.consentOpen ? (
        <div data-testid="receipt-reading-consent" className="flex flex-col items-start gap-3 pb-3">
          <p className="text-[14px] leading-relaxed text-[var(--segment-text)]">{turn.reading.disclosure}</p>
          <button type="button" disabled={turn.disabled} onClick={() => void turn.save()} className={primaryButtonClass}>{t("common.confirm")}</button>
        </div>
      ) : null}
      {state.failed ? <TurnOnError retry={turn.save} disabled={turn.disabled} /> : null}
    </div>
  );
}

/**
 * The notice on a work surface (the Bandeja and the dossier) while reading is off: it says so, and its button
 * turns reading on in place. It shows under the same rule as the row above. `pending` holds its space while the
 * list under it loads.
 */
function ReceiptReadingNotice({ state, pending }: { state: ReadingState; pending: boolean }) {
  const { t } = useTranslation();
  const turn = useTurnOn(state);
  if (!turn) return null;
  return (
    <div data-testid="receipt-reading-notice" data-surface-block="reading" data-enabled="false" aria-hidden={pending || undefined} style={pending ? { visibility: "hidden" } : undefined} className="mb-4 max-w-[640px] rounded-item border border-[#E4E2DA] bg-[#FFFEFA] px-4 dark:border-white/[0.07] dark:bg-white/[0.03]">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className={titleClass}>{t("business.activity.off_notice")}</span>
          <span className={helpClass}>{turn.help}</span>
        </span>
        <button
          type="button"
          data-testid="receipt-reading-turn-on"
          disabled={turn.disabled}
          onClick={(event) => {
            // Pointer activation on Safari can leave focus on the page behind the dialog.
            if (!turn.reading.consented_at) event.currentTarget.focus();
            void turn.start();
          }}
          className={noticeButtonClass}
        >
          {t("business.home_setup.steps.receipt_reading.title")}
        </button>
      </div>
      {state.consentOpen ? (
        <ConfirmDialog
          isOpen
          tone="primary"
          title={t("business.activity.switch_label")}
          description={turn.reading.disclosure}
          cancelLabel={t("common.cancel")}
          confirmLabel={t(state.failed ? "common.retry" : "common.confirm")}
          isBusy={turn.saving}
          error={state.failed ? t("business.activity.error") : undefined}
          onConfirm={() => void turn.save()}
          onCancel={() => { if (!turn.saving) state.setConsentOpen(false); }}
        />
      ) : state.failed && turn.reading.consented_at ? <TurnOnError retry={turn.save} disabled={turn.disabled} /> : null}
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
