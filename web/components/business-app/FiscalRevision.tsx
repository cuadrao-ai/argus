"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { DgiiDeclaration, DgiiField, DgiiFields } from "@/lib/business-dgii";
import { useBusiness } from "./BusinessWorkspace";
import { quietButtonClass } from "./business-ui";

export default function FiscalRevision({ declaration }: { declaration: DgiiDeclaration }) {
  const { t } = useTranslation();
  const { openPanel, source } = useBusiness();
  const [fields, setFields] = useState<DgiiFields | null>(null);
  useEffect(() => { let live = true; void source.dgiiFields().then((value) => { if (live) setFields(value); }).catch(() => {}); return () => { live = false; }; }, [source]);
  const shown = (field: DgiiField) => {
    const value = declaration[field.name];
    return value === null ? t("business.dossier.unknown", "Unknown") : field.labels?.[String(value)] ?? String(value);
  };
  return <details className="mt-3 text-[13px]"><summary className="min-h-11 cursor-pointer text-[#2f5a49] dark:text-[#8fcbb0]">{t("business.dgii.details", "Tax details for 606 / 607")}</summary><dl className="mt-2 space-y-2">{fields?.[declaration.form].filter((field) => field.name in declaration).map((field) => <div key={field.name}><dt className="text-black/55 dark:text-white/55">{field.label}</dt><dd className="break-words text-black/75 dark:text-white/75">{shown(field)}</dd></div>)}</dl>{typeof declaration.purchase_activity_id === "string" ? <button type="button" className={`${quietButtonClass} mt-2`} onClick={() => { const id = declaration.purchase_activity_id; if (typeof id === "string") openPanel({ kind: "expense", expenseId: id }); }}>{t("business.dgii.original_purchase", "Original purchase")}</button> : null}</details>;
}
