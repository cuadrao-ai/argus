"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CuadraoLockup } from "@/components/CuadraoLockup";
import { landingLanguageChoices, normalizeEnabledLanguage } from "@/lib/language-features";
import { SettingsMenu } from "@/components/SettingsMenu";
import entryStyles from "@/app/auth-entry.module.css";
import styles from "./recovery.module.css";

export function RecoveryShell({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const content = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>();
  useEffect(() => {
    if (!content.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setHeight(entry.borderBoxSize[0]?.blockSize ?? entry.target.getBoundingClientRect().height));
    observer.observe(content.current);
    return () => observer.disconnect();
  }, []);
  const languages = landingLanguageChoices(normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language));
  return (
    <main data-auth-split="true" className={`${entryStyles.screen} ${styles.screen}`}>
      <SettingsMenu />
      <div data-auth-logo className={styles.logo}>
        <span aria-label="Cuadrao"><CuadraoLockup width={268} /></span>
      </div>
      <div data-auth-brand="cuadrao" className={styles.panel}>
        <section className={styles.card} style={{ height }}>
          <div ref={content} className={styles.content}>{children}</div>
        </section>
        {languages.map(language => <button key={language.code} type="button" lang={language.code} className={styles.language}
          onClick={() => void i18n.changeLanguage(language.code)}>{language.name}</button>)}
      </div>
    </main>
  );
}
