"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { prefersReducedMotion } from "./spring";
import { dampPull, PULL_IDLE, PULL_INDICATOR, PULL_SETTLE_MS, PULL_SLOP, pullFrame, pullStep, type PullEvent, type PullPhase, type RefreshOutcome } from "./pull-to-refresh";

const COARSE = "(pointer: coarse)";
const subscribeCoarse = (change: () => void) => {
  if (typeof window.matchMedia !== "function") return () => undefined;
  const query = window.matchMedia(COARSE);
  query.addEventListener("change", change);
  return () => query.removeEventListener("change", change);
};
const coarseSnapshot = () => typeof window.matchMedia === "function" && window.matchMedia(COARSE).matches;

type Gesture = { x: number; y: number; scroller: Element; pulling: boolean };

function scrollParent(node: HTMLElement): Element {
  for (let parent = node.parentElement; parent; parent = parent.parentElement) {
    const overflow = getComputedStyle(parent).overflowY;
    if (overflow === "auto" || overflow === "scroll") return parent;
  }
  return document.scrollingElement ?? document.documentElement;
}

/** A pull that starts inside something scrolled down scrolls that, not the list. */
function scrolledWithin(target: EventTarget | null, surface: HTMLElement): boolean {
  for (let node = target instanceof Element ? target : null; node && node !== surface; node = node.parentElement) {
    if (node.scrollTop > 0) return true;
  }
  return false;
}

const EASE = `${PULL_SETTLE_MS}ms cubic-bezier(0.2, 0.8, 0.2, 1)`;
const ARC = 2 * Math.PI * 7;

/**
 * Pull to refresh for a phone list (a coarse pointer below the tablet stop).
 * The pull starts only with the list at its top, follows the finger with
 * resistance, and on a release past the threshold runs `onRefresh`, the
 * list's own reload. The indicator stays until that reload answers; a failure
 * is the list's own to show, and both are said politely. Anywhere else, and
 * with a mouse, it renders its children and listens to nothing.
 */
export function PullToRefresh({ onRefresh, children }: { onRefresh: () => Promise<RefreshOutcome>; children: ReactNode }) {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const coarse = useSyncExternalStore(subscribeCoarse, coarseSnapshot, () => false);
  const enabled = isBelowTablet && coarse;
  const surface = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<PullPhase>(PULL_IDLE);
  const [reduced, setReduced] = useState(false);
  const [said, setSaid] = useState("");
  const current = useRef<PullPhase>(PULL_IDLE);
  const latest = useRef({ onRefresh, updated: "", failed: "" });
  const updated = t("common.refresh_updated", "Updated");
  const failed = t("common.refresh_failed", "We couldn't update.");
  useEffect(() => { latest.current = { onRefresh, updated, failed }; });

  const dispatch = useCallback((event: PullEvent) => {
    const before = current.current;
    const next = pullStep(before, event);
    if (next === before) return;
    current.current = next;
    setPhase(next);
    if (next.kind === "refreshing") setSaid("");
  }, []);

  // Entering refreshing is the one moment the reload runs: once per release.
  useEffect(() => {
    if (phase.kind !== "refreshing") return undefined;
    let live = true;
    const words = latest.current;
    words.onRefresh().catch((): RefreshOutcome => "failed").then((outcome) => {
      if (!live) return;
      setSaid(outcome === "updated" ? words.updated : words.failed);
      dispatch({ kind: "settled", outcome });
    });
    return () => { live = false; };
  }, [phase.kind, dispatch]);

  useEffect(() => {
    if (phase.kind !== "settling") return undefined;
    const timer = setTimeout(() => dispatch({ kind: "rested" }), PULL_SETTLE_MS);
    return () => clearTimeout(timer);
  }, [phase, dispatch]);

  useEffect(() => {
    const node = surface.current;
    if (!enabled || !node) return undefined;
    let gesture: Gesture | null = null;
    const start = (event: TouchEvent) => {
      gesture = null;
      if (event.touches.length !== 1 || current.current.kind !== "idle") return;
      const scroller = scrollParent(node);
      if (scroller.scrollTop > 0 || scrolledWithin(event.target, node)) return;
      setReduced(prefersReducedMotion());
      gesture = { x: event.touches[0].clientX, y: event.touches[0].clientY, scroller, pulling: false };
    };
    const move = (event: TouchEvent) => {
      if (!gesture) return;
      if (event.touches.length !== 1) {
        if (gesture.pulling) dispatch({ kind: "cancel" });
        gesture = null;
        return;
      }
      const dx = event.touches[0].clientX - gesture.x;
      const dy = event.touches[0].clientY - gesture.y;
      if (!gesture.pulling) {
        if (Math.abs(dx) < PULL_SLOP && Math.abs(dy) < PULL_SLOP) return;
        // Sideways belongs to the row or tray under the finger, upward to the scroll.
        if (dy <= Math.abs(dx) || gesture.scroller.scrollTop > 0) {
          gesture = null;
          return;
        }
        gesture.pulling = true;
      }
      // Only a pull already under way holds the page still, so the browser's own bounce or reload never joins it.
      if (event.cancelable) event.preventDefault();
      dispatch({ kind: "move", distance: dampPull(Math.max(0, dy - PULL_SLOP)) });
    };
    const end = (kind: "release" | "cancel") => () => {
      if (gesture?.pulling) dispatch({ kind });
      gesture = null;
    };
    const release = end("release");
    const cancel = end("cancel");
    node.addEventListener("touchstart", start, { passive: true });
    node.addEventListener("touchmove", move, { passive: false });
    node.addEventListener("touchend", release, { passive: true });
    node.addEventListener("touchcancel", cancel, { passive: true });
    return () => {
      node.removeEventListener("touchstart", start);
      node.removeEventListener("touchmove", move);
      node.removeEventListener("touchend", release);
      node.removeEventListener("touchcancel", cancel);
      if (gesture?.pulling) dispatch({ kind: "cancel" });
    };
  }, [enabled, dispatch]);

  const frame = pullFrame(phase, reduced);
  const moving = frame.content !== 0;
  return (
    <div ref={surface} data-testid="pull-to-refresh" data-phase={phase.kind} className="relative">
      {enabled ? (
        <>
          <div
            aria-hidden="true"
            data-testid="pull-indicator"
            className="pointer-events-none absolute left-1/2 top-0 z-10 flex items-center justify-center rounded-full border border-black/[0.06] bg-white text-[var(--cuadrao-green)] shadow-[0_1px_3px_rgba(0,0,0,0.08)] dark:border-white/10 dark:bg-[#1f2225]"
            style={{
              width: PULL_INDICATOR,
              height: PULL_INDICATOR,
              marginLeft: -PULL_INDICATOR / 2,
              opacity: frame.opacity,
              transform: `translate3d(0, ${frame.indicator}px, 0) rotate(${frame.turn}turn)`,
              transition: frame.eased ? `transform ${EASE}, opacity ${EASE}` : "none",
              visibility: phase.kind === "idle" ? "hidden" : "visible",
            }}
          >
            <svg viewBox="0 0 18 18" width="18" height="18" className={frame.spinning ? "motion-safe:animate-spin" : undefined}>
              <circle cx="9" cy="9" r="7" fill="none" stroke="currentColor" strokeOpacity="0.18" strokeWidth="2" />
              <circle
                cx="9" cy="9" r="7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                strokeDasharray={ARC}
                strokeDashoffset={ARC * (1 - 0.8 * frame.progress)}
                transform="rotate(-90 9 9)"
                style={{ transition: frame.eased ? `stroke-dashoffset ${EASE}` : "none" }}
              />
            </svg>
          </div>
          <p aria-live="polite" role="status" data-testid="pull-announcement" className="sr-only">{said}</p>
        </>
      ) : null}
      <div
        aria-busy={phase.kind === "refreshing" || undefined}
        style={moving || frame.eased ? { transform: moving ? `translate3d(0, ${frame.content}px, 0)` : undefined, transition: frame.eased ? `transform ${EASE}` : "none" } : undefined}
      >
        {children}
      </div>
    </div>
  );
}
