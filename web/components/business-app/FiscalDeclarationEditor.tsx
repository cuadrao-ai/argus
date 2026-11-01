"use client";

import { secondaryButtonClass } from "./business-ui";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessDossier, RefundCandidate } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiField, DgiiFields, DgiiReview } from "@/lib/business-dgii";
import { referenceCode } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { resolveLanguage } from "@/lib/language-features";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { DatePicker } from "./foundation/DatePicker";
import { SURFACE_CARD } from "./foundation/surfaces";
import { REVIEW_INPUT_CLASS, ReviewSelect } from "./ReceiptFieldControls";
import { fiscalFieldGroups, type FiscalGroup } from "./fiscal-field-groups";

const EDITOR_ID = "fiscal-declaration";
const GROUP_TITLE_CLASS = "text-[12px] font-medium uppercase leading-4 tracking-[0.06em] text-[#56635e] dark:text-white/60";
const FIELD_LABEL_CLASS = "mb-1 block text-[13px] leading-[18px] text-[#56635e] dark:text-white/70";
const FIELD_NOTE_CLASS = "mt-1 block min-h-5 text-[13px] leading-5 text-[#9e2f39] dark:text-[#ec9aa0]";
const MONEY_NOTE_CLASS = "[&_p[aria-live]]:mt-1 [&_p[aria-live]]:min-h-5 [&_p[aria-live]]:text-[13px] [&_p[aria-live]]:leading-5";
const OWN_ROWS: ReadonlySet<string> = new Set(["rnc", "ncf", "itbis", "category", "payment_method"]);

export default function FiscalDeclarationEditor({ dossier, fields, disabled, open, onOpenChange, reviewFiscal, onChanged, onBusy, onDirty }: { dossier: BusinessDossier; fields: DgiiFields | null; disabled: boolean; /** Held by the page, because a saved row gives this form a fresh revision. */ open?: boolean; onOpenChange?: (open: boolean) => void; reviewFiscal: (id: string, version: number, review: DgiiReview, key: string) => Promise<BusinessDossier>; onChanged: (value: BusinessDossier) => void; onBusy: (value: boolean) => void; onDirty: (value: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const recordForm = dossier.facts.kind.value === "income" ? "607" : "606";
  const formFollows = dossier.facts.kind.state === "known" && (dossier.dgii?.form ?? recordForm) === recordForm;
  const [form, setForm] = useState<"606" | "607">(dossier.dgii?.form ?? recordForm);
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")])));
  const fiscal = { rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" };
  const [actualRefund, setActualRefund] = useState(dossier.dgii?.actual_refund === true);
  const [broken, setBroken] = useState<ReadonlySet<string>>(new Set());
  const [checked, setChecked] = useState(false);
  const [resets, setResets] = useState(0);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [problem, setProblem] = useState<{ text: string; reference: string } | null>(null);
  // The purchase the server refused for this refund: the choice stays, and the person picks another.
  const [refused, setRefused] = useState<string | null>(null);
  const candidates = dossier.refund_candidates ?? [];
  const request = useRef<{ key: string; version: number; input: DgiiReview } | null>(null);
  useEffect(() => () => { onDirty(false); onBusy(false); }, [onBusy, onDirty]);
  const editable = dossier.review_state === "open" && dossier.capabilities.includes("prepare") && !disabled && !busy;
  const change = () => onDirty(true);
  const reset = () => {
    setForm(dossier.dgii?.form ?? recordForm);
    setValues(Object.fromEntries(Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")])));
    setActualRefund(dossier.dgii?.actual_refund === true);
    setBroken(new Set()); setChecked(false); setResets((value) => value + 1);
    setProblem(null); setRefused(null); onDirty(false);
  };
  const save = async () => {
    if (!fields || !editable) return;
    if (broken.size) { setChecked(true); return; }
    const declaration: DgiiDeclaration = { form };
    for (const field of fields[form]) if (!(field.name in fiscal)) declaration[field.name] = values[field.name] || null;
    if (form === "606") { if (values.category_suggested === "true") declaration.category_suggested = true; declaration.actual_refund = actualRefund; declaration.purchase_activity_id = values.purchase_activity_id || null; }
    const input: DgiiReview = { fiscal: { rnc: fiscal.rnc || null, ncf: fiscal.ncf || null, itbis: fiscal.itbis || null }, declaration };
    request.current ??= { key: randomId(), version: dossier.version, input };
    const pending = request.current;
    setBusy(true); onBusy(true); setProblem(null); setRefused(null);
    try {
      const value = await reviewFiscal(dossier.draft_id, pending.version, pending.input, pending.key);
      request.current = null; onDirty(false); setUncertain(false); onChanged(value);
    } catch (error) {
      const { status, code } = error as { status?: number; code?: string };
      if (status && status >= 400 && status < 500) request.current = null;
      else setUncertain(true);
      // Until the server leaves owner-paid purchases out of the list, picking one is refused this way.
      const purchase = pending.input.declaration.purchase_activity_id;
      if (status === 422 && code === "recorded_correction_unsupported" && typeof purchase === "string") { setRefused(purchase); return; }
      setProblem({ text: t(`business.dgii.error.${code}`, "") || t("business.dgii.save_failed", "We couldn't confirm the tax details were saved. Check the current record before you approve."), reference: referenceCode(error) });
    } finally { setBusy(false); onBusy(false); }
  };
  const locked = !editable || uncertain;
  const currency = dossier.facts.currency.value ?? "";
  const groupTitle: Record<FiscalGroup, string> = {
    identity: t("business.dossier.placeholder.group_identity", "Identification"),
    amounts: t("business.dossier.placeholder.group_amounts", "Amounts"),
    itbis: t("business.dossier.field.itbis", "ITBIS"),
    retentions: t("business.dossier.placeholder.group_retentions", "Withholdings"),
    other: t("business.dossier.placeholder.group_other", "Other"),
  };
  const fieldControl = (field: DgiiField): ReactNode => {
    const id = `${EDITOR_ID}-${field.name}`;
    const value = values[field.name] ?? "";
    const setValue = (next: string, invalid = false) => {
      if (next === value && invalid === broken.has(field.name)) return;
      change();
      setValues((current) => ({ ...current, [field.name]: next }));
      setBroken((current) => { const kept = new Set(current); if (invalid) kept.add(field.name); else kept.delete(field.name); return kept; });
    };
    const title = <span className={FIELD_LABEL_CLASS}>{field.label}</span>;
    const dateProblem = checked && broken.has(field.name);
    if (field.kind === "date") return <div key={field.name}>
      <label htmlFor={id}>{title}</label>
      <DatePicker id={id} label={field.label} value={value} disabled={locked} invalid={dateProblem} onChange={(iso, invalid) => setValue(iso ?? "", invalid)} />
      <span role={dateProblem ? "alert" : undefined} className={FIELD_NOTE_CLASS}>{dateProblem ? t("business.date_range.invalid_date", { format: t("business.date_picker.placeholder", "dd/mm/aaaa"), defaultValue: "Enter a valid date as {{format}}." }) : null}</span>
    </div>;
    if (field.kind === "money") return <label key={field.name} className={`block ${MONEY_NOTE_CLASS}`}>{title}<MoneyInput flush label={field.label} currency={currency} value={value || null} allowZero disabled={locked} testId={id} onValueChange={({ value: next, invalid }) => setValue(next ?? "", invalid)} /></label>;
    return <label key={field.name} className="block">{title}
      {field.kind === "select"
        ? <ReviewSelect id={id} name={field.name} value={value} disabled={locked} onChange={(event) => setValue(event.target.value)}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{field.options.map((option) => <option key={option} value={option}>{field.labels?.[option] ?? option}</option>)}</ReviewSelect>
        : <input id={id} name={field.name} className={REVIEW_INPUT_CLASS} autoComplete="off" value={value} disabled={locked} onChange={(event) => setValue(event.target.value)} />}
      <span className={FIELD_NOTE_CLASS} />
    </label>;
  };
  return <details className={`group ${SURFACE_CARD} @container`} data-testid={EDITOR_ID} open={open} onToggle={(event) => onOpenChange?.(event.currentTarget.open)}>
    <summary className="-m-2 flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-item p-2 font-display text-[16px] font-medium leading-6 text-[#172b26] hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white dark:hover:bg-white/[0.05] [&::-webkit-details-marker]:hidden">
      {t("business.dossier.placeholder.more_fiscal", "More tax details")}
      <ChevronDown className="h-4 w-4 shrink-0 text-[#56635e] transition-transform group-open:rotate-180 motion-reduce:transition-none dark:text-white/60" aria-hidden="true" />
    </summary>
    <p className="mb-5 mt-4 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{t("business.dgii.review_note", "Use the amounts on the receipt and your tax classification. Leave blank anything you don't know. Saving creates a revision; approving is a separate step.")}</p>
    {formFollows ? null : <label className="mb-5 block">
      <span className={FIELD_LABEL_CLASS}>{t("business.dgii.form", "Form")}</span>
      <ReviewSelect value={form} disabled={locked} onChange={(event) => { change(); setForm(event.target.value === "607" ? "607" : "606"); setValues({}); setBroken(new Set()); }}><option value="606">606</option><option value="607">607</option></ReviewSelect>
    </label>}
    <div key={resets} className="space-y-5">
      {fiscalFieldGroups(fields?.[form].filter((field) => !OWN_ROWS.has(field.name)) ?? []).map(({ group, fields: grouped }) => <section key={group} aria-label={groupTitle[group]} data-group={group}>
        <h4 className={`${GROUP_TITLE_CLASS} mb-2`}>{groupTitle[group]}</h4>
        <div className="grid grid-cols-1 items-end gap-x-4 gap-y-1 @[26rem]:grid-cols-2">{grouped.map(fieldControl)}</div>
      </section>)}
    </div>
    {form === "606" ? <div className="my-4 space-y-3"><label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={actualRefund} disabled={!editable || uncertain} onChange={(event) => { change(); setActualRefund(event.target.checked); }} />{t("business.dgii.actual_refund", "Money was refunded for this credit note")}</label>{actualRefund ? <RefundCandidates candidates={candidates} chosen={values.purchase_activity_id ?? ""} refused={refused} disabled={!editable || uncertain} locale={locale} onChoose={(id) => { change(); setRefused(null); setValues((current) => ({ ...current, purchase_activity_id: id })); }} /> : null}</div> : null}
    {problem ? <div role="alert" className="my-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]"><p>{problem.text}</p><ReferenceCode reference={problem.reference} /></div> : null}
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
