"use client";

import { businessDateMessage } from "@/lib/business-date-errors";

import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Link2, Loader2, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessDossier, BusinessMontosReview, RefundCandidate } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiField, DgiiFields, DgiiReview } from "@/lib/business-dgii";
import { referenceCode } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { resolveLanguage } from "@/lib/language-features";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { DatePicker } from "./foundation/DatePicker";
import { SURFACE_CARD } from "./foundation/surfaces";
import { REVIEW_INPUT_CLASS, ReviewSelect } from "./ReceiptFieldControls";
import ReceiptRowSave from "./ReceiptRowSave";
import type { RowSave } from "./receipt-review-save";
import { fiscalFieldGroups, foldsBehindRow, type FiscalGroup } from "./fiscal-field-groups";
import { dgiiOptionLabel } from "./receipt-fact-presentation";

const EDITOR_ID = "fiscal-declaration";
const GROUP_TITLE_CLASS = "text-[12px] font-medium uppercase leading-4 tracking-[0.06em] text-[#56635e] dark:text-white/60";
const FIELD_LABEL_CLASS = "mb-1 block text-[13px] leading-[18px] text-[#56635e] dark:text-white/70";
const FIELD_NOTE_CLASS = "mt-1 block min-h-5 text-[13px] leading-5 text-[#9e2f39] dark:text-[#ec9aa0]";
const MONEY_NOTE_CLASS = "[&_p[aria-live]]:mt-1 [&_p[aria-live]]:min-h-5 [&_p[aria-live]]:text-[13px] [&_p[aria-live]]:leading-5";
// A switched-off amount or date dims like a switched-off select or text field.
const OFF_FIELD_CLASS = "[&_.rounded-item:has(>input:disabled)]:bg-[#eceeea] [&_input:disabled]:text-[#56635e] [&_input:disabled]:opacity-100 dark:[&_.rounded-item:has(>input:disabled)]:bg-[#263b35] dark:[&_input:disabled]:text-white/70";
const FOLD_ROW_CLASS = "-mx-2 flex min-h-11 w-[calc(100%+1rem)] items-center justify-between gap-3 rounded-item bg-[#f7f5ee] px-2 text-left hover:bg-[#efece3] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:bg-white/[0.04] dark:hover:bg-white/[0.07]";
const OWN_ROWS: ReadonlySet<string> = new Set(["rnc", "ncf", "category", "payment_method"]);

export default function FiscalDeclarationEditor({ dossier, fields, disabled, open, onOpenChange, reviewFiscal, reviewMontos, onChanged, onBusy, onDirty, saved = false }: { dossier: BusinessDossier; fields: DgiiFields | null; disabled: boolean; /** Held by the page, because a saved row gives this form a fresh revision. */ open?: boolean; onOpenChange?: (open: boolean) => void; /** Whether this revision is the one this form just saved; held by the page for the same reason. */ saved?: boolean; reviewMontos?: (id: string, version: number, review: BusinessMontosReview, key: string) => Promise<BusinessDossier>; reviewFiscal: (id: string, version: number, review: DgiiReview, key: string) => Promise<BusinessDossier>; onChanged: (value: BusinessDossier) => void; onBusy: (value: boolean) => void; onDirty: (value: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const recordForm = dossier.facts.kind.value === "income" ? "607" : "606";
  const formFollows = dossier.facts.kind.state === "known" && (dossier.dgii?.form ?? recordForm) === recordForm;
  const [form, setForm] = useState<"606" | "607">(dossier.dgii?.form ?? recordForm);
  const initialValues = () => Object.fromEntries([
    ...Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")]),
    ...Object.entries(dossier.inheritance ?? {}).filter(([, entry]) => entry.inherited).map(([name, entry]) => [name, entry.value ?? ""]),
  ]);
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [overrides, setOverrides] = useState<ReadonlySet<string>>(new Set());
  const fiscal = { rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" };
  const [actualRefund, setActualRefund] = useState(dossier.dgii?.actual_refund === true);
  const [broken, setBroken] = useState<ReadonlySet<string>>(new Set());
  const [checked, setChecked] = useState(false);
  const [resets, setResets] = useState(0);
  const [busy, setBusy] = useState<"save" | "restore" | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [problem, setProblem] = useState<Extract<RowSave, { state: "failed" }> | null>(null);
  const [unfolded, setUnfolded] = useState(false);
  // The purchase the server refused for this refund: the choice stays, and the person picks another.
  const [refused, setRefused] = useState<string | null>(null);
  const candidates = dossier.refund_candidates ?? [];
  const request = useRef<{ key: string; version: number; input: DgiiReview } | null>(null);
  const restoreRequest = useRef<{ key: string; field: string } | null>(null);
  useEffect(() => () => { onDirty(false); onBusy(false); }, [onBusy, onDirty]);
  const preparing = dossier.review_state === "open" && dossier.capabilities.includes("prepare");
  const editable = preparing && !disabled && busy === null;
  const change = () => { setDirty(true); onDirty(true); };
  const reset = () => {
    setForm(dossier.dgii?.form ?? recordForm);
    setValues(initialValues());
    setOverrides(new Set());
    setActualRefund(dossier.dgii?.actual_refund === true);
    setBroken(new Set()); setChecked(false); setResets((value) => value + 1);
    setProblem(null); setRefused(null); setDirty(false); onDirty(false); setUnfolded(false);
  };
  const save = async () => {
    if (!fields || !editable) return;
    if (broken.size) { setChecked(true); return; }
    const declaration: DgiiDeclaration = { form };
    for (const field of fields[form]) if (field.name !== "rnc" && field.name !== "ncf") declaration[field.name] = values[field.name] || null;
    if (form === "606") { if (values.category_suggested === "true") declaration.category_suggested = true; declaration.actual_refund = actualRefund; declaration.purchase_activity_id = values.purchase_activity_id || null; }
    const input: DgiiReview = { fiscal: { rnc: fiscal.rnc || null, ncf: fiscal.ncf || null, itbis: fiscal.itbis || null }, declaration, ...(overrides.size ? { montos: { override_inherited: [...overrides] } } : {}) };
    request.current ??= { key: randomId(), version: dossier.version, input };
    const pending = request.current;
    setBusy("save"); onBusy(true); setProblem(null); setRefused(null);
    try {
      const value = await reviewFiscal(dossier.draft_id, pending.version, pending.input, pending.key);
      request.current = null; onDirty(false); setUncertain(false); onChanged(value);
    } catch (error) {
      const { status, code } = error as { status?: number; code?: string };
      const lost = !(status && status >= 400 && status < 500);
      if (lost) setUncertain(true);
      else request.current = null;
      // Until the server leaves owner-paid purchases out of the list, picking one is refused this way.
      const purchase = pending.input.declaration.purchase_activity_id;
      if (status === 422 && code === "recorded_correction_unsupported" && typeof purchase === "string") { setRefused(purchase); return; }
      setProblem({ state: "failed", message: businessDateMessage(error, t, locale) || t(`business.dgii.error.${code}`, "") || t("business.dgii.save_failed", "We couldn't confirm the tax details were saved. Check the current record before you approve."), reference: referenceCode(error), retry: lost, unknown: lost });
    } finally { setBusy(null); onBusy(false); }
  };
  const restore = async (field: string) => {
    if (!reviewMontos || !editable) return;
    restoreRequest.current ??= { key: randomId(), field };
    const pending = restoreRequest.current;
    setRestoring(pending.field);
    setBusy("restore"); onBusy(true); setProblem(null);
    try {
      const next = await reviewMontos(dossier.draft_id, dossier.version, { restore_inherited: [pending.field] }, pending.key);
      restoreRequest.current = null; setRestoring(null); setUncertain(false); onDirty(false); onChanged(next);
    } catch (error) {
      const { status } = error as { status?: number };
      const lost = !(status && status >= 400 && status < 500);
      if (lost) setUncertain(true);
      else { restoreRequest.current = null; setRestoring(null); }
      setProblem({ state: "failed", message: t("business.dgii.save_failed"), reference: referenceCode(error), retry: lost, unknown: lost });
    } finally { setBusy(null); onBusy(false); }
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
      if (dossier.inheritance?.[field.name]) setOverrides((current) => new Set([...current, field.name]));
      change();
      setValues((current) => ({ ...current, [field.name]: next }));
      setBroken((current) => { const kept = new Set(current); if (invalid) kept.add(field.name); else kept.delete(field.name); return kept; });
    };
    const label = t([`business.dgii.field_${form}.${field.name}`, `business.dgii.field.${field.name}`], { defaultValue: field.name });
    const inherited = dossier.inheritance?.[field.name];
    const linked = inherited?.inherited && !overrides.has(field.name);
    // A source that is not money says its own name and shows its value as the field does.
    const plainSource = inherited?.field === "occurred_on" || inherited?.field === "rnc" || inherited?.field === "original_ncf";
    const sourceLabel = inherited?.field === "occurred_on" ? t("business.dossier.field.occurred_on") : inherited?.field === "rnc" || inherited?.field === "original_ncf" ? t(`business.dossier.placeholder.inherited_${inherited.field}`) : t(`business.terms.${inherited?.field}`);
    const sourceValue = inherited?.value == null ? UNKNOWN_VALUE : inherited.field === "occurred_on" ? formatDay(inherited.value, locale) : inherited.field === "rnc" ? dgiiOptionLabel(t, field.name, inherited.value) : inherited.field === "original_ncf" ? inherited.value : formatMoney(inherited.value, currency, locale) || UNKNOWN_VALUE;
    const inheritedLabel = t("business.terms.inherited_from", { field: sourceLabel });
    const restoreLabel = plainSource ? t("business.dossier.placeholder.use_inherited_value", { field: sourceLabel, value: sourceValue }) : t("business.terms.use_inherited", { amount: sourceValue });
    const title = <span className={`${FIELD_LABEL_CLASS} flex items-center gap-1.5`}>{label}{inherited ? linked ? <Tooltip content={inheritedLabel} side="top"><span tabIndex={0} aria-label={inheritedLabel} data-inherited={field.name}><Link2 className="h-3.5 w-3.5" aria-hidden="true" /></span></Tooltip> : reviewMontos ? <Tooltip content={restoreLabel} side="top"><button type="button" aria-label={restoreLabel} data-restore-inherited={field.name} className="-my-2 flex h-9 w-9 items-center justify-center rounded-full hover:bg-black/[0.04] dark:hover:bg-white/[0.06]" disabled={!editable || dirty || uncertain && restoring !== field.name} onClick={() => void restore(field.name)}><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /></button></Tooltip> : null : null}</span>;
    const dateProblem = checked && broken.has(field.name);
    if (field.kind === "date") return <div key={field.name}>
      <label htmlFor={id}>{title}</label>
      <DatePicker id={id} label={label} value={value} disabled={locked} invalid={dateProblem} onChange={(iso, invalid) => setValue(iso ?? "", invalid)} />
      <span role={dateProblem ? "alert" : undefined} className={FIELD_NOTE_CLASS}>{dateProblem ? t("business.date_range.invalid_date", { format: t("business.date_picker.placeholder", "dd/mm/aaaa"), defaultValue: "Enter a valid date as {{format}}." }) : null}</span>
    </div>;
    if (field.kind === "money") return <label key={field.name} className={`block ${MONEY_NOTE_CLASS}`}>{title}<MoneyInput flush label={label} currency={currency} value={value || null} allowZero disabled={locked} testId={id} onValueChange={({ value: next, invalid }) => setValue(next ?? "", invalid)} /></label>;
    return <label key={field.name} className="block">{title}
      {field.kind === "select"
        ? <ReviewSelect id={id} name={field.name} value={value} disabled={locked} onChange={(event) => setValue(event.target.value)}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{field.options.map((option) => <option key={option} value={option}>{dgiiOptionLabel(t, field.name, option)}</option>)}</ReviewSelect>
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
    <div key={resets} className={`space-y-5 ${OFF_FIELD_CLASS}`}>
      {fiscalFieldGroups(fields?.[form].filter((field) => !OWN_ROWS.has(field.name)) ?? []).map(({ group, fields: grouped }) => {
        const folds = foldsBehindRow(form, group, grouped, values, broken);
        const fieldsId = `${EDITOR_ID}-${group}-fields`;
        return <section key={group} aria-label={groupTitle[group]} data-group={group}>
          <h4 className={folds ? (unfolded ? "mb-3" : undefined) : `${GROUP_TITLE_CLASS} mb-2`}>{folds ? <button type="button" aria-expanded={unfolded} aria-controls={fieldsId} className={FOLD_ROW_CLASS} onClick={() => setUnfolded((current) => !current)}>
            <span className={GROUP_TITLE_CLASS}>{groupTitle[group]}</span>
            <span className="flex items-center gap-2 text-[13px] leading-[18px] text-[#56635e] dark:text-white/60">{unfolded ? null : t("business.dgii.no_withholdings", "No withholdings")}<ChevronDown className={`h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none ${unfolded ? "rotate-180" : ""}`} aria-hidden="true" /></span>
          </button> : groupTitle[group]}</h4>
          <div id={fieldsId} hidden={folds && !unfolded} className="grid grid-cols-1 items-end gap-x-4 gap-y-1 @[26rem]:grid-cols-2">{grouped.map(fieldControl)}</div>
        </section>;
      })}
    </div>
    {form === "606" ? <div className="my-4 space-y-3"><label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={actualRefund} disabled={!editable || uncertain} onChange={(event) => { change(); setActualRefund(event.target.checked); }} />{t("business.dgii.actual_refund", "Money was refunded for this credit note")}</label>{actualRefund ? <RefundCandidates candidates={candidates} chosen={values.purchase_activity_id ?? ""} refused={refused} disabled={!editable || uncertain} locale={locale} onChoose={(id) => { change(); setRefused(null); setValues((current) => ({ ...current, purchase_activity_id: id })); }} /> : null}</div> : null}
    {preparing ? <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" className={primaryButtonClass} aria-busy={busy === "save"} disabled={!editable || !fields || restoring !== null} onClick={() => void save()}>
        {/* The resting label keeps its width while saving, so Cancelar stays where it was. */}
        <span className="grid justify-items-center [&>*]:col-start-1 [&>*]:row-start-1">
          <span className={busy === "save" ? "invisible" : undefined}>{t("business.dgii.save", "Save")}</span>
          {busy === "save" ? <span className="flex items-center gap-2"><Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" /><span role="status">{t("business.capture.saving", "Saving…")}</span></span> : null}
        </span>
      </button>
      <button type="button" className={secondaryButtonClass} disabled={!editable || uncertain} onClick={reset}>{t("common.cancel", "Cancel")}</button>
    </div> : null}
    <ReceiptRowSave save={problem ?? (saved && !dirty ? { state: "saved" } : undefined)} onRetry={() => void (restoring ? restore(restoring) : save())} />
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
