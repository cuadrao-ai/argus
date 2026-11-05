"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CuadraoLockup } from "./CuadraoLockup";
import { LOADING_TRACK } from "./business-app/foundation/presentation";
import styles from "./FullscreenLoading.module.css";

type RegisterLoading = (token: symbol) => () => void;
const LoadingClients = createContext<RegisterLoading | null>(null);

export function FullscreenLoadingBoundary({ children }: { children: ReactNode }) {
  const clients = useRef(new Set<symbol>());
  const [pending, setPending] = useState(false);
  const [visible, setVisible] = useState(false);
  const register = useCallback<RegisterLoading>((token) => {
    clients.current.add(token);
    setPending(true);
    return () => {
      clients.current.delete(token);
      setPending(clients.current.size > 0);
    };
  }, []);

  useEffect(() => {
    if (!pending) {
      setVisible(false);
      return;
    }
    const timer = window.setTimeout(() => setVisible(true), 300);
    return () => window.clearTimeout(timer);
  }, [pending]);

  return (
    <LoadingClients.Provider value={register}>
      <div className={styles.businessSurface}>
        <div hidden={pending}>{children}</div>
        {pending && visible ? <LoadingScreen /> : null}
      </div>
    </LoadingClients.Provider>
  );
}

export default function FullscreenLoading() {
  const register = useContext(LoadingClients);
  const [token] = useState(() => Symbol());
  useLayoutEffect(() => register?.(token), [register, token]);
  return register ? null : <StandaloneLoading />;
}

function StandaloneLoading() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 300);
    return () => window.clearTimeout(timer);
  }, []);

  if (!visible) return null;

  return <LoadingScreen />;
}

function LoadingScreen() {
  const { t } = useTranslation();
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
