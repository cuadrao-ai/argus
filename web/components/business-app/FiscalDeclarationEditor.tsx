"use client";

import { secondaryButtonClass } from "./business-ui";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessDossier } from "@/lib/business-dossier";
import { listBusinessExpenses, type BusinessExpense } from "@/lib/business-api";
import { getDgiiFields, reviewDgii, type DgiiDeclaration, type DgiiFields, type DgiiReview } from "@/lib/business-dgii";
import { randomId } from "@/lib/random-id";
import { SURFACE_CARD } from "./foundation/surfaces";

const inputClass = "mt-2 block min-h-11 w-full rounded-item border border-[#7d8a84] bg-[#FFFEFA] px-3 text-[16px] text-[#172b26] dark:bg-[#141517] dark:text-white";

export default function FiscalDeclarationEditor({ dossier, disabled, onChanged, onBusy, onDirty }: { dossier: BusinessDossier; disabled: boolean; onChanged: (value: BusinessDossier) => void; onBusy: (value: boolean) => void; onDirty: (value: boolean) => void }) {
  const { t } = useTranslation();
  const [fields, setFields] = useState<DgiiFields | null>(null);
  const [form, setForm] = useState<"606" | "607">((dossier.dgii?.form) ?? (dossier.facts.kind.value === "income" ? "607" : "606"));
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")])));
  const [fiscal, setFiscal] = useState(() => ({ rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" }));
  const [actualRefund, setActualRefund] = useState(dossier.dgii?.actual_refund === true);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [purchases, setPurchases] = useState<BusinessExpense[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const request = useRef<{ key: string; version: number; input: DgiiReview } | null>(null);
  useEffect(() => { let live = true; void getDgiiFields().then((value) => { if (live) setFields(value); }).catch(() => { if (live) setProblem(t("business.dgii.load_failed", "No se pudieron cargar los campos fiscales.")); }); return () => { live = false; }; }, [t]);
  useEffect(() => () => { onDirty(false); onBusy(false); }, [onBusy, onDirty]);
  useEffect(() => {
    let live = true;
    const day = dossier.facts.occurred_on.value;
    if (actualRefund && day) {
      const from = new Date(`${day}T12:00:00Z`); from.setUTCDate(from.getUTCDate() - 30);
      void listBusinessExpenses(from.toISOString().slice(0, 10), day).then((values) => { if (live) setPurchases(values); }).catch(() => { if (live) setProblem(t("business.dgii.purchases_failed", "No se pudieron cargar las compras originales.")); });
    }
    return () => { live = false; };
  }, [actualRefund, dossier.facts.occurred_on.value, t]);
  const editable = dossier.review_state === "open" && dossier.capabilities.includes("prepare") && !disabled && !busy;
  const change = () => onDirty(true);
  const reset = () => {
    setForm(dossier.dgii?.form ?? (dossier.facts.kind.value === "income" ? "607" : "606"));
    setValues(Object.fromEntries(Object.entries(dossier.dgii ?? {}).map(([name, value]) => [name, String(value ?? "")])));
    setFiscal({ rnc: dossier.facts.fiscal?.rnc.value ?? "", ncf: dossier.facts.fiscal?.ecf.value ?? dossier.facts.fiscal?.ncf.value ?? "", itbis: dossier.facts.fiscal?.itbis.value ?? "" });
    setActualRefund(dossier.dgii?.actual_refund === true);
    setProblem(null); onDirty(false);
  };
  const save = async () => {
    if (!fields || !editable) return;
    const declaration: DgiiDeclaration = { form };
    for (const field of fields[form]) if (!(field.name in fiscal)) declaration[field.name] = values[field.name] || null;
    if (form === "606") { declaration.actual_refund = actualRefund; declaration.purchase_activity_id = values.purchase_activity_id || null; }
    const input: DgiiReview = { fiscal: { rnc: fiscal.rnc || null, ncf: fiscal.ncf || null, itbis: fiscal.itbis || null }, declaration };
    request.current ??= { key: randomId(), version: dossier.version, input };
    setBusy(true); onBusy(true); setProblem(null);
    try {
      const pending = request.current;
      const value = await reviewDgii(dossier.draft_id, pending.version, pending.input, pending.key);
      request.current = null; onDirty(false); setUncertain(false); onChanged(value);
    } catch (error) {
      const { status, code } = error as { status?: number; code?: string };
      if (status && status >= 400 && status < 500) request.current = null;
      else setUncertain(true);
      setProblem(t(`business.dgii.error.${code}`, t("business.dgii.save_failed", "No se confirmó que los datos fiscales se guardaran. Revisa el registro actual antes de aprobar.")));
    } finally { setBusy(false); onBusy(false); }
  };
  return <details className={SURFACE_CARD} data-testid="fiscal-declaration">
    <summary className="min-h-11 cursor-pointer text-[14px] font-medium text-black dark:text-white">{t("business.dgii.details", "Datos fiscales para 606 / 607")}</summary>
    <p className="my-3 text-[13px] text-black/65 dark:text-white/65">{t("business.dgii.review_note", "Usa los montos del comprobante y tu clasificación fiscal. Deja en blanco los datos que no sabes. Guardar crea una revisión; aprobar es otro paso.")}</p>
    <label className="block text-[13px]">{t("business.dgii.form", "Formato")}<select className={inputClass} value={form} disabled={!editable || uncertain} onChange={(event) => { change(); setForm(event.target.value === "607" ? "607" : "606"); setValues({}); }}><option value="606">606</option><option value="607">607</option></select></label>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">{fields?.[form].map((field) => {
      const common = field.name === "rnc" || field.name === "ncf" || field.name === "itbis";
      const value = field.name === "rnc" ? fiscal.rnc : field.name === "ncf" ? fiscal.ncf : field.name === "itbis" ? fiscal.itbis : values[field.name] ?? "";
      const setValue = (value: string) => { change(); if (common) setFiscal((current) => ({ ...current, [field.name]: value })); else setValues((current) => ({ ...current, [field.name]: value })); };
      const suggested = field.name === "category" && values.category_suggested === "true";
      return <label key={field.name} className="block text-[13px] text-black/65 dark:text-white/65">{field.label}{suggested ? <span className="ml-2 text-black/45 dark:text-white/45">{t("business.dgii.suggested", "Sugerido")}</span> : null}{field.kind === "select" ? <select className={inputClass} value={value} disabled={!editable || uncertain} onChange={(event) => setValue(event.target.value)}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{field.options.map((option) => <option key={option} value={option}>{option}</option>)}</select> : <input className={inputClass} type={field.kind === "date" ? "date" : "text"} inputMode={field.kind === "money" ? "decimal" : undefined} value={value} disabled={!editable || uncertain} onChange={(event) => setValue(event.target.value)} />}</label>;
    })}</div>
    {form === "606" ? <div className="my-4 space-y-3"><label className="flex min-h-11 items-center gap-2 text-[13px]"><input type="checkbox" checked={actualRefund} disabled={!editable || uncertain} onChange={(event) => { change(); setActualRefund(event.target.checked); }} />{t("business.dgii.actual_refund", "Se recibió un reembolso de dinero por esta nota de crédito")}</label>{actualRefund ? <label className="block text-[13px]">{t("business.dgii.original_purchase", "Compra original")}<select className={inputClass} value={values.purchase_activity_id ?? ""} disabled={!editable || uncertain} onChange={(event) => { change(); setValues((current) => ({ ...current, purchase_activity_id: event.target.value })); }}><option value="">{t("business.dossier.unknown", "Unknown")}</option>{purchases.map((purchase) => <option key={purchase.id} value={purchase.id}>{purchase.merchant ?? purchase.occurred_on} · {purchase.amount} {purchase.currency}</option>)}</select></label> : null}</div> : null}
    {problem ? <p role="alert" className="my-3 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{problem}</p> : null}
    {dossier.review_state === "open" && dossier.capabilities.includes("prepare") ? <button type="button" className={`${secondaryButtonClass} mt-3`} disabled={!editable || !fields} onClick={() => void save()}>{t("business.dgii.save", "Guardar revisión fiscal")}</button> : null}
    {editable && !uncertain ? <button type="button" className={`${secondaryButtonClass} ml-2 mt-3`} onClick={reset}>{t("common.cancel", "Cancel")}</button> : null}
  </details>;
}
