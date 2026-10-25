"use client";

import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { HeaderSearch } from "./HeaderSearch";
import styles from "./business-header.module.css";

export default function BusinessHeader({ home, name, onSearch }: { home: boolean; name: string | null; onSearch?: () => void }) {
  const { t, i18n } = useTranslation();
  const greetingName = name?.trim();
  const greeting = greetingName ? t("business.overview.greeting", { name: greetingName }) : t("business.overview.greeting_unnamed");
  const date = new Date();
  const dateLabel = new Intl.DateTimeFormat(i18n.resolvedLanguage ?? resolveLanguage({}), { weekday: "long", month: "long", day: "numeric" }).format(date);
  return (
    <div data-business-search-anchor data-testid="business-desktop-header" className={styles.header}>
      {home ? <>
        <div className={styles.welcome}>
          <time dateTime={`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`} className={styles.date}>{dateLabel}</time>
          <h1 id="business-overview-title" className={`${styles.greeting} font-display`}>{greeting}</h1>
        </div>
        {onSearch ? <div className={styles.search}><HeaderSearch onOpen={onSearch} /></div> : null}
      </> : null}
    </div>
  );
}
