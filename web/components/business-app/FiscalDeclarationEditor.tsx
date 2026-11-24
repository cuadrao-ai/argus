"use client";

import { businessDateMessage } from "@/lib/business-date-errors";

import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import MoneyInput from "@/components/money/MoneyInput";
import type { BusinessDossier, RefundCandidate } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiField, DgiiFields, DgiiReview } from "@/lib/business-dgii";
import { referenceCode } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { resolveLanguage } from "@/lib/language-features";
import { formatAmount, formatDay, formatMoney, UNKNOWN_VALUE } from "./business-format";
import { DatePicker } from "./foundation/DatePicker";
import styles from "./dossier/dossier.module.css";
import { REVIEW_INPUT_CLASS, ReviewSelect } from "./ReceiptFieldControls";
import type { BusinessDataSource } from "./business-data";
import { DossierRow, RestoreButton, type RowEdit, type RowStatus } from "./dossier/DossierParts";
import ReceiptRowSave from "./ReceiptRowSave";
import type { RowSave } from "./receipt-review-save";
import { fiscalFieldLabel } from "./dossier/fiscal-field-label";
import { calculatedRows, fiscalFieldGroups, foldOf, recordForm, type FiscalForm, type FiscalGroup } from "./dossier/fiscal-rows";
import { dgiiOptionLabel } from "./receipt-fact-presentation";
import { usePreview } from "./useAmountsPreview";

const EDITOR_ID = "fiscal-declaration";
const FIELD_NOTE_CLASS = "text-[#9e2f39] dark:text-[#ec9aa0]";
// A switched-off amount or date dims like a switched-off select or text field.
const OFF_FIELD_CLASS = "[&_.rounded-item:has(>input:disabled)]:bg-[#eceeea] [&_input:disabled]:text-[#56635e] [&_input:disabled]:opacity-100 dark:[&_.rounded-item:has(>input:disabled)]:bg-[#263b35] dark:[&_input:disabled]:text-white/70";
type Links = NonNullable<BusinessDossier["inheritance"]>;

/**
 * The Datos fiscales tab: the declaration's fields in grouped cards, each a row
 * of the dossier's grid. A field that follows a source says so in its status
 * slot, and holding it apart offers the way back there. The amounts the server
 * calculates close their card with ƒ and never open; while an amount is being
 * typed they show the server's preview of it. Retenciones and Otros
 * impuestos stay folded until someone adds a row. NCF modificado shows on a
 * credit or debit note, and the refund question on a purchase's credit note
 * alone. Each row saves its own change and then shows its new value.
 */
export default function FiscalDeclarationEditor({ dossier, fields, disabled, reviewFiscal, previewLinks, montosCalculated, onChanged, onBusy, onDirty }: { dossier: BusinessDossier; fields: DgiiFields | null; disabled: boolean; /** The server's preview of the unsaved form: what each linked field shows. */ previewLinks?: BusinessDataSource["previewAmounts"]; /** What the server calculates for the amount an open Montos row holds, while it is unsaved. */ montosCalculated?: BusinessDossier["dgii_calculated"]; reviewFiscal: (id: string, version: number, review: DgiiReview, key: string) => Promise<BusinessDossier>; onChanged: (value: BusinessDossier) => void; onBusy: (value: boolean) => void; onDirty: (value: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  // The form is the declaration's own; a record with none declares on its kind's.
  const form: FiscalForm = dossier.dgii?.form ?? recordForm(dossier);
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
  const [editing, setEditing] = useState<string | null>(null);
  // A field's control keeps text that never became a value, so putting a value back remounts that control.
  const [fieldResets, setFieldResets] = useState<Readonly<Record<string, number>>>({});
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [problem, setProblem] = useState<Extract<RowSave, { state: "failed" }> | null>(null);
  const [unfolded, setUnfolded] = useState<ReadonlySet<FiscalGroup>>(new Set());
  // The purchase the server refused for this refund: the choice stays, and the person picks another.
  const [refused, setRefused] = useState<string | null>(null);
  const candidates = dossier.refund_candidates ?? [];
  const noteKind = dossier.note_kind ?? null;
  const [pending, setPending] = useState<{ key: string; version: number; input: DgiiReview } | null>(null);
  useEffect(() => () => { onDirty(false); onBusy(false); }, [onBusy, onDirty]);
  const editable = dossier.facts_editable === true && !disabled && !saving;
  const change = () => { setDirty(true); onDirty(true); };
  const reset = () => {
    setValues(stored);
    setLinks(new Map());
    setActualRefund(dossier.dgii?.actual_refund === true);
    setBroken(new Set()); setChecked(false); setEditing(null);
    setProblem(null); setRefused(null); setDirty(false); onDirty(false);
  };
  const given: Links = dossier.inheritance ?? {};
  const follows = (name: string, shown: Links) => links.get(name) ?? shown[name]?.inherited;
  /** The review Guardar sends. A field that follows its source goes as the dossier gave it: the server works out its value. */
  const draft = (): DgiiReview | null => {
    if (!fields) return null;
    const declaration: DgiiDeclaration = { form };
    for (const field of fields[form]) if (field.name !== "rnc" && field.name !== "ncf") declaration[field.name] = (follows(field.name, given) ? stored[field.name] : values[field.name]) || null;
    if (form === "606") { if (values.category_suggested === "true") declaration.category_suggested = true; declaration.actual_refund = actualRefund; declaration.purchase_activity_id = actualRefund ? values.purchase_activity_id || null : null; }
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
    if (!input || !editable || !editing) return;
    if (!dirty) { setEditing(null); return; }
    if (broken.size) { setChecked(true); return; }
    const request = pending ?? { key: randomId(), version: dossier.version, input };
    setSaving(true); onBusy(true); setProblem(null); setRefused(null);
    try {
      const value = await reviewFiscal(dossier.draft_id, request.version, request.input, request.key);
      setPending(null); setEditing(null); setDirty(false); onDirty(false); onChanged(value);
    } catch (error) {
      const { status, code } = error as { status?: number; code?: string };
      const lost = !(status && status >= 400 && status < 500);
      setPending(lost ? request : null);
      // Until the server leaves owner-paid purchases out of the list, picking one is refused this way.
      const purchase = request.input.declaration.purchase_activity_id;
      if (status === 422 && code === "recorded_correction_unsupported" && typeof purchase === "string") { setRefused(purchase); return; }
      const fallback = lost && dossier.review_state === "open" ? t("business.dgii.save_failed")
        : lost ? t("business.dossier.save_unconfirmed", { field: t("business.dossier.tab.fiscal") })
        : t("business.dossier.placeholder.save_refused", { field: t("business.dossier.tab.fiscal") });
      setProblem({ state: "failed", message: businessDateMessage(error, t, locale) || t(`business.dgii.error.${code}`, "") || fallback, reference: referenceCode(error), retry: lost, unknown: lost });
    } finally { setSaving(false); onBusy(false); }
  };
  // Restaurar changes the form alone. Guardar sends it.
  const restore = (name: string) => {
    const restored = paired(name);
    setEditing(name);
    change();
    setLinks((current) => { const next = new Map(current); for (const side of restored) next.set(side, true); return next; });
    setBroken((current) => { const kept = new Set(current); for (const side of restored) kept.delete(side); return kept; });
    setFieldResets((current) => ({ ...current, ...Object.fromEntries(restored.map((side) => [side, (current[side] ?? 0) + 1])) }));
  };
  const uncertain = pending !== null;
  const locked = !editable || uncertain;
  const canChange = (name: string) => !locked && (!editing || editing === name)
    && ((name !== "modified_ncf" && name !== "actual_refund") || dossier.editable_fields?.includes(name));
  const edit = (name: string, editor: ReactNode): RowEdit => ({
    open: editing === name,
    saving,
    locked: uncertain,
    disabled: !editable || !fields,
    onOpen: canChange(name) ? () => setEditing(name) : undefined,
    onSave: () => void save(),
    onCancel: reset,
    editor,
  });
  const note = (name: string) => editing === name && problem ? <ReceiptRowSave save={problem} onRetry={() => void save()} /> : null;
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
    const label = fiscalFieldLabel(t, form, field.name);
    // A source that is not money says its own name and shows its value as the field does.
    const sourceLabel = inherited?.field === "occurred_on" ? t("business.dossier.field.occurred_on") : inherited?.field === "rnc" || inherited?.field === "original_ncf" ? t(`business.dossier.placeholder.inherited_${inherited.field}`) : t(`business.terms.${inherited?.field}`);
    const sourceValue = inherited?.value == null ? UNKNOWN_VALUE : inherited.field === "occurred_on" ? formatDay(inherited.value, locale) : inherited.field === "rnc" ? dgiiOptionLabel(t, field.name, inherited.value) : inherited.field === "original_ncf" ? inherited.value : formatMoney(inherited.value, currency, locale) || UNKNOWN_VALUE;
    const inheritedLabel = t(`business.dossier.fiscal.source.${inherited?.field}`, { defaultValue: t("business.terms.inherited_from", { field: sourceLabel }) });
    // The status slot: the link a field follows, or the way back to it once a person held the field apart.
    const status: RowStatus | null = linked && value !== "" ? { kind: "link", text: inheritedLabel } : null;
    const readOnly = dossier.source_owned_fields?.includes(field.name) === true;
    const restoreAction = inherited && !linked && !readOnly && canChange(field.name)
      ? <RestoreButton field={field.name} value={sourceValue} onRestore={() => restore(field.name)} />
      : null;
    const dateProblem = checked && broken.has(field.name);
    const control = field.kind === "date" ? <DatePicker key={fieldResets[field.name]} id={id} label={label} value={value} disabled={locked} invalid={dateProblem} onChange={(iso, invalid) => setValue(iso ?? "", invalid)} />
      : field.kind === "money" ? <MoneyInput key={fieldResets[field.name]} flush label={label} currency={currency} value={value || null} allowZero disabled={locked} testId={id} onValueChange={({ value: next, invalid }) => setValue(next ?? "", invalid)} />
      : field.kind === "select" ? <ReviewSelect id={id} name={field.name} aria-label={label} value={value} disabled={locked} onChange={(event) => setValue(event.target.value)}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{field.options.map((option) => <option key={option} value={option}>{dgiiOptionLabel(t, field.name, option)}</option>)}</ReviewSelect>
      : <input id={id} name={field.name} className={REVIEW_INPUT_CLASS} autoComplete="off" aria-label={label} value={value} disabled={locked} onChange={(event) => setValue(event.target.value)} />;
    const shown = !value ? "" : field.kind === "date" ? formatDay(value, locale)
      : field.kind === "money" ? formatAmount(value, currency || "DOP", locale)
      : field.kind === "select" ? dgiiOptionLabel(t, field.name, value) : value;
    return <DossierRow key={field.name} row={field.name} data={{ "data-field": field.name, "data-inherited": status ? field.name : undefined }} label={label} value={shown} look={field.kind === "money" ? "number" : "text"} status={status} statusAction={restoreAction} edit={readOnly ? undefined : edit(field.name, control)} below={<>
      {dateProblem ? <div role="alert" className={FIELD_NOTE_CLASS}>{t("business.date_range.invalid_date", { format: t("business.date_picker.placeholder", "dd/mm/aaaa"), defaultValue: "Enter a valid date as {{format}}." })}</div> : null}
      {note(field.name)}
    </>} />;
  };
  const refundLabel = t("business.dgii.actual_refund", "Money was refunded for this credit note");
  const originalPurchase = actualRefund ? candidates.find((purchase) => purchase.id === values.purchase_activity_id) : undefined;
  const refundControl = <>
    <label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={actualRefund} disabled={locked} onChange={(event) => { change(); setActualRefund(event.target.checked); }} />{refundLabel}</label>
    {actualRefund ? <RefundCandidates candidates={candidates} chosen={values.purchase_activity_id ?? ""} refused={refused} disabled={locked || dossier.review_state === "accepted"} locale={locale} onChoose={(id) => { change(); setRefused(null); setValues((current) => ({ ...current, purchase_activity_id: id })); }} /> : null}
  </>;
  // The calculated amounts follow the server's preview of whatever is unsaved: this form, or an open Montos row.
  const calculated = calculatedRows((unsaved ? preview.last?.dgii_calculated : montosCalculated) ?? dossier.dgii_calculated);
  const calculatedRow = ({ row, amount }: { row: string; amount: string }) => <DossierRow key={row} row={row} look="number" total label={t(`business.dossier.placeholder.fiscal_${row}`)} value={formatAmount(amount, currency || "DOP", locale)} status={{ kind: "calculated", text: t(`business.dossier.placeholder.fiscal_${row}_hint`) }} />;
  return <div className={`${styles.stack} @container`} data-testid={EDITOR_ID}>
    <div className={`${styles.stack} ${OFF_FIELD_CLASS}`}>
      {fiscalFieldGroups(fields?.[form] ?? [], noteKind !== null, form === "607" ? dossier.sale_payment?.options : undefined).map(({ group, fields: grouped }) => {
        const fold = foldOf(group, grouped, values, broken);
        const fieldsId = `${EDITOR_ID}-${group}-fields`;
        const open = unfolded.has(group);
        const folded = fold !== null && !open && !grouped.some((field) => field.name === editing);
        return <section key={group} className={styles.card} aria-label={groupTitle[group]} data-group={group}>
          <div className={styles.cardHead}>
            <h3 className={styles.cardTitle}>{groupTitle[group]}</h3>
            {fold && dossier.facts_editable ? <button type="button" aria-expanded={open} aria-controls={fieldsId} className={styles.link} disabled={Boolean(editing)} data-danger={open || undefined} onClick={() => setUnfolded((current) => { const next = new Set(current); if (!next.delete(group)) next.add(group); return next; })}>{open ? t("business.dossier.fiscal.remove") : t(fold.add)}</button> : null}
          </div>
          {fold && folded ? <p className={styles.emptyLine}>{t(fold.empty)}</p> : null}
          <ul id={fieldsId} hidden={folded} className={styles.rows}>{grouped.map(fieldControl)}{calculated.filter((row) => row.group === group).map(calculatedRow)}</ul>
        </section>;
      })}
    </div>
    {form === "606" && noteKind === "credit" ? <section className={styles.card}><ul className={styles.rows}>
      <DossierRow row="actual_refund" label={refundLabel} value={t(actualRefund ? "business.marks.yes" : "business.marks.no")} edit={edit("actual_refund", refundControl)} below={<>
        {originalPurchase && editing !== "actual_refund" ? <RefundCandidates candidates={[originalPurchase]} chosen={originalPurchase.id} refused={null} disabled locale={locale} /> : null}
        {note("actual_refund")}
      </>} />
    </ul></section> : null}
  </div>;
}

/**
 * The purchases the server says this refund may name, newest first. A refused
 * pick stays chosen with the reason under it, and the others stay open to pick.
 */
function RefundCandidates({ candidates, chosen, refused, disabled, locale, onChoose }: { candidates: readonly RefundCandidate[]; chosen: string; refused: string | null; disabled: boolean; locale: string; onChoose?: (id: string) => void }) {
  const { t } = useTranslation();
  return <fieldset data-testid="refund-candidates" className="text-[13px]">
    <legend className="text-black dark:text-white">{t("business.dgii.original_purchase", "Original purchase")}</legend>
    {candidates.length ? <ul className="mt-2 divide-y divide-[#EEF0EC] rounded-item border border-[#DCE0DA] dark:divide-white/[0.06] dark:border-white/10">
      {candidates.map((purchase) => <li key={purchase.id} data-testid="refund-candidate" data-refused={refused === purchase.id ? "true" : undefined}>
        <label className="flex min-h-11 items-center gap-3 px-3 py-2">
          <input type="radio" name="refund-purchase" value={purchase.id} checked={chosen === purchase.id} disabled={disabled} onChange={() => onChoose?.(purchase.id)} />
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
