"use client";

import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { referenceCode } from "@/lib/failure-screen";
import { useBusiness } from "../BusinessWorkspace";
import { formatMoney } from "../business-format";
import { showToast } from "../foundation/toasts";
import { createBankTransaccionesSource } from "./transacciones-adapter";
import { createSampleTransaccionesSource } from "./transacciones-sample";
import { magnitude, suggestionRun, UNKNOWN, type Decision, type Movement, type TransaccionesSource, type TransaccionesView } from "./transacciones-model";

const OverrideContext = createContext<TransaccionesSource | null>(null);

/** Tests and previews hand the screen a source of their own. */
export function TransaccionesSourceOverride({ source, children }: { source: TransaccionesSource; children: ReactNode }) {
  return createElement(OverrideContext.Provider, { value: source }, children);
}

/** The screen's source: an override, the sample beside the sample workspace, or today's bank routes. */
function useTransaccionesSource(): TransaccionesSource {
  const override = useContext(OverrideContext);
  const { source, chosen } = useBusiness();
  const scope = chosen?.space_id ?? "own";
  return useMemo(
    () => override ?? (source.mode === "fixture" ? createSampleTransaccionesSource() : createBankTransaccionesSource()),
    // A new Business starts a new source, so nothing decided in one shows in another.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [override, source.mode, scope],
  );
}

export type ListState = { kind: "loading" } | { kind: "failed" } | { kind: "ready"; view: TransaccionesView };

/** The tray: which row, and whether it shows the record or asks why it needs no proof. `run` holds the suggestion run's rows in order. */
export type TrayState = Readonly<{ movementId: string; mode: "record" | "reasons"; run: readonly string[] | null }>;

export type DecisionFailure = Readonly<{ movementId: string; decision: Decision; reference: string }>;

export const movementName = (movement: Movement) => movement.counterparty ?? movement.bankText ?? UNKNOWN;

const newKey = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `k-${Date.now()}-${Math.random()}`);

/**
 * Transacciones' working state: the list, the tray and the run, and every
 * decision. A decision reads the list again once the server takes it; the
 * screen never moves a row on its own. A toast only confirms; a failure stays
 * inline in the tray with Reintentar.
 */
export function useTransacciones() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "es-419";
  const source = useTransaccionesSource();
  const { period, revision } = useBusiness();
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [reloads, setReloads] = useState(0);
  const [tray, setTray] = useState<TrayState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<DecisionFailure | null>(null);
  // Igualadas confirmed in a row share one toast and one Deshacer.
  const batch = useRef<Decision[]>([]);

  const load = useCallback(async () => {
    const view = await source.load({ from: period.from, to: period.to });
    setList({ kind: "ready", view });
    return view;
  }, [source, period.from, period.to]);

  useEffect(() => {
    let cancelled = false;
    setList((current) => (current.kind === "ready" ? current : { kind: "loading" }));
    source.load({ from: period.from, to: period.to }).then(
      (view) => { if (!cancelled) setList({ kind: "ready", view }); },
      () => { if (!cancelled) setList({ kind: "failed" }); },
    );
    return () => { cancelled = true; };
  }, [source, period.from, period.to, revision, reloads]);

  const retryLoad = useCallback(() => {
    setList({ kind: "loading" });
    setReloads((value) => value + 1);
  }, []);

  const movements = useMemo(() => (list.kind === "ready" ? list.view.movements : []), [list]);
  const byId = useMemo(() => new Map(movements.map((movement) => [movement.id, movement])), [movements]);

  const undoAll = useCallback(async (decisions: readonly Decision[]) => {
    if (!source.undo) return;
    for (const decision of [...decisions].reverse()) await source.undo(decision);
    batch.current = [];
    await load().catch(() => setList({ kind: "failed" }));
  }, [load, source]);

  const confirmToast = useCallback((decision: Decision, movement: Movement, inRun: boolean) => {
    const undo = source.undo ? (decisions: readonly Decision[]) => ({ label: t("business.transactions.undo", "Deshacer"), run: () => void undoAll(decisions) }) : () => undefined;
    if (decision.kind === "igualar") {
      batch.current = inRun ? [...batch.current, decision] : [decision];
      const decisions = batch.current;
      const text = decisions.length > 1
        ? t("business.transactions.toast.igualadas", "{{count}} igualadas", { count: decisions.length })
        : t("business.transactions.toast.igualada", "Igualada: {{name}}, {{amount}}", { name: movementName(movement), amount: formatMoney(magnitude(movement.money).amount, movement.money.currency, locale) });
      showToast({ kind: "success", text, action: undo(decisions) });
      return;
    }
    batch.current = [];
    const text = decision.kind === "rechazar"
      ? t("business.transactions.toast.rechazada", "Quitamos esa sugerencia")
      : decision.kind === "sin_comprobante"
        ? t("business.transactions.toast.sin_comprobante", "Marcada: {{reason}}", { reason: t(`business.transactions.reasons.${decision.reason}`) })
        : t("business.transactions.toast.desigualada", "Desigualada: {{name}}", { name: movementName(movement) });
    showToast({ kind: "success", text, action: undo([decision]) });
  }, [locale, source.undo, t, undoAll]);

  const decide = useCallback(async (decision: Decision) => {
    const movement = byId.get(decision.movementId);
    if (!movement || busy) return;
    const run = tray?.run ?? null;
    setBusy(decision.movementId);
    setFailure(null);
    try {
      await source.decide(decision, newKey());
    } catch (error) {
      setBusy(null);
      setFailure({ movementId: decision.movementId, decision, reference: referenceCode(error) });
      setTray((current) => ({ movementId: decision.movementId, mode: "record", run: current?.run ?? null }));
      return;
    }
    const view = await load().catch(() => null);
    setBusy(null);
    confirmToast(decision, movement, run !== null);
    if (!view) return;
    // The run moves on to the next suggestion still pending; the last one closes the tray.
    if (run) {
      const pending = new Set(suggestionRun(view.movements).map((row) => row.id));
      const next = run.slice(run.indexOf(decision.movementId) + 1).find((id) => pending.has(id));
      setTray(next ? { movementId: next, mode: "record", run } : null);
    } else if (tray?.movementId === decision.movementId) {
      setTray((current) => (current ? { ...current, mode: "record" } : current));
    }
  }, [busy, byId, confirmToast, load, source, tray]);

  const retry = useCallback(() => {
    if (failure) void decide(failure.decision);
  }, [decide, failure]);

  const open = useCallback((movementId: string, mode: TrayState["mode"] = "record") => {
    setFailure((current) => (current && current.movementId !== movementId ? null : current));
    setTray((current) => ({ movementId, mode, run: current?.run?.includes(movementId) ? current.run : null }));
  }, []);

  const startRun = useCallback(() => {
    const run = suggestionRun(movements).map((row) => row.id);
    batch.current = [];
    if (run.length) setTray({ movementId: run[0], mode: "record", run });
  }, [movements]);

  const close = useCallback(() => {
    batch.current = [];
    setTray(null);
    setFailure(null);
  }, []);

  return { source, list, movements, byId, tray, open, close, startRun, decide, busy, failure, retry, retryLoad };
}

export type TransaccionesController = ReturnType<typeof useTransacciones>;
