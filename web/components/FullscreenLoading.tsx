"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CuadraoLockup } from "./CuadraoLockup";
import styles from "./FullscreenLoading.module.css";

export default function FullscreenLoading() {
  const { t, i18n } = useTranslation();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 300);
    return () => window.clearTimeout(timer);
  }, []);

  if (!visible) return null;

  const label = (i18n.resolvedLanguage ?? i18n.language).startsWith("es")
    ? "Cargando"
    : t("common.loading", "Loading...");

  return (
    <div data-testid="fullscreen-loading" className={styles.screen}>
      <span className="sr-only" role="status" aria-live="polite">{label}</span>
      <div aria-hidden="true" className={styles.indicator}>
        <CuadraoLockup width={240} />
        <div data-testid="fullscreen-loading-track" className={styles.track}>
          <div data-testid="fullscreen-loading-sheen" className={styles.sheen} />
        </div>
      </div>
    </div>
  );
}
