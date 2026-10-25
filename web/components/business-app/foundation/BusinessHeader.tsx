"use client";

import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { HeaderSearch } from "./HeaderSearch";
import styles from "./business-header.module.css";
import HomeGreeting from "./HomeGreeting";
import { useHomeClock } from "./home-greeting";

export default function BusinessHeader({ home, name, title, onSearch }: { home: boolean; name: string | null; title?: string; onSearch?: () => void }) {
  const { i18n } = useTranslation();
  const clock = useHomeClock(home);
  const date = clock?.date;
  const dateLabel = date ? new Intl.DateTimeFormat(i18n.resolvedLanguage ?? resolveLanguage({}), { weekday: "long", month: "long", day: "numeric" }).format(date) : "";
  return (
    <div data-business-search-anchor data-testid="business-desktop-header" className={styles.header}>
      {home ? <>
        <div className={styles.welcome}>
          <time dateTime={date ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}` : undefined} className={styles.date} style={{ minHeight: "1.5em" }}>{dateLabel}</time>
          <h1 id="business-overview-title" className={`${styles.greeting} font-display`}><HomeGreeting period={clock?.period ?? null} name={name} /></h1>
        </div>
        {onSearch ? <div className={styles.search}><HeaderSearch onOpen={onSearch} /></div> : null}
      </> : title ? <div className={styles.welcome}>
        <span aria-hidden="true" className={styles.date} style={{ height: "1.5em" }} />
        <h1 className={`${styles.greeting} font-display`}>{title}</h1>
      </div> : null}
    </div>
  );
}
