"use client";

import { useId, useRef, useState } from "react";
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { ErrorSummary, FormField, useFieldChecks } from "@/components/ui/FormField";
import { saveBusinessName, type BusinessNamingState } from "@/lib/business-naming-api";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "./business-ui";

export default function BusinessNameDialog({ business, required, onSaved, onClose }: {
  business: BusinessNamingState;
  required: boolean;
  onSaved: (business: BusinessNamingState) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [name, setName] = useState(business.name_required ? "" : business.name);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const label = t("business.dgii.business_name", "Business name");
  const checks = useFieldChecks(
    { name: (values) => (values.name.trim() ? null : t("business.dgii.business_name_required", "Enter the business name.")) },
    { name },
  );
  const save = async () => {
    if (busy || !checks.submit()) return;
    setBusy(true);
    setFailed(false);
    try {
      const next = await saveBusinessName(business.id, name.trim());
      if (next.name_required) { setFailed(true); return; }
      onSaved(next);
    } catch { setFailed(true); }
    finally { setBusy(false); }
  };
  return <AdaptivePanel title={t("business.naming.title", "What is your business called?")} closeLabel={t("common.close")} onClose={() => { if (!busy && !required) onClose(); }} dismissible={!required && !busy} initialFocusRef={input} width="md">
    <form noValidate className="space-y-[13px] p-5" onSubmit={event => { event.preventDefault(); void save(); }}>
      <p className="text-[14px] text-[#56635e] dark:text-white/70">{t("business.naming.explanation", "Your accountant and your team will see it like this.")}</p>
      <ErrorSummary key={checks.attempt} title={t("common.form_summary", "Check these fields to continue:")} items={checks.summary.map(() => ({ id: `${id}-name`, label }))} />
      <FormField ref={input} id={`${id}-name`} label={label} hint={t("business.naming.example", "For example, Colmado La Esquina")} error={checks.errorOf("name")} autoComplete="organization" value={name} onBlur={() => checks.blur("name")} onChange={event => setName(event.target.value)} maxLength={80} disabled={busy} />
      {failed ? (
        <div role="alert" className="flex items-start gap-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
          <AlertCircle className="mt-[3px] h-4 w-4 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <p>{t("business.naming.save_failed", "We couldn't save the name. Try again.")}</p>
            <button type="submit" disabled={busy} className={`${quietButtonClass} -ml-1`}>{t("common.retry", "Retry")}</button>
          </div>
        </div>
      ) : null}
      <div className="flex flex-wrap justify-end gap-3 pt-2">
        {!required ? <button type="button" disabled={busy} className={secondaryButtonClass} onClick={onClose}>{t("business.naming.skip", "Not now")}</button> : null}
        <button type="submit" className={primaryButtonClass} disabled={busy}>{required ? t("business.naming.continue", "Save and continue") : t("business.naming.save", "Save")}</button>
      </div>
    </form>
  </AdaptivePanel>;
}
