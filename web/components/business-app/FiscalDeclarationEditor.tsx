"use client";

import { secondaryButtonClass } from "./business-ui";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier, RefundCandidate } from "@/lib/business-dossier";
import { getDgiiFields, reviewDgii, type DgiiDeclaration, type DgiiFields, type DgiiReview } from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { resolveLanguage } from "@/lib/language-features";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { SURFACE_CARD } from "./foundation/surfaces";

const inputClass = "mt-2 block min-h-11 w-full rounded-item border border-[#7d8a84] bg-[#FFFEFA] px-3 text-[16px] text-[#172b26] dark:bg-[#141517] dark:text-white";
const EDITOR_ID = "fiscal-declaration";

/** Opens the tax details and puts the cursor on one field, or on the summary when the field is not listed. */
export function focusFiscalField(field: string | null): void {
  const editor = document.querySelector<HTMLDetailsElement>(`[data-testid="${EDITOR_ID}"]`);
  if (!editor) return;
  editor.open = true;
  const target = (field ? editor.querySelector<HTMLElement>(`[name="${field}"]`) : null) ?? editor.querySelector<HTMLElement>("summary");
  target?.focus();
}

export default function FiscalDeclarationEditor({ dossier, disabled, onChanged, onBusy, onDirty }: { dossier: BusinessDossier; disabled: boolean; onChanged: (value: BusinessDossier) => void; onBusy: (value: boolean) => void; onDirty: (value: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [fields, setFields] = useState<DgiiFields | null>(null);
  const [form, setForm] = useState<"606" | "607">((dossier.dgii?.form) ?? (dossier.facts.kind.value === "income" ? "607" : "606"));
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")])));
  const [fiscal, setFiscal] = useState(() => ({ rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" }));
  const [actualRefund, setActualRefund] = useState(dossier.dgii?.actual_refund === true);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // The purchase the server refused for this refund: the choice stays, and the person picks another.
  const [refused, setRefused] = useState<string | null>(null);
  const candidates = dossier.refund_candidates ?? [];
  const request = useRef<{ key: string; version: number; input: DgiiReview } | null>(null);
  useEffect(() => { let live = true; void getDgiiFields().then((value) => { if (live) setFields(value); }).catch(() => { if (live) setProblem(t("business.dgii.load_failed", "We couldn't load the tax fields.")); }); return () => { live = false; }; }, [t]);
  useEffect(() => () => { onDirty(false); onBusy(false); }, [onBusy, onDirty]);
  const editable = dossier.review_state === "open" && dossier.capabilities.includes("prepare") && !disabled && !busy;
  const change = () => onDirty(true);
  const reset = () => {
    setForm(dossier.dgii?.form ?? (dossier.facts.kind.value === "income" ? "607" : "606"));
    setValues(Object.fromEntries(Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")])));
    setFiscal({ rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" });
    setActualRefund(dossier.dgii?.actual_refund === true);
    setProblem(null); setRefused(null); onDirty(false);
  };
  const save = async () => {
    if (!fields || !editable) return;
    const declaration: DgiiDeclaration = { form };
    for (const field of fields[form]) if (!(field.name in fiscal)) declaration[field.name] = values[field.name] || null;
    if (form === "606") { declaration.actual_refund = actualRefund; declaration.purchase_activity_id = values.purchase_activity_id || null; }
    const input: DgiiReview = { fiscal: { rnc: fiscal.rnc || null, ncf: fiscal.ncf || null, itbis: fiscal.itbis || null }, declaration };
    request.current ??= { key: randomId(), version: dossier.version, input };
    const pending = request.current;
    setBusy(true); onBusy(true); setProblem(null); setRefused(null);
    try {
      const value = await reviewDgii(dossier.draft_id, pending.version, pending.input, pending.key);
      request.current = null; onDirty(false); setUncertain(false); onChanged(value);
    } catch (error) {
      const { status, code } = error as { status?: number; code?: string };
      if (status && status >= 400 && status < 500) request.current = null;
      else setUncertain(true);
      // Until the server leaves owner-paid purchases out of the list, picking one is refused this way.
      const purchase = pending.input.declaration.purchase_activity_id;
      if (status === 422 && code === "recorded_correction_unsupported" && typeof purchase === "string") { setRefused(purchase); return; }
      setProblem(t(`business.dgii.error.${code}`, t("business.dgii.save_failed", "We couldn't confirm the tax details were saved. Check the current record before you approve.")));
    } finally { setBusy(false); onBusy(false); }
  };
  return <details className={SURFACE_CARD} data-testid={EDITOR_ID}>
    <summary className="min-h-11 cursor-pointer text-[14px] font-medium text-black dark:text-white">{t("business.dgii.details", "Tax details for 606 / 607")}</summary>
    <p className="my-3 text-[13px] text-black/65 dark:text-white/65">{t("business.dgii.review_note", "Use the amounts on the receipt and your tax classification. Leave blank anything you don't know. Saving creates a revision; approving is a separate step.")}</p>
    <label className="block text-[13px]">{t("business.dgii.form", "Form")}<select className={inputClass} value={form} disabled={!editable || uncertain} onChange={(event) => { change(); setForm(event.target.value === "607" ? "607" : "606"); setValues({}); }}><option value="606">606</option><option value="607">607</option></select></label>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">{fields?.[form].map((field) => {
      const common = field.name === "rnc" || field.name === "ncf" || field.name === "itbis";
      const value = field.name === "rnc" ? fiscal.rnc : field.name === "ncf" ? fiscal.ncf : field.name === "itbis" ? fiscal.itbis : values[field.name] ?? "";
      const setValue = (value: string) => { change(); if (common) setFiscal((current) => ({ ...current, [field.name]: value })); else setValues((current) => ({ ...current, [field.name]: value })); };
      const suggested = field.name === "category" && values.category_suggested === "true";
      return <label key={field.name} className="block text-[13px] text-black/65 dark:text-white/65">{field.label}{suggested ? <span className="ml-2 text-black/45 dark:text-white/45">{t("business.dgii.suggested", "Suggested")}</span> : null}{field.kind === "select" ? <select name={field.name} className={inputClass} value={value} disabled={!editable || uncertain} onChange={(event) => setValue(event.target.value)}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{field.options.map((option) => <option key={option} value={option}>{option}</option>)}</select> : <input name={field.name} className={inputClass} type={field.kind === "date" ? "date" : "text"} inputMode={field.kind === "money" ? "decimal" : undefined} value={value} disabled={!editable || uncertain} onChange={(event) => setValue(event.target.value)} />}</label>;
    })}</div>
    {form === "606" ? <div className="my-4 space-y-3"><label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={actualRefund} disabled={!editable || uncertain} onChange={(event) => { change(); setActualRefund(event.target.checked); }} />{t("business.dgii.actual_refund", "Money was refunded for this credit note")}</label>{actualRefund ? <RefundCandidates candidates={candidates} chosen={values.purchase_activity_id ?? ""} refused={refused} disabled={!editable || uncertain} locale={locale} onChoose={(id) => { change(); setRefused(null); setValues((current) => ({ ...current, purchase_activity_id: id })); }} /> : null}</div> : null}
    {problem ? <p role="alert" className="my-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{problem}</p> : null}
    {dossier.review_state === "open" && dossier.capabilities.includes("prepare") ? <button type="button" className={`${secondaryButtonClass} mt-3`} disabled={!editable || !fields} onClick={() => void save()}>{t("business.dgii.save", "Save tax review")}</button> : null}
    {editable && !uncertain ? <button type="button" className={`${secondaryButtonClass} ml-2 mt-3`} onClick={reset}>{t("common.cancel", "Cancel")}</button> : null}
  </details>;
}

/**
 * The purchases the server says this refund may name, newest first. A refused
 * pick stays chosen with the reason under it, and the others stay open to pick.
 */
function RefundCandidates({ candidates, chosen, refused, disabled, locale, onChoose }: { candidates: readonly RefundCandidate[]; chosen: string; refused: string | null; disabled: boolean; locale: string; onChoose: (id: string) => void }) {
  const { t } = useTranslation();
  return <fieldset data-testid="refund-candidates" className="text-[13px]">
    <legend className="text-black dark:text-white">{t("business.dgii.original_purchase", "Original purchase")}</legend>
    {candidates.length ? <ul className="mt-2 divide-y divide-[#EEF0EC] rounded-item border border-[#DCE0DA] dark:divide-white/[0.06] dark:border-white/10">
      {candidates.map((purchase) => <li key={purchase.id} data-testid="refund-candidate" data-refused={refused === purchase.id ? "true" : undefined}>
        <label className="flex min-h-11 items-center gap-3 px-3 py-2">
          <input type="radio" name="refund-purchase" value={purchase.id} checked={chosen === purchase.id} disabled={disabled} onChange={() => onChoose(purchase.id)} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] text-[#172b26] dark:text-white">{purchase.merchant ?? UNKNOWN_VALUE}</span>
            <span className="block text-[#56635e] dark:text-white/65">{formatDay(purchase.occurred_on, locale)}</span>
          </span>
          <span className="shrink-0 tabular-nums text-[14px] text-[#172b26] dark:text-white">{formatMoney(purchase.amount, purchase.currency, locale) || UNKNOWN_VALUE}</span>
        </label>
        {refused === purchase.id ? <p role="alert" data-testid="refund-candidate-refused" className="px-3 pb-2 text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.dgii.refund_candidate_refused", "That purchase can't be used for this refund. Pick another one.")}</p> : null}
      </li>)}
    </ul> : <p data-testid="refund-candidates-none" className="mt-2 text-[#56635e] dark:text-white/65">{t("business.dgii.refund_candidates_none", "There are no approved purchases to pick.")}</p>}
  </fieldset>;
}
