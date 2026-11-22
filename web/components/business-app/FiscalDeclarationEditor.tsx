"use client";

import { businessDateMessage } from "@/lib/business-date-errors";

import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link2, Loader2, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessDossier, RefundCandidate } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiField, DgiiFields, DgiiReview } from "@/lib/business-dgii";
import { referenceCode } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { resolveLanguage } from "@/lib/language-features";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { DatePicker } from "./foundation/DatePicker";
import styles from "./dossier/dossier.module.css";
import { REVIEW_INPUT_CLASS, ReviewSelect } from "./ReceiptFieldControls";
import type { BusinessDataSource } from "./business-data";
import ReceiptRowSave from "./ReceiptRowSave";
import type { RowSave } from "./receipt-review-save";
import { fiscalFieldGroups, foldsBehindRow, type FiscalGroup } from "./fiscal-field-groups";
import { dgiiOptionLabel } from "./receipt-fact-presentation";
import { usePreview } from "./useAmountsPreview";

const EDITOR_ID = "fiscal-declaration";
const FIELD_NOTE_CLASS = "text-[#9e2f39] dark:text-[#ec9aa0]";
const MONEY_NOTE_CLASS = "[&_p[aria-live]]:mt-1 [&_p[aria-live]]:min-h-5 [&_p[aria-live]]:text-[13px] [&_p[aria-live]]:leading-5";
// A switched-off amount or date dims like a switched-off select or text field.
const OFF_FIELD_CLASS = "[&_.rounded-item:has(>input:disabled)]:bg-[#eceeea] [&_input:disabled]:text-[#56635e] [&_input:disabled]:opacity-100 dark:[&_.rounded-item:has(>input:disabled)]:bg-[#263b35] dark:[&_input:disabled]:text-white/70";
const OWN_ROWS: ReadonlySet<string> = new Set(["rnc", "ncf", "category", "payment_method"]);
type Links = NonNullable<BusinessDossier["inheritance"]>;

/**
 * The Datos fiscales tab: the declaration's fields in grouped cards, each a row
 * of the dossier's grid. A field that follows a source says so in its status
 * slot, and holding it apart offers the way back there. Retenciones stays
 * folded on a purchase until someone adds one. Guardar sends the whole form.
 */
export default function FiscalDeclarationEditor({ dossier, fields, disabled, reviewFiscal, previewLinks, onChanged, onBusy, onDirty, saved = false }: { dossier: BusinessDossier; fields: DgiiFields | null; disabled: boolean; /** Whether this revision is the one this form just saved; held by the page for the same reason. */ saved?: boolean; /** The server's preview of the unsaved form: what each linked field shows. */ previewLinks?: BusinessDataSource["previewAmounts"]; reviewFiscal: (id: string, version: number, review: DgiiReview, key: string) => Promise<BusinessDossier>; onChanged: (value: BusinessDossier) => void; onBusy: (value: boolean) => void; onDirty: (value: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const recordForm = dossier.facts.kind.value === "income" ? "607" : "606";
  const formFollows = dossier.facts.kind.state === "known" && (dossier.dgii?.form ?? recordForm) === recordForm;
  const [form, setForm] = useState<"606" | "607">(dossier.dgii?.form ?? recordForm);
  const initialValues = () => Object.fromEntries([
    ...Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")]),
    ...Object.entries(dossier.inheritance ?? {}).filter(([, entry]) => entry.inherited).map(([name, entry]) => [name, entry.value ?? ""]),
  ]);
  const [stored] = useState<Record<string, string>>(initialValues);
  const [values, setValues] = useState(stored);
  // What this person did to a field that follows a source, until Save: false holds it apart, true puts it back.
  const [links, setLinks] = useState<ReadonlyMap<string, boolean>>(new Map());
  const fiscal = { rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" };
  const [actualRefund, setActualRefund] = useState(dossier.dgii?.actual_refund === true);
  const [broken, setBroken] = useState<ReadonlySet<string>>(new Set());
  const [checked, setChecked] = useState(false);
  const [resets, setResets] = useState(0);
  // A field's control keeps text that never became a value, so putting a value back remounts that control.
  const [fieldResets, setFieldResets] = useState<Readonly<Record<string, number>>>({});
  const [saving, setSaving] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [problem, setProblem] = useState<Extract<RowSave, { state: "failed" }> | null>(null);
  const [unfolded, setUnfolded] = useState(false);
  // The purchase the server refused for this refund: the choice stays, and the person picks another.
  const [refused, setRefused] = useState<string | null>(null);
  const candidates = dossier.refund_candidates ?? [];
  const request = useRef<{ key: string; version: number; input: DgiiReview } | null>(null);
  useEffect(() => () => { onDirty(false); onBusy(false); }, [onBusy, onDirty]);
  const preparing = dossier.review_state === "open" && dossier.capabilities.includes("prepare");
  const editable = preparing && !disabled && !saving;
  const change = () => { setDirty(true); onDirty(true); };
  const reset = () => {
    setForm(dossier.dgii?.form ?? recordForm);
    setValues(stored);
    setLinks(new Map());
    setActualRefund(dossier.dgii?.actual_refund === true);
    setBroken(new Set()); setChecked(false); setResets((value) => value + 1);
    setProblem(null); setRefused(null); setDirty(false); onDirty(false); setUnfolded(false);
  };
  // The links apply to the record's own form; another form's draft follows none of them.
  const given: Links = form === (dossier.dgii?.form ?? recordForm) ? dossier.inheritance ?? {} : {};
  const follows = (name: string, shown: Links) => links.get(name) ?? shown[name]?.inherited;
  /** The review Guardar sends. A field that follows its source goes as the dossier gave it: the server works out its value. */
  const draft = (): DgiiReview | null => {
    if (!fields) return null;
    const declaration: DgiiDeclaration = { form };
    for (const field of fields[form]) if (field.name !== "rnc" && field.name !== "ncf") declaration[field.name] = (follows(field.name, given) ? stored[field.name] : values[field.name]) || null;
    if (form === "606") { if (values.category_suggested === "true") declaration.category_suggested = true; declaration.actual_refund = actualRefund; declaration.purchase_activity_id = values.purchase_activity_id || null; }
    const changed = (linked: boolean) => [...links].filter(([, value]) => value === linked).map(([name]) => name);
    const montos = { ...(changed(false).length ? { override_inherited: changed(false) } : {}), ...(changed(true).length ? { restore_inherited: changed(true) } : {}) };
    return { fiscal: { rnc: fiscal.rnc || null, ncf: fiscal.ncf || null, itbis: fiscal.itbis || null }, declaration, ...(Object.keys(montos).length ? { montos } : {}) };
  };
  const unsaved = dirty ? draft() : null;
  const preview = usePreview(previewLinks, dossier, unsaved && { declaration: unsaved.declaration, override_inherited: unsaved.montos?.override_inherited, restore_inherited: unsaved.montos?.restore_inherited });
  // What each linked field shows: the server's last answer for this draft, or the dossier's.
  const known: Links = unsaved ? preview.last?.inheritance ?? given : given;
  const paired = (name: string) => [name, ...(known[name]?.paired_with ?? [])];
  const save = async () => {
    const input = draft();
    if (!input || !editable) return;
    if (broken.size) { setChecked(true); return; }
    request.current ??= { key: randomId(), version: dossier.version, input };
    const pending = request.current;
    setSaving(true); onBusy(true); setProblem(null); setRefused(null);
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
    } finally { setSaving(false); onBusy(false); }
  };
  // Restaurar changes the form alone. Guardar sends it.
  const restore = (name: string) => {
    const restored = paired(name);
    change();
    setLinks((current) => { const next = new Map(current); for (const side of restored) next.set(side, true); return next; });
    setBroken((current) => { const kept = new Set(current); for (const side of restored) kept.delete(side); return kept; });
    setFieldResets((current) => ({ ...current, ...Object.fromEntries(restored.map((side) => [side, (current[side] ?? 0) + 1])) }));
  };
  const locked = !editable || uncertain;
  const currency = dossier.facts.currency.value ?? "";
  const groupTitle: Record<FiscalGroup, string> = {
    identity: t("business.dossier.card.report", { form }),
    amounts: t("business.dossier.card.billed"),
    itbis: t("business.dossier.field.itbis", "ITBIS"),
    retentions: t("business.dossier.placeholder.group_retentions", "Withholdings"),
    other: t("business.dossier.card.other_taxes"),
  };
  const fieldControl = (field: DgiiField): ReactNode => {
    const id = `${EDITOR_ID}-${field.name}`;
    const inherited = known[field.name];
    const linked = follows(field.name, known);
    const value = (linked ? inherited?.value : values[field.name]) ?? "";
    const setValue = (next: string, invalid = false) => {
      // A field held apart with this one keeps the value it showed.
      const held = inherited ? paired(field.name) : [];
      setLinks((current) => { const next = new Map(current); for (const side of held) next.set(side, false); return next; });
      change();
      setValues((current) => ({ ...current, ...Object.fromEntries(held.filter((side) => follows(side, known)).map((side) => [side, known[side]?.value ?? ""])), [field.name]: next }));
      setBroken((current) => { const kept = new Set(current); if (invalid) kept.add(field.name); else kept.delete(field.name); return kept; });
    };
    const label = t([`business.dgii.field_${form}.${field.name}`, `business.dgii.field.${field.name}`], { defaultValue: field.name });
    // A source that is not money says its own name and shows its value as the field does.
    const sourceLabel = inherited?.field === "occurred_on" ? t("business.dossier.field.occurred_on") : inherited?.field === "rnc" || inherited?.field === "original_ncf" ? t(`business.dossier.placeholder.inherited_${inherited.field}`) : t(`business.terms.${inherited?.field}`);
    const sourceValue = inherited?.value == null ? UNKNOWN_VALUE : inherited.field === "occurred_on" ? formatDay(inherited.value, locale) : inherited.field === "rnc" ? dgiiOptionLabel(t, field.name, inherited.value) : inherited.field === "original_ncf" ? inherited.value : formatMoney(inherited.value, currency, locale) || UNKNOWN_VALUE;
    const inheritedLabel = t("business.terms.inherited_from", { field: sourceLabel });
    const restoreLabel = t("business.dossier.placeholder.restore_inherited", { value: sourceValue });
    // The status slot: the link a field follows, or the way back to it once a person held the field apart.
    const slot = !inherited ? null : linked ? value === "" ? null
      : <Tooltip content={inheritedLabel} side="top"><span tabIndex={0} role="img" aria-label={inheritedLabel} data-inherited={field.name} className={styles.icon}><Link2 size={16} aria-hidden="true" /></span></Tooltip>
      : <Tooltip content={restoreLabel} side="top"><button type="button" aria-label={restoreLabel} data-restore-inherited={field.name} className={styles.pen} style={{ opacity: 1, width: 24, height: 24 }} disabled={locked} onClick={() => restore(field.name)}><RotateCcw size={14} aria-hidden="true" /></button></Tooltip>;
    const dateProblem = checked && broken.has(field.name);
    const control = field.kind === "date" ? <DatePicker key={fieldResets[field.name]} id={id} label={label} value={value} disabled={locked} invalid={dateProblem} onChange={(iso, invalid) => setValue(iso ?? "", invalid)} />
      : field.kind === "money" ? <div className={MONEY_NOTE_CLASS}><MoneyInput key={fieldResets[field.name]} flush label={label} currency={currency} value={value || null} allowZero disabled={locked} testId={id} onValueChange={({ value: next, invalid }) => setValue(next ?? "", invalid)} /></div>
      : field.kind === "select" ? <ReviewSelect id={id} name={field.name} value={value} disabled={locked} onChange={(event) => setValue(event.target.value)}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{field.options.map((option) => <option key={option} value={option}>{dgiiOptionLabel(t, field.name, option)}</option>)}</ReviewSelect>
      : <input id={id} name={field.name} className={REVIEW_INPUT_CLASS} autoComplete="off" value={value} disabled={locked} onChange={(event) => setValue(event.target.value)} />;
    return (
      <li key={field.name} className={styles.row} data-field={field.name}>
        <label htmlFor={id} className={styles.label}>{label}</label>
        <span className={styles.slot}>{slot}</span>
        <div className={styles.wide}>{control}</div>
        {dateProblem ? <div role="alert" className={`${styles.below} ${FIELD_NOTE_CLASS}`}>{t("business.date_range.invalid_date", { format: t("business.date_picker.placeholder", "dd/mm/aaaa"), defaultValue: "Enter a valid date as {{format}}." })}</div> : null}
      </li>
    );
  };
  return <div className={`${styles.stack} @container`} data-testid={EDITOR_ID}>
    {formFollows ? null : <section className={styles.card}><ul className={styles.rows}><li className={styles.row}>
      <label htmlFor={`${EDITOR_ID}-form`} className={styles.label}>{t("business.dgii.form", "Form")}</label>
      <span className={styles.slot} />
      <div className={styles.wide}><ReviewSelect id={`${EDITOR_ID}-form`} value={form} disabled={locked} onChange={(event) => { change(); setForm(event.target.value === "607" ? "607" : "606"); setValues({}); setLinks(new Map()); setBroken(new Set()); setResets((value) => value + 1); }}><option value="606">606</option><option value="607">607</option></ReviewSelect></div>
    </li></ul></section>}
    <div key={resets} className={`${styles.stack} ${OFF_FIELD_CLASS}`}>
      {fiscalFieldGroups(fields?.[form].filter((field) => !OWN_ROWS.has(field.name)) ?? []).map(({ group, fields: grouped }) => {
        const folds = foldsBehindRow(form, group, grouped, values, broken);
        const fieldsId = `${EDITOR_ID}-${group}-fields`;
        const folded = folds && !unfolded;
        return <section key={group} className={styles.card} aria-label={groupTitle[group]} data-group={group}>
          <div className={styles.cardHead}>
            <h3 className={styles.cardTitle}>{groupTitle[group]}</h3>
            {folds ? <button type="button" aria-expanded={unfolded} aria-controls={fieldsId} className={styles.link} data-danger={unfolded || undefined} onClick={() => setUnfolded((current) => !current)}>{unfolded ? t("business.dossier.fiscal.remove") : t("business.dossier.fiscal.add_retention")}</button> : null}
          </div>
          {folded ? <p className={styles.emptyLine}>{t("business.dossier.fiscal.no_retentions")}</p> : null}
          <ul id={fieldsId} hidden={folded} className={styles.rows}>{grouped.map(fieldControl)}</ul>
        </section>;
      })}
    </div>
    {form === "606" ? <section className={styles.card}><div className={`${styles.cardBody} space-y-3`}><label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={actualRefund} disabled={!editable || uncertain} onChange={(event) => { change(); setActualRefund(event.target.checked); }} />{t("business.dgii.actual_refund", "Money was refunded for this credit note")}</label>{actualRefund ? <RefundCandidates candidates={candidates} chosen={values.purchase_activity_id ?? ""} refused={refused} disabled={!editable || uncertain} locale={locale} onChoose={(id) => { change(); setRefused(null); setValues((current) => ({ ...current, purchase_activity_id: id })); }} /> : null}</div></section> : null}
    {preparing ? <>
      <p className={styles.note}>{t("business.dgii.review_note", "Use the amounts on the receipt and your tax classification. Leave blank anything you don't know. Saving creates a revision; approving is a separate step.")}</p>
      <div className={styles.bar}>
        <button type="button" className={primaryButtonClass} aria-busy={saving} disabled={!editable || !fields} onClick={() => void save()}>
          {/* The resting label keeps its width while saving, so Cancelar stays where it was. */}
          <span className="grid justify-items-center [&>*]:col-start-1 [&>*]:row-start-1">
            <span className={saving ? "invisible" : undefined}>{t("business.dgii.save", "Save")}</span>
            {saving ? <span className="flex items-center gap-2"><Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" /><span role="status">{t("business.capture.saving", "Saving…")}</span></span> : null}
          </span>
        </button>
        <button type="button" className={secondaryButtonClass} disabled={!editable || uncertain} onClick={reset}>{t("common.cancel", "Cancel")}</button>
      </div>
    </> : null}
    <ReceiptRowSave save={problem ?? (saved && !dirty ? { state: "saved" } : undefined)} onRetry={() => void save()} />
  </div>;
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
