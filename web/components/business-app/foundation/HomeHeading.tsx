"use client";

import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import styles from "./business-header.module.css";
import HomeGreeting from "./HomeGreeting";
import { useHomeClock } from "./home-greeting";

/** Inicio's heading: the local date with the Business, then the greeting. The top bar and the page share this one owner. */
export function HomeHeading({ name, business, className = "" }: { name: string | null | undefined; business?: string; className?: string }) {
  const { i18n } = useTranslation();
  const clock = useHomeClock(true);
  const date = clock?.date;
  const dateLabel = date ? new Intl.DateTimeFormat(i18n.resolvedLanguage ?? resolveLanguage({}), { weekday: "long", month: "long", day: "numeric" }).format(date) : "";
  return (
    <div data-testid="home-heading" className={`min-w-0 ${className}`}>
      <time dateTime={date ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}` : undefined} className={styles.date} style={{ minHeight: "1.5em" }}>{dateLabel}{dateLabel && business ? <span> · {business}</span> : null}</time>
      <h1 id="business-overview-title" className={`${styles.greeting} font-display`}><HomeGreeting period={clock?.period ?? null} name={name ?? null} /></h1>
    </div>
  );
}
