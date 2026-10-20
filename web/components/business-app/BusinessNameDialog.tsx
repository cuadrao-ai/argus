"use client";

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { saveBusinessName, type BusinessNamingState } from "@/lib/business-naming-api";
import { businessNameCopy } from "./business-name-copy";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

export default function BusinessNameDialog({ business, required, onSaved, onClose }: {
  business: BusinessNamingState;
  required: boolean;
  onSaved: (business: BusinessNamingState) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(business.name_required ? "" : business.name);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const title = businessNameCopy.title;
  const save = async () => {
    if (busy || !name.trim()) return;
    setBusy(true);
    setFailed(false);
    try {
      const next = await saveBusinessName(business.id, name.trim());
      if (next.name_required) { setFailed(true); return; }
      onSaved(next);
    } catch { setFailed(true); }
    finally { setBusy(false); }
  };
  return <AdaptivePanel title={title} closeLabel={t("common.close")} onClose={() => { if (!busy && !required) onClose(); }} dismissible={!required && !busy} initialFocusRef={input} width="md">
    <form className="space-y-5 p-5" onSubmit={event => { event.preventDefault(); void save(); }}>
      <p className="text-sm text-black/65 dark:text-white/65">{businessNameCopy.explanation}</p>
      <input ref={input} aria-label={title} placeholder={businessNameCopy.placeholder} value={name} onChange={event => setName(event.target.value)} maxLength={80} required disabled={busy} className="min-h-11 w-full rounded-xl border border-black/20 bg-transparent px-3 py-3 text-base text-black outline-offset-4 dark:border-white/25 dark:text-white" />
      {failed ? <p role="alert" className={inlineFailureTextClass}>{t("common.error_occurred")}</p> : null}
      <div className="flex flex-wrap justify-end gap-3">
        {!required ? <button type="button" disabled={busy} className={secondaryButtonClass} onClick={onClose}>{businessNameCopy.skip}</button> : null}
        <button type="submit" className={primaryButtonClass} disabled={busy || !name.trim()}>{required ? businessNameCopy.continue : businessNameCopy.save}</button>
      </div>
    </form>
  </AdaptivePanel>;
}
