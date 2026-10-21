"use client";

import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { referenceCode } from "@/lib/failure-screen";
import { useBusiness } from "../BusinessWorkspace";
import { formatMoney, UNKNOWN_VALUE } from "../business-format";
import { showToast } from "../foundation/toasts";
import { createBankTransaccionesSource, createRecordsTransaccionesSource, decisionProblem, listChanged, type DecisionProblem } from "./transacciones-adapter";
import { useBankTransport, useIgualarEnabled } from "./transacciones-gate";
import { createSampleBankServer } from "./transacciones-sample";
import { inverse, magnitude, periodCount, suggestionRun, type Decision, type IgualarView, type Movement, type Segment, type TransaccionesSource, type TransaccionesView } from "./transacciones-model";
import { resolveLanguage } from "@/lib/language-features";

const OverrideContext = createContext<TransaccionesSource | null>(null);

/** Tests and previews hand the screen a source of their own. */
export function TransaccionesSourceOverride({ source, children }: { source: TransaccionesSource; children: ReactNode }) {
  return createElement(OverrideContext.Provider, { value: source }, children);
}

/**
 * The screen's source: an override; with igualar off, the period's saved
 * records; with it on, the bank routes (the sample bank beside the sample
 * workspace), which fall back to the records while the server has them off
 * or no statement is imported yet.
 */
function useTransaccionesSource(): TransaccionesSource {
  const override = useContext(OverrideContext);
  const igualar = useIgualarEnabled();
  const transport = useBankTransport();
  const { t } = useTranslation();
  const { source, chosen } = useBusiness();
  const ownerFunds = t("business.dossier.owner_funds", "Owner's money");
  const scope = chosen?.space_id ?? "own";
  return useMemo(() => {
    if (override) return override;
    const saved = createRecordsTransaccionesSource({ expenses: source.expenses, overview: source.overview, workspace: source.workspace, ownerFunds });
    if (!igualar) return saved;
    return createBankTransaccionesSource(source.mode === "fixture" && transport === "sample" ? createSampleBankServer() : undefined, saved);
    // A new Business starts a new source, so nothing decided in one shows in another.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [override, igualar, transport, source, ownerFunds, scope]);
}

/** A page of the list, and how many rows a re-read asks for so nothing loaded drops off. */
const PAGE = 50;
const MAX_PAGE = 200;

export type ListState = { kind: "loading" } | { kind: "failed" } | { kind: "ready"; view: TransaccionesView };
export type MoreState = { kind: "idle" } | { kind: "loading" } | { kind: "failed"; changed: boolean };

/** The tray: which row, and whether it shows the record or asks why it needs no proof. `run` holds the suggestion run's rows in order. */
export type TrayState = Readonly<{ movementId: string; mode: "record" | "reasons"; run: readonly string[] | null }>;

/** A decision the server did not take: the row as it stood, the key Reintentar sends again, and the way out. */
export type DecisionFailure = Readonly<{ movement: Movement; decision: Decision; key: string; problem: DecisionProblem; reference: string }>;

/** A decision the server took, and the row as it stood before, for Deshacer. */
type Taken = Readonly<{ decision: Decision; movement: Movement }>;

export const movementName = (movement: Movement) => movement.counterparty ?? movement.bankText ?? UNKNOWN_VALUE;

const newKey = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `k-${Date.now()}-${Math.random()}`);

/**
 * Transacciones' working state: the segment and its pages, the tray and the
 * run, and every decision. A decision reads the list again once the server
 * takes it; the screen never moves a row on its own. A toast only confirms; a
 * failure stays inline in the tray, Reintentar sending the same key again.
 */
export function useTransacciones() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const source = useTransaccionesSource();
  const { period, revision } = useBusiness();
  const [chosen, setChosen] = useState<Segment | null>(null);
  // With nothing to igualar in the period, the screen opens on Todas.
  const [fallback, setFallback] = useState<Segment>("por_igualar");
  const segment = chosen ?? fallback;
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [more, setMore] = useState<MoreState>({ kind: "idle" });
  const [reloads, setReloads] = useState(0);
  const [tray, setTray] = useState<TrayState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<DecisionFailure | null>(null);
  const [runWanted, setRunWanted] = useState(false);
  // Igualadas confirmed in a row share one toast and one Deshacer.
  const batch = useRef<Taken[]>([]);
  const loaded = useRef(0);

  useEffect(() => {
    setChosen(null);
    setFallback("por_igualar");
  }, [source, period.from, period.to]);

  const read = useCallback(async (limit = PAGE) => {
    const view = await source.load({ from: period.from, to: period.to, segment, limit });
    loaded.current = view.mode === "igualar" ? view.movements.length : 0;
    return view;
  }, [source, period.from, period.to, segment]);

  useEffect(() => {
    let cancelled = false;
    // A background read keeps the rows on screen, and focus with them; only another segment shows loading.
    setList((current) => (current.kind === "ready" && (current.view.mode === "records" || current.view.segment === segment) ? current : { kind: "loading" }));
    setMore({ kind: "idle" });
    read().then(
      (view) => {
        if (cancelled) return;
        if (view.mode === "igualar" && chosen === null && segment === "por_igualar" && periodCount(view.totals, "porIgualar") === 0) {
          setFallback("todas");
          return;
        }
        setList({ kind: "ready", view });
      },
      () => { if (!cancelled) setList({ kind: "failed" }); },
    );
    return () => { cancelled = true; };
    // `chosen` only matters for the first read of a period; a choice changes `segment`, which reads again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [read, revision, reloads]);

  /** Read the segment again with every row already shown, after the server took a decision. */
  const reread = useCallback(async () => {
    const view = await read(Math.min(MAX_PAGE, Math.max(PAGE, loaded.current)));
    setList({ kind: "ready", view });
    return view;
  }, [read]);

  const retryLoad = useCallback(() => {
    setList({ kind: "loading" });
    setReloads((value) => value + 1);
  }, []);

  const view: IgualarView | null = list.kind === "ready" && list.view.mode === "igualar" ? list.view : null;
  const movements = useMemo(() => view?.movements ?? [], [view]);
  const byId = useMemo(() => new Map(movements.map((movement) => [movement.id, movement])), [movements]);

  const loadMore = useCallback(async () => {
    if (!view?.nextCursor || more.kind === "loading") return;
    setMore({ kind: "loading" });
    try {
      const next = await source.load({ from: period.from, to: period.to, segment: view.segment, cursor: view.nextCursor, limit: PAGE });
      if (next.mode !== "igualar") throw new Error("bank: the list changed mode");
      const seen = new Set(view.movements.map((movement) => movement.id));
      const merged: IgualarView = { ...next, movements: [...view.movements, ...next.movements.filter((movement) => !seen.has(movement.id))] };
      loaded.current = merged.movements.length;
      setList({ kind: "ready", view: merged });
      setMore({ kind: "idle" });
    } catch (error) {
      setMore({ kind: "failed", changed: listChanged(error) });
    }
  }, [more.kind, period.from, period.to, source, view]);

  // Deshacer runs back through `decide`, which shows the toast that offers it; the ref breaks that loop.
  const decideRef = useRef<(decision: Decision, options?: { key?: string; undoing?: boolean; row?: Movement }) => Promise<void>>(async () => undefined);

  /** Deshacer: each decision's inverse, newest first, each its own request through the same path. */
  const undoAll = useCallback(async (taken: readonly Taken[]) => {
    batch.current = [];
    for (const { decision, movement } of [...taken].reverse()) {
      const back = inverse(decision);
      if (back) await decideRef.current(back, { undoing: true, row: movement });
    }
  }, []);

  const confirmToast = useCallback((decision: Decision, movement: Movement, inRun: boolean) => {
    const undoable = inverse(decision) !== null;
    const undo = (taken: readonly Taken[]) => (undoable ? { label: t("business.transactions.undo", "Deshacer"), run: () => void undoAll(taken) } : undefined);
    if (decision.kind === "igualar" || decision.kind === "igualar_con") {
      batch.current = inRun ? [...batch.current, { decision, movement }] : [{ decision, movement }];
      const decisions = batch.current;
      const name = movement.match.state === "sugerencia" ? movement.match.suggestion.document.counterparty ?? movementName(movement) : movementName(movement);
      const text = decisions.length > 1
        ? t("business.transactions.toast.igualadas", "{{count}} igualadas", { count: decisions.length })
        : t("business.transactions.toast.igualada", "Igualada: {{name}}, {{amount}}", { name, amount: formatMoney(magnitude(movement.money).amount, movement.money.currency, locale) });
      showToast({ kind: "success", text, action: undo(decisions) });
      return;
    }
    batch.current = [];
    const text = decision.kind === "rechazar"
      ? t("business.transactions.toast.rechazada", "Quitamos esa sugerencia")
      : decision.kind === "sin_comprobante"
        ? t("business.transactions.toast.sin_comprobante", "Marcada: {{reason}}", { reason: t(`business.transactions.reasons.${decision.reason}`) })
        : t("business.transactions.toast.desigualada", "Desigualada: {{name}}", { name: movementName(movement) });
    showToast({ kind: "success", text, action: undo([{ decision, movement }]) });
  }, [locale, t, undoAll]);

  const decide = useCallback(async (decision: Decision, options: { key?: string; undoing?: boolean; row?: Movement } = {}) => {
    const movement = options.row ?? byId.get(decision.movementId) ?? (failure?.movement.id === decision.movementId ? failure.movement : undefined);
    if (!movement || busy) return;
    const key = options.key ?? newKey();
    const run = tray?.run ?? null;
    setBusy(decision.movementId);
    setFailure(null);
    try {
      await source.decide(decision, key);
    } catch (error) {
      setBusy(null);
      setFailure({ movement, decision, key, problem: decisionProblem(error), reference: referenceCode(error) });
      setTray((current) => ({ movementId: decision.movementId, mode: "record", run: current?.run ?? null }));
      return;
    }
    const after = await reread().catch(() => null);
    setBusy(null);
    if (!options.undoing) confirmToast(decision, movement, run !== null);
    if (!after || after.mode !== "igualar") return;
    // The run moves on to the next suggestion still pending; the last one closes the tray.
    if (run) {
      const pending = new Set(suggestionRun(after).map((row) => row.id));
      const next = run.slice(run.indexOf(decision.movementId) + 1).find((id) => pending.has(id));
      setTray(next ? { movementId: next, mode: "record", run } : null);
    } else if (tray?.movementId === decision.movementId) {
      // A row that left the segment leaves the tray with it, so it never comes back open on another segment.
      const stays = after.movements.some((row) => row.id === decision.movementId);
      setTray((current) => (current && stays ? { ...current, mode: "record" } : null));
    }
  }, [busy, byId, confirmToast, failure, reread, source, tray]);
  useEffect(() => { decideRef.current = decide; }, [decide]);

  /** The way out of a failed decision: the same request with the same key, or a fresh read of the list. */
  const recover = useCallback(() => {
    if (!failure) return;
    if (failure.problem.action === "retry") {
      void decide(failure.decision, { key: failure.key });
      return;
    }
    setFailure(null);
    void reread().catch(() => setList({ kind: "failed" }));
  }, [decide, failure, reread]);

  const open = useCallback((movementId: string, mode: TrayState["mode"] = "record") => {
    setFailure((current) => (current && current.movement.id !== movementId ? null : current));
    setTray((current) => ({ movementId, mode, run: current?.run?.includes(movementId) ? current.run : null }));
  }, []);

  const choose = useCallback((next: Segment) => {
    setChosen(next);
  }, []);

  // The run walks the Por igualar segment, where the server lists suggestions most confident first.
  useEffect(() => {
    if (!runWanted || !view || view.segment !== "por_igualar") return;
    setRunWanted(false);
    const run = suggestionRun(view).map((row) => row.id);
    batch.current = [];
    if (run.length) setTray({ movementId: run[0], mode: "record", run });
  }, [runWanted, view]);

  const startRun = useCallback(() => {
    if (segment !== "por_igualar") setChosen("por_igualar");
    setRunWanted(true);
  }, [segment]);

  const close = useCallback(() => {
    batch.current = [];
    setTray(null);
    setFailure(null);
  }, []);

  return { source, list, view, segment, choose, movements, byId, more, loadMore, tray, open, close, startRun, decide, busy, failure, recover, retryLoad };
}

export type TransaccionesController = ReturnType<typeof useTransacciones>;
