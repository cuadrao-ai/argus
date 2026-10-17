"use client";

import { useEffect, useRef } from "react";
import type { BusinessLocale } from "./content";
import { ExpenseStory } from "./expense-story";
import styles from "./owner-stories.module.css";

export function SupportingRecords({ locale }: { locale: BusinessLocale }) {
  const details = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    function revealTarget() {
      const target = window.location.hash;
      if (target !== "#gastos-documentos" && target !== "#preparar-registros") return;
      if (details.current) details.current.open = true;
      requestAnimationFrame(() => document.getElementById(target.slice(1))?.scrollIntoView({ block: "start", behavior: "instant" }));
    }
    revealTarget();
    window.addEventListener("hashchange", revealTarget);
    function onLink(event: MouseEvent) {
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (link?.getAttribute("href") === window.location.hash) revealTarget();
    }
    document.addEventListener("click", onLink);
    return () => { window.removeEventListener("hashchange", revealTarget); document.removeEventListener("click", onLink); };
  }, []);
  return <details ref={details} className={styles.supporting}>
    <summary><span>{locale === "es" ? "También los documentos detrás de cada registro" : "The documents behind each record, too"}</span><span aria-hidden="true">+</span></summary>
    <ExpenseStory locale={locale} />
  </details>;
}
