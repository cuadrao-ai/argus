"use client";

import { useTranslation } from "react-i18next";
import type { RecordReadiness } from "@/lib/business-dossier";

/** Locale words follow the server's ordered list; an unknown code uses the existing fallback. */
export function useMissingWords(missing: readonly string[]) {
  const { t, i18n } = useTranslation();
  return missing.map((code) => {
    const key = `business.transactions.layout.workflow.missing.${code}`;
    return t(i18n.exists(key) ? key : "business.transactions.layout.workflow.missing.detail_missing");
  });
}

export function OpenRecordMissingReasons({ missing = [], reasons }: RecordReadiness) {
  const { t } = useTranslation();
  const words = missing.map(code => t(reasons?.[code]?.words ?? "business.transactions.layout.workflow.missing.detail_missing"));
  if (!words.length) return null;
  return <section className="mb-4 text-[13px]" aria-label={t("business.transactions.layout.column_reason")}>
    <p className="mb-1 font-medium">{t("business.transactions.layout.column_reason")}</p>
    <ul data-record-missing-list className="list-disc space-y-1 pl-4">{words.map((word, index) => <li key={index}>{word}</li>)}</ul>
  </section>;
}
