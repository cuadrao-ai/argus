"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CuadraoLockup } from "./CuadraoLockup";
import { LOADING_TRACK } from "./business-app/foundation/presentation";
import styles from "./FullscreenLoading.module.css";

export default function FullscreenLoading() {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 300);
    return () => window.clearTimeout(timer);
  }, []);

  if (!visible) return null;

  const label = t("common.loading", "Cargando...");

  return (
    <div data-testid="fullscreen-loading" className={styles.screen}>
      <span className="sr-only" role="status" aria-live="polite">{label}</span>
      <div aria-hidden="true" className={styles.indicator}>
        <CuadraoLockup width={240} />
        <div data-testid="fullscreen-loading-track" className={styles.track} style={{ backgroundColor: LOADING_TRACK }}>
          <div data-testid="fullscreen-loading-sheen" className={styles.sheen} />
        </div>
      </div>
    </div>
  );
}
