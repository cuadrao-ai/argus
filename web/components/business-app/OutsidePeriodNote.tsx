"use client";

import { useTranslation } from "react-i18next";
import { formatDay } from "./business-format";
import { quietButtonClass } from "./business-ui";

/** A saved expense the chosen period leaves out is named, never left to look vanished. */
export default function OutsidePeriodNote({ count, latestOn, onShowAll }: { count: number; latestOn: string | null; onShowAll: () => void }) {
  const { t, i18n } = useTranslation();
  if (!(count > 0)) return null;
  const date = latestOn ? formatDay(latestOn, i18n.resolvedLanguage ?? "en") : "";
  return (
    <p role="note" data-testid="business-outside-period" className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-black/65 dark:text-white/65">
      <span>{t("business.period.outside", { count, date, defaultValue: "{{count}} expenses saved outside this period, the latest on {{date}}." })}</span>
      <button type="button" onClick={onShowAll} className={quietButtonClass}>{t("business.period.show_all", "Show all")}</button>
    </p>
  );
}
