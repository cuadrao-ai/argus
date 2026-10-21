"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { Switch } from "@/components/ui/Switch";
import type { ReceiptReading } from "@/lib/business-api";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { useBusiness } from "./BusinessWorkspace";
import { useBusinessConsent } from "./business-consent-context";
import { quietButtonClass, secondaryButtonClass } from "./business-ui";
import { showToast } from "./foundation/toasts";

/**
 * The one notice about receipt reading and the one home of its switch. The
 * notice is a line that says what is true; its action opens Lectura de
 * recibos, where the switch sits beside the words the owner agrees to.
 * Nothing shows while the setting is unknown, so a failed read never claims
 * reading is off. `showWhenOn` keeps a quiet line with the way to turn it off.
 */
export default function ReceiptReadingControl({ showWhenOn = false }: { showWhenOn?: boolean }) {
  const { source, reload, chosen } = useBusiness();
  const consent = useBusinessConsent();
  const { t, i18n } = useTranslation();
  const language = normalizeEnabledLanguage(i18n.resolvedLanguage ?? "en");
  const businessKey = chosen?.space_id ?? "own";
  const generation = useRef(0);
  const mutation = useRef<AbortController | null>(null);
  useLayoutEffect(() => {
    generation.current += 1;
    return () => { generation.current += 1; mutation.current?.abort(); };
  }, [source, businessKey, language]);
  const [reading, setReading] = useState<ReceiptReading | null>(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setReading(null);
    setOpen(false);
    setFailed(false);
    source.receiptReading?.(language, controller.signal).then((value) => { if (current) setReading(value); }, () => undefined);
    return () => { current = false; controller.abort(); };
  }, [source, language, businessKey]);
  if (!consent.accepted || !reading || (reading.enabled && !showWhenOn)) return null;

  const change = async (enabled: boolean) => {
    if (!source.setReceiptReading) return;
    const current = generation.current;
    const controller = new AbortController();
    mutation.current = controller;
    setFailed(false);
    try {
      const next = await source.setReceiptReading(reading, enabled, language, controller.signal);
      if (generation.current !== current || controller.signal.aborted) return;
      setReading(next);
      setOpen(false);
      reload();
      showToast({ kind: "success", text: next.enabled ? t("business.activity.turned_on", "Receipt reading is on.") : t("business.activity.turned_off", "Receipt reading is off.") });
    } catch (error) {
      if (generation.current === current && !controller.signal.aborted) setFailed(true);
      throw error;
    } finally {
      if (mutation.current === controller) mutation.current = null;
    }
  };

  const line = reading.enabled
    ? t("business.activity.reading_on", "Receipt reading is on.")
    : reading.can_change
      ? t("business.activity.saved_prompt", "Your receipts are saved unread. Turn on receipt reading to prepare them for review.")
      : t("business.activity.owner_only", "Your receipts are saved unread. The Business owner can turn reading on.");
  return (
    <>
      <div data-testid="receipt-reading-control" data-enabled={reading.enabled ? "true" : "false"} className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="min-w-[16rem] flex-1 text-[14px] text-[#56635e] dark:text-white/70">{line}</p>
        {reading.can_change ? (
          <button type="button" onClick={() => setOpen(true)} className={reading.enabled ? quietButtonClass : secondaryButtonClass}>
            {reading.enabled ? t("business.activity.change", "Change") : t("business.activity.turn_on", "Turn receipt reading on")}
          </button>
        ) : null}
      </div>
      {open ? (
        <AdaptivePanel title={t("business.activity.sheet_title", "Receipt reading")} closeLabel={t("common.close", "Close")} onClose={() => setOpen(false)} width="sm">
          <div data-testid="receipt-reading-sheet" className="flex flex-col gap-3 desktop:px-5">
            <div className="flex items-center justify-between gap-4">
              <span className="text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.activity.switch_label", "Read my receipts with AI")}</span>
              <Switch testId="receipt-reading-switch" label={t("business.activity.switch_label", "Read my receipts with AI")} checked={reading.enabled} disabled={!reading.enabled && !reading.available} onChange={change} />
            </div>
            {!reading.enabled && !reading.available ? <p className="text-[13px] text-[#56635e] dark:text-white/65">{t("business.activity.unavailable", "AI reading can't be turned on right now.")}</p> : null}
            {failed ? (
              <div role="alert" className="flex flex-wrap items-center justify-between gap-x-3 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">
                <p>{t("business.activity.error", "Receipt reading could not be updated. Try again.")}</p>
                <button type="button" onClick={() => void change(!reading.enabled).catch(() => undefined)} className={quietButtonClass}>{t("common.retry", "Retry")}</button>
              </div>
            ) : null}
            <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{reading.disclosure}</p>
          </div>
        </AdaptivePanel>
      ) : null}
    </>
  );
}
