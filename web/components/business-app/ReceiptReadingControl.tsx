"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
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
  /** Lectura de documentos is open. It closes with a saved change, and when the Business or language changes under it. */
  sheetOpen: boolean;
  setSheetOpen: (open: boolean) => void;
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
  const [sheetOpen, setSheetOpen] = useState(false);
  useEffect(() => {
    setReading(null);
    setSheetOpen(false);
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
      setSheetOpen(false);
      reload();
      onChanged?.(next);
    } catch (error) {
      if (generation.current === current && !controller.signal.aborted) setFailed(true);
      throw error;
    } finally {
      if (mutation.current === controller) mutation.current = null;
    }
  };
  return { reading, failed, canSet: Boolean(source.setReceiptReading), sheetOpen, setSheetOpen, change };
}

/**
 * The one notice about document reading and the one home of its switch. The
 * notice is a line that says what is true; its action opens Lectura de
 * documentos, where the switch sits beside the words the owner agrees to.
 * Nothing shows while the setting is unknown, so a failed read never claims
 * reading is off, and nothing shows while reading is on.
 * `variant="row"` is the same control as a settings row: its state in words
 * (a dash while it is unknown) and, for whoever may change it, the button that
 * opens the same sheet.
 */
export default function ReceiptReadingControl({ variant = "notice", pending = false }: { variant?: "notice" | "row" | "inline"; pending?: boolean }) {
  const { t } = useTranslation();
  const isRow = variant === "row";
  const isInline = variant === "inline";
  const titleId = useId();
  const state = useReceiptReading((next) => {
    if (!isInline) showToast({ kind: "success", text: next.enabled ? t("business.activity.turned_on") : t("business.activity.turned_off") });
  });
  const { reading, failed, change, sheetOpen: open, setSheetOpen: setOpen } = state;
  if (!reading || (reading.enabled && !isRow && !isInline)) {
    if (isInline) return <InlineReading reading={null} />;
    return isRow ? <ReadingRow titleId={titleId} title={t("business.activity.sheet_title")} reading={null} /> : null;
  }

  if (isInline) return <InlineReading reading={reading} failed={failed} onChange={state.canSet ? change : undefined} />;

  const line = reading.can_change ? t("business.activity.saved_prompt") : t("business.activity.owner_only");
  return (
    <>
      {isRow ? (
        <ReadingRow
          titleId={titleId}
          title={t("business.activity.sheet_title")}
          reading={reading}
          changeLabel={t("business.activity.change")}
          onChange={() => setOpen(true)}
        />
      ) : (
        <div data-testid="receipt-reading-control" data-surface-block="reading" data-enabled="false" aria-hidden={pending || undefined} style={pending ? { visibility: "hidden" } : undefined} className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p className="min-w-[16rem] flex-1 text-[14px] text-[#56635e] dark:text-white/70">{line}</p>
          {reading.can_change ? (
            <button type="button" onClick={() => setOpen(true)} className={secondaryButtonClass}>{t("business.activity.turn_on")}</button>
          ) : null}
        </div>
      )}
      {open ? <ReadingSheet reading={reading} failed={failed} change={change} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

/** Lectura de documentos: the switch beside the words the owner agrees to. */
function ReadingSheet({ reading, failed, change, onClose }: { reading: ReceiptReading; failed: boolean; change: (enabled: boolean) => Promise<void>; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <AdaptivePanel title={t("business.activity.sheet_title")} closeLabel={t("common.close")} onClose={onClose} width="sm">
      <div data-testid="receipt-reading-sheet" className="flex flex-col gap-3 desktop:px-5">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.activity.switch_label")}</span>
          <Switch testId="receipt-reading-switch" label={t("business.activity.switch_label")} checked={reading.enabled} disabled={!reading.enabled && !reading.available} onChange={change} />
        </div>
        {!reading.enabled && !reading.available ? <p className="text-[13px] text-[#56635e] dark:text-white/65">{t("business.activity.unavailable")}</p> : null}
        {failed ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-x-3 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">
            <p>{t("business.activity.error")}</p>
            <button type="button" onClick={() => void change(!reading.enabled).catch(() => undefined)} className={quietButtonClass}>{t("common.retry")}</button>
          </div>
        ) : null}
        <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{reading.disclosure}</p>
      </div>
    </AdaptivePanel>
  );
}

/**
 * The same setting as one row of Agregar's options. Turning it off is one tap. Turning it on opens Lectura de
 * documentos, because reading starts only beside the words the owner agrees to. Nothing shows while it is unknown.
 */
export function ReceiptReadingOption({ state }: { state: ReadingState }) {
  const { t } = useTranslation();
  const { reading, failed, change, sheetOpen: open, setSheetOpen: setOpen } = state;
  if (!reading) return null;
  const help = reading.enabled
    ? t("business.intake.reading_help_on")
    : !reading.can_change
      ? t("business.activity.owner_only")
      : reading.available ? t("business.intake.reading_help_off") : t("business.activity.unavailable");
  return (
    <div data-testid="receipt-reading-control" data-enabled={reading.enabled ? "true" : "false"} className="flex min-h-16 items-center justify-between gap-4 border-b border-[#ECEAE3] py-2.5 dark:border-white/[0.07]">
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-[14px] font-medium text-[#172b26] dark:text-white">{t("business.activity.switch_label")}</span>
        <span className="text-[12.5px] leading-[17px] text-[#56635e] dark:text-white/70">{help}</span>
        {failed && !open ? <span role="alert" className="text-[12.5px] leading-[17px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.activity.error")}</span> : null}
      </span>
      <Switch
        testId="receipt-reading-option"
        label={t("business.activity.switch_label")}
        checked={reading.enabled}
        disabled={!reading.can_change || !state.canSet || (!reading.enabled && !reading.available)}
        onChange={(next) => (next ? setOpen(true) : change(false))}
      />
      {open ? <ReadingSheet reading={reading} failed={failed} change={change} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

function ReadingRow({ titleId, title, reading, changeLabel, onChange }: { titleId: string; title: string; reading: ReceiptReading | null; changeLabel?: string; onChange?: () => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="receipt-reading-row" data-enabled={reading ? (reading.enabled ? "true" : "false") : "unknown"} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="min-w-0">
        <p id={titleId} className="text-[16px] font-medium text-[#172b26] dark:text-white">{title}</p>
        <p data-testid="receipt-reading-state" className="text-[14px] text-[#56635e] dark:text-white/70">
          {reading ? (
            reading.enabled ? t("business.activity.state_on") : t("business.activity.state_off")
          ) : (
            <>
              <span aria-hidden="true">-</span>
              <span className="sr-only">{t("business.activity.state_unknown")}</span>
            </>
          )}
        </p>
      </div>
      {reading?.can_change && onChange ? (
        <button type="button" onClick={onChange} aria-describedby={titleId} className={secondaryButtonClass}>{changeLabel}</button>
      ) : null}
    </div>
  );
}

export function InlineReading({reading, failed = false, onChange}: {reading: Pick<ReceiptReading,"enabled"|"can_change"|"available"|"disclosure"> | null; failed?: boolean; onChange?: (enabled: boolean) => Promise<void>}) {
  const {t} = useTranslation();
  return <div data-testid="receipt-reading-inline" data-enabled={reading ? String(reading.enabled) : "unknown"}>
    <div className="flex items-center justify-between gap-4">
      <h2 className="text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.reception.reading_title")}</h2>
      {reading ? <Switch label={t("business.activity.switch_label")} testId="receipt-reading-switch" checked={reading.enabled} disabled={!reading.can_change || !onChange || (!reading.enabled && !reading.available)} onChange={onChange ?? (() => {})} /> : <span className="text-[14px] text-[#56635e] dark:text-white/70">{t("business.activity.state_unknown")}</span>}
    </div>
    {reading?.disclosure ? <p className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{reading.disclosure}</p> : null}
    {reading && !reading.enabled && !reading.available ? <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/70">{t("business.activity.unavailable")}</p> : null}
    {failed ? <div role="alert" className="mt-2 flex flex-wrap items-center gap-2 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]"><p>{t("business.activity.error")}</p><button type="button" className={quietButtonClass} onClick={() => void onChange?.(!reading?.enabled).catch(() => undefined)}>{t("common.retry")}</button></div> : null}
  </div>;
}
