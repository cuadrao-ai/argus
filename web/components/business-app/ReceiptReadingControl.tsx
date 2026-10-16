"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ReceiptReading } from "@/lib/business-api";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { useBusiness } from "./BusinessWorkspace";
import { secondaryButtonClass } from "./business-ui";

export default function ReceiptReadingControl({ hideWhenEnabled = false }: { hideWhenEnabled?: boolean }) {
  const { source, reload, chosen } = useBusiness();
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
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setReading(null);
    setFailed(false);
    setBusy(false);
    source.receiptReading?.(language, controller.signal).then((value) => { if (current) setReading(value); }, () => { if (current) setFailed(true); });
    return () => { current = false; controller.abort(); };
  }, [source, language, businessKey]);
  if (!source.receiptReading || (hideWhenEnabled && (reading?.enabled || (!reading && !failed)))) return null;
  const change = async () => {
    if (!reading || !source.setReceiptReading || busy) return;
    const current = generation.current;
    const controller = new AbortController();
    mutation.current = controller;
    setBusy(true);
    setFailed(false);
    try {
      const next = await source.setReceiptReading(reading, !reading.enabled, language, controller.signal);
      if (generation.current === current && !controller.signal.aborted) { setReading(next); reload(); }
    } catch { if (generation.current === current && !controller.signal.aborted) setFailed(true); }
    finally { if (generation.current === current) setBusy(false); if (mutation.current === controller) mutation.current = null; }
  };
  return <section className="mb-4 rounded-[14px] border border-black/10 p-4 dark:border-white/10" data-testid="receipt-reading-control">
    <p className="text-[14px] text-black/75 dark:text-white/75">{reading?.enabled ? t("business.activity.reading_on", "Receipt reading is on.") : t("business.activity.saved_prompt", "Your receipts are saved unread. Turn on receipt reading to prepare them for review.")}</p>
    {reading?.can_change ? <>
      {!reading.enabled ? <><p className="mt-2 text-[13px] text-black/60 dark:text-white/60">{reading.disclosure}</p>{reading.route ? <p className="mt-1 text-[12px] text-black/50 dark:text-white/50">{reading.route.gateway} · {reading.route.interpretation.map((route) => route.model).join(", ")}</p> : null}</> : null}
      <button type="button" className={`${secondaryButtonClass} mt-3`} disabled={busy || (!reading.enabled && !reading.available)} onClick={() => void change()}>{reading.enabled ? t("business.activity.turn_off", "Turn reading off") : t("business.activity.turn_on", "Turn receipt reading on")}</button>
    </> : reading ? <p className="mt-2 text-[13px] text-black/60 dark:text-white/60">{t("business.activity.owner_only", "The Business owner can turn receipt reading on.")}</p> : null}
    {failed ? <p role="alert" className="mt-2 text-[13px]">{t("business.activity.error", "Receipt reading could not be updated. Try again.")}</p> : null}
  </section>;
}
