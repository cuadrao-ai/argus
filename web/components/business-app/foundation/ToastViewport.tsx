"use client";

import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { dismissToast, springEasing, toastDuration, useToasts, type Toast, type ToastKind } from "./toasts";

const SPRING = springEasing(180, 20);
const GAP_PX = 8;
const SWIPE_DISMISS_PX = 80;
const SWIPE_FLICK = 0.5;

/** Every kind carries an icon and a left border, so colour is never the only signal. */
const TONE: Record<ToastKind, { icon: LucideIcon; border: string; ink: string }> = {
  info: { icon: Info, border: "#56635e", ink: "text-[#56635e] dark:text-white/70" },
  success: { icon: CircleCheck, border: "#2f5a49", ink: "text-[#2f5a49] dark:text-[#8fcbb0]" },
  warning: { icon: TriangleAlert, border: "#735c14", ink: "text-[#735c14] dark:text-[#f6e7c1]" },
  error: { icon: CircleAlert, border: "#9e2f39", ink: "text-[#9e2f39] dark:text-[#ec9aa0]" },
};

/**
 * The one place toasts appear: bottom right on desktop, top on a phone, never
 * over the middle of the work. One at a time: a new one springs in and the
 * one it replaces leaves.
 */
export function ToastViewport() {
  const items = useToasts();
  const { isBelowTablet } = useResponsiveLayout();
  const [heights, setHeights] = useState<Record<number, number>>({});
  const edge = isBelowTablet ? "top" : "bottom";
  const newestFirst = [...items].reverse();
  // Each toast sits past every newer one: the sum of their heights and gaps.
  const offsets = newestFirst.map((_, index) => newestFirst.slice(0, index).reduce((sum, newer) => sum + (heights[newer.id] ?? 64) + GAP_PX, 0));
  return (
    <div
      data-testid="toast-viewport"
      data-edge={edge}
      className={`pointer-events-none fixed z-[140] ${edge === "top" ? "inset-x-4 top-[max(1rem,env(safe-area-inset-top))]" : "bottom-6 right-6 w-[min(380px,calc(100vw-3rem))]"}`}
    >
      {newestFirst.map((toast, index) => (
        <ToastCard
          key={toast.id}
          toast={toast}
          edge={edge}
          offset={offsets[index]}
          onHeight={(height) => setHeights((current) => (current[toast.id] === height ? current : { ...current, [toast.id]: height }))}
        />
      ))}
    </div>
  );
}

function ToastCard({ toast, edge, offset, onHeight }: { toast: Toast; edge: "top" | "bottom"; offset: number; onHeight: (height: number) => void }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const duration = toastDuration(toast);
  const remaining = useRef(duration ?? 0);
  const swipe = useRef<{ x: number; at: number } | null>(null);
  const [entered, setEntered] = useState(false);
  const [paused, setPaused] = useState(false);
  const [dragX, setDragX] = useState(0);
  const tone = TONE[toast.kind];
  const Icon = tone.icon;

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    onHeight(node.offsetHeight);
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => onHeight(node.offsetHeight));
    observer.observe(node);
    return () => observer.disconnect();
    // The measure callback changes every render; the node does not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  // Hover or focus pauses the clock; the time left resumes where it stopped.
  useEffect(() => {
    if (duration === null || paused) return undefined;
    const started = Date.now();
    const timer = window.setTimeout(() => dismissToast(toast.id), remaining.current);
    return () => {
      window.clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (Date.now() - started));
    };
  }, [duration, paused, toast.id]);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest("button")) return;
    swipe.current = { x: event.clientX, at: event.timeStamp };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (swipe.current) setDragX(event.clientX - swipe.current.x);
  };
  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const start = swipe.current;
    swipe.current = null;
    if (!start) return;
    const dx = event.clientX - start.x;
    const speed = Math.abs(dx) / Math.max(1, event.timeStamp - start.at);
    if (Math.abs(dx) > SWIPE_DISMISS_PX || speed > SWIPE_FLICK) dismissToast(toast.id);
    else setDragX(0);
  };

  const y = edge === "bottom" ? -offset : offset;
  const enterFrom = edge === "bottom" ? 24 : -24;
  return (
    <div
      ref={ref}
      role={toast.kind === "error" || toast.kind === "warning" ? "alert" : "status"}
      aria-live={toast.kind === "error" || toast.kind === "warning" ? "assertive" : "polite"}
      data-testid="toast"
      data-kind={toast.kind}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => { swipe.current = null; setDragX(0); }}
      style={{
        transform: `translate3d(${dragX}px, ${entered ? y : y + enterFrom}px, 0)`,
        opacity: entered ? Math.max(0.2, 1 - Math.abs(dragX) / 240) : 0,
        transition: dragX !== 0 ? "none" : `transform ${SPRING.durationMs}ms ${SPRING.easing}, opacity 160ms ease-out`,
        borderLeftColor: tone.border,
      }}
      className={`pointer-events-auto absolute inset-x-0 ${edge === "bottom" ? "bottom-0" : "top-0"} flex touch-pan-y items-start gap-3 rounded-[12px] border border-l-4 border-[#DCE0DA] bg-white py-2 pl-3 pr-1 motion-reduce:!transition-none dark:border-white/10 dark:bg-[#1f2225]`}
    >
      <Icon className={`mt-2.5 h-5 w-5 shrink-0 ${tone.ink}`} aria-hidden="true" />
      <p className="min-w-0 flex-1 break-words py-2 text-[14px] leading-5 text-[#172b26] dark:text-white">{toast.text}</p>
      {toast.action ? (
        <button
          type="button"
          onClick={() => { toast.action?.run(); dismissToast(toast.id); }}
          className="inline-flex min-h-11 shrink-0 items-center rounded-full px-3 text-[14px] font-medium text-[#2f5a49] hover:bg-[#2f5a49]/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-[#8fcbb0]"
        >
          {toast.action.label}
        </button>
      ) : null}
      <button
        type="button"
        aria-label={t("common.close", "Close")}
        onClick={() => dismissToast(toast.id)}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
