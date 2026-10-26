"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { ChevronLeft, X } from "lucide-react";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useSheetStack } from "@/components/ui/sheetStack";

/**
 * A sheet rests at one of three snap points and nowhere in between: peek shows
 * a summary, half holds a form, full takes long content. Each sheet names the
 * snaps it allows. `fit` is only for menus and pickers, which hug their content.
 */
export type SheetSnap = "peek" | "half" | "full";
export type SheetSnaps = readonly SheetSnap[] | "fit";

/** Share of the screen height each snap takes. */
export const SHEET_SNAP_SHARE: Record<SheetSnap, number> = { peek: 0.32, half: 0.6, full: 0.94 };
const SNAP_ORDER: readonly SheetSnap[] = ["peek", "half", "full"];
const FIT_MAX_SHARE = 0.7;

const INTERACTIVE_SELECTOR = "a[href],button,input,select,textarea,[role='button']";

/** A flick at this speed (px/ms) closes the sheet from any height, or lifts it a snap when upward. */
const FLICK_VELOCITY = 0.6;
const DRAG_CAPTURE_THRESHOLD_PX = 3;

/**
 * Whether the gesture ended because the user let go, or because the browser
 * took it away. `pointercancel` is the second, and it decides nothing: the
 * grip sits directly above a scrolling body, so a downward drag the browser
 * reclaims as a scroll arrives here carrying exactly the travel and direction
 * that read as a dismissal.
 */
export type SheetGesturePhase = "release" | "cancel";
export type SheetRelease = { kind: "dismiss" } | { kind: "snap"; snap: SheetSnap | "fit" };

/**
 * Where a let-go sheet goes. Speed decides before distance: a downward flick
 * closes from any height and an upward flick lifts one snap. A slow drag closes
 * only below half of the lowest snap; otherwise it springs to the nearest snap.
 */
export function sheetRelease({
  heightPx,
  snapPx,
  from,
  velocityY,
  phase = "release",
}: {
  heightPx: number;
  /** Each allowed snap and its height in px. */
  snapPx: readonly { snap: SheetSnap | "fit"; px: number }[];
  from: SheetSnap | "fit";
  /** Positive is downward. */
  velocityY: number;
  phase?: SheetGesturePhase;
}): SheetRelease {
  if (phase === "cancel" || snapPx.length === 0) return { kind: "snap", snap: from };
  if (velocityY >= FLICK_VELOCITY) return { kind: "dismiss" };
  const ordered = [...snapPx].sort((a, b) => a.px - b.px);
  if (velocityY <= -FLICK_VELOCITY) {
    const higher = ordered.find((item) => item.px > (snapPx.find((entry) => entry.snap === from)?.px ?? heightPx));
    return { kind: "snap", snap: (higher ?? ordered[ordered.length - 1]).snap };
  }
  if (heightPx < ordered[0].px / 2) return { kind: "dismiss" };
  const nearest = ordered.reduce((best, item) => (Math.abs(item.px - heightPx) < Math.abs(best.px - heightPx) ? item : best));
  return { kind: "snap", snap: nearest.snap };
}

function useViewportHeight(): number {
  const [height, setHeight] = useState(() => (typeof window === "undefined" ? 800 : window.innerHeight));
  useEffect(() => {
    const update = () => setHeight(window.innerHeight);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return height;
}

type BottomSheetProps = {
  isOpen: boolean;
  onClose: () => void;
  /** Accessible name for the sheet, rendered as its heading unless hidden. */
  title: string;
  /** Accessible name for the close control. */
  closeLabel: string;
  /** Accessible name for the back arrow shown when another sheet waits beneath. */
  backLabel?: string;
  dismissible?: boolean;
  snaps?: SheetSnaps;
  /** Where the sheet opens; the first allowed snap by default. */
  initialSnap?: SheetSnap;
  /** Use the whole viewport for a focused full-height task. Other snaps are unchanged. */
  fullScreen?: boolean;
  titleHidden?: boolean;
  /** A line under the title; it is what the peek snap shows. */
  description?: ReactNode;
  headerSize?: "default" | "large";
  /** Pinned below the scrolling body, for a sticky primary action. */
  footer?: ReactNode;
  initialFocusRef?: RefObject<HTMLElement | null>;
  children: ReactNode;
};

/** Bottom sheet primitive: snaps, flick or drag, scrim tap, or the close control. */
export function BottomSheetSurface({
  isOpen,
  onClose,
  title,
  closeLabel,
  backLabel,
  dismissible = true,
  snaps = ["half", "full"],
  initialSnap,
  fullScreen = false,
  titleHidden = false,
  description,
  headerSize = "default",
  footer,
  initialFocusRef,
  children,
}: BottomSheetProps) {
  const headingId = useId();
  const descriptionId = useId();
  const overlayId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dragOriginRef = useRef<{ y: number; at: number; height: number } | null>(null);
  const viewport = useViewportHeight();
  const fit = snaps === "fit";
  const allowed = fit ? [] : SNAP_ORDER.filter((snap) => snaps.includes(snap));
  const firstSnap: SheetSnap | "fit" = fit ? "fit" : initialSnap && allowed.includes(initialSnap) ? initialSnap : allowed[0] ?? "half";
  const [snap, setSnap] = useState<SheetSnap | "fit">(firstSnap);
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const { drawn, hasBelow } = useSheetStack(overlayId, isOpen);

  useModalSurface({
    isOpen,
    overlayId,
    containerRef: panelRef,
    onDismiss: onClose,
    canDismiss: () => dismissible,
    // Escape is routed by the registry, which only calls the topmost layer, so
    // the sheet no longer has to work out whether the press was meant for it.
    onEscape: dismissible ? onClose : () => {},
    initialFocusRef: initialFocusRef ?? closeButtonRef,
  });

  useEffect(() => {
    if (!isOpen) return;
    setSnap(firstSnap);
    setDragHeight(null);
    dragOriginRef.current = null;
    // Opening again starts at the declared snap, not where the last drag left it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const snapHeight = (target: SheetSnap) => Math.round(viewport * (fullScreen && target === "full" ? 1 : SHEET_SNAP_SHARE[target]));

  const handleDragStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dismissible && fit) return;
    // Controls in the header keep their own clicks; capturing here would eat them.
    if (event.target instanceof Element && event.target.closest(INTERACTIVE_SELECTOR)) return;
    dragOriginRef.current = { y: event.clientY, at: event.timeStamp, height: panelRef.current?.offsetHeight ?? 0 };
    // Grab the pointer at once: a fast first move would otherwise leave the grip before the drag is seen.
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleDragMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const origin = dragOriginRef.current;
    if (!origin) return;
    const deltaY = event.clientY - origin.y;
    // A tap stays a tap: the height only follows once the pointer has really moved.
    if (Math.abs(deltaY) <= DRAG_CAPTURE_THRESHOLD_PX) return;
    const tallest = fit ? origin.height : snapHeight("full");
    setDragHeight(Math.max(0, Math.min(tallest, origin.height - deltaY)));
  };

  const endGesture = (event: ReactPointerEvent<HTMLDivElement>, phase: SheetGesturePhase) => {
    const origin = dragOriginRef.current;
    dragOriginRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    setDragHeight(null);
    if (!origin) return;
    const deltaY = event.clientY - origin.y;
    const elapsed = Math.max(1, event.timeStamp - origin.at);
    const outcome = sheetRelease({
      heightPx: origin.height - deltaY,
      snapPx: fit ? [{ snap: "fit", px: origin.height }] : allowed.map((item) => ({ snap: item, px: snapHeight(item) })),
      from: snap,
      velocityY: deltaY / elapsed,
      phase,
    });
    if (outcome.kind === "dismiss") {
      if (dismissible) onClose();
      return;
    }
    setSnap(outcome.snap);
  };

  if (!isOpen) return null;

  const height = dragHeight ?? (snap === "fit" ? null : snapHeight(snap));
  const dragging = dragHeight !== null;

  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center" hidden={!drawn} data-sheet-stacked={hasBelow ? "true" : undefined}>
      <div
        aria-hidden="true"
        onClick={dismissible ? onClose : undefined}
        className="argus-sheet-scrim absolute inset-0 bg-black/20 dark:bg-black/50"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        aria-describedby={description ? descriptionId : undefined}
        data-snap={snap}
        data-full-screen={fullScreen && snap === "full" ? "true" : undefined}
        style={height === null ? { maxHeight: `${Math.round(viewport * FIT_MAX_SHARE)}px` } : { height: `${height}px`, ...(fullScreen && snap === "full" ? { borderRadius: 0, paddingTop: "env(safe-area-inset-top)" } : {}) }}
        className={`argus-sheet relative flex w-full max-w-[720px] flex-col overflow-hidden rounded-t-surface border-t border-black/[0.06] bg-white dark:border-white/10 dark:bg-[#1f2225] ${dragging ? "" : "transition-[height] duration-300 ease-[cubic-bezier(0.2,0.9,0.3,1.08)] motion-reduce:transition-none"} ${hasBelow ? "" : "argus-sheet-enter"}`}
      >
        <div
          onPointerDown={handleDragStart}
          onPointerMove={handleDragMove}
          onPointerUp={(event) => endGesture(event, "release")}
          onPointerCancel={(event) => endGesture(event, "cancel")}
          className="argus-sheet-grip shrink-0 cursor-grab touch-none px-4 pb-2 pt-2 active:cursor-grabbing"
        >
          <div className="mx-auto my-1 h-1.5 w-10 rounded-full bg-black/15 dark:bg-white/15" />
          <div className="mt-1 flex items-start gap-2">
            {hasBelow && dismissible ? (
              <button
                type="button"
                onClick={onClose}
                aria-label={backLabel ?? closeLabel}
                className="-ml-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/70 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/70 dark:hover:bg-white/5"
              >
                <ChevronLeft className="h-5 w-5" aria-hidden="true" />
              </button>
            ) : null}
            <div className="min-w-0 flex-1 pt-2">
              <h2 id={headingId} className={titleHidden ? "sr-only" : `font-display ${headerSize === "large" ? "text-[21px]" : "text-[17px]"} font-medium tracking-tight text-black dark:text-white`}>
                {title}
              </h2>
              {description ? (
                <p id={descriptionId} className={`mt-1 ${headerSize === "large" ? "text-[14px]" : "text-[13px]"} leading-relaxed text-[#56635e] dark:text-white/70`}>
                  {description}
                </p>
              ) : null}
            </div>
            {dismissible && !hasBelow ? (
              <button
                ref={closeButtonRef}
                type="button"
                onClick={onClose}
                aria-label={closeLabel}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/60 dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            ) : null}
          </div>
        </div>
        <div className={`argus-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 ${footer ? "pb-4" : "pb-[max(1rem,env(safe-area-inset-bottom))]"}`}>
          {children}
        </div>
        {footer ? (
          <div className="argus-sheet-footer shrink-0 border-t border-black/5 px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))] dark:border-white/5">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export const BottomSheet = withViewportPortal(BottomSheetSurface);
export default BottomSheet;
