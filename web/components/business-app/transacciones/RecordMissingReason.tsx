"use client";

import { useTranslation } from "react-i18next";
import type { RecordReadiness } from "@/lib/business-dossier";

export function useMissingWords(record?: RecordReadiness | null) {
  const { t } = useTranslation();
  const reasons = record?.reasons;
  return reasons && record?.missing ? record.missing.map(code => t(reasons[code].words)) : [];
}

export function OpenRecordMissingReasons(record: RecordReadiness) {
  const { t } = useTranslation();
  const words = useMissingWords(record);
  if (!words.length) return null;
  return <section className="mb-4 text-[13px]" aria-label={t("business.transactions.layout.column_reason")}>
    <p className="mb-1 font-medium">{t("business.transactions.layout.column_reason")}</p>
    <ul data-record-missing-list className="list-disc space-y-1 pl-4">{words.map((word, index) => <li key={index}>{word}</li>)}</ul>
  </section>;
}
