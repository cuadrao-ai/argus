"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getDgiiFields, type DgiiDeclaration, type DgiiFields } from "@/lib/business-dgii";
import { useBusiness } from "./BusinessWorkspace";

export default function FiscalRevision({ declaration }: { declaration: DgiiDeclaration }) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const [fields, setFields] = useState<DgiiFields | null>(null);
  useEffect(() => { let live = true; void getDgiiFields().then((value) => { if (live) setFields(value); }).catch(() => {}); return () => { live = false; }; }, []);
  return <details className="mt-3 text-[13px]"><summary className="min-h-11 cursor-pointer text-[#2f5a49] dark:text-[#8fcbb0]">{t("business.dgii.details", "Datos fiscales para 606 / 607")}</summary><dl className="mt-2 space-y-2">{fields?.[declaration.form].filter((field) => field.name in declaration).map((field) => <div key={field.name}><dt className="text-black/55 dark:text-white/55">{field.label}</dt><dd className="break-words text-black/75 dark:text-white/75">{declaration[field.name] === null ? t("business.dossier.unknown", "Unknown") : String(declaration[field.name])}</dd></div>)}</dl>{typeof declaration.purchase_activity_id === "string" ? <button type="button" className="mt-2 underline" onClick={() => { const id = declaration.purchase_activity_id; if (typeof id === "string") openPanel({ kind: "expense", expenseId: id }); }}>{t("business.dgii.original_purchase", "Compra original")}</button> : null}</details>;
}
