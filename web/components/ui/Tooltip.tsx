"use client";

import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type TooltipSide = "top" | "bottom" | "left" | "right";

type TooltipProps = {
  /** One short sentence: a hint, not documentation. */
  content: string;
  children: React.ReactElement<
    React.HTMLAttributes<HTMLElement> & React.RefAttributes<HTMLElement>
  >;
  side?: TooltipSide;
};

/** A passing cursor shows nothing; a hover that stays this long does. */
export const TOOLTIP_DELAY_MS = 300;
export const TOOLTIP_MAX_WIDTH_PX = 300;
const GAP_PX = 8;
const EDGE_PX = 8;
const ARROW_INSET_PX = 12;

type Box = { left: number; top: number; width: number; height: number };
export type TooltipPlacement = { side: TooltipSide; left: number; top: number; arrow: number };

const OPPOSITE: Record<TooltipSide, TooltipSide> = { top: "bottom", bottom: "top", left: "right", right: "left" };

/**
 * Where a tooltip of this size goes: on its side when it fits, flipped to the
 * opposite side when it does not, then shifted along the edge so it stays on
 * screen. `arrow` is the tail's offset along that edge, so it still points at
 * the trigger's centre after the shift.
 */
export function placeTooltip(trigger: Box, tip: { width: number; height: number }, viewport: { width: number; height: number }, preferred: TooltipSide): TooltipPlacement {
  const fits = (side: TooltipSide) =>
    side === "top" ? trigger.top - GAP_PX - tip.height >= EDGE_PX
      : side === "bottom" ? trigger.top + trigger.height + GAP_PX + tip.height <= viewport.height - EDGE_PX
        : side === "left" ? trigger.left - GAP_PX - tip.width >= EDGE_PX
          : trigger.left + trigger.width + GAP_PX + tip.width <= viewport.width - EDGE_PX;
  const side = fits(preferred) || !fits(OPPOSITE[preferred]) ? preferred : OPPOSITE[preferred];
  const clamp = (value: number, size: number, room: number) => Math.min(Math.max(value, EDGE_PX), Math.max(EDGE_PX, room - size - EDGE_PX));
  if (side === "top" || side === "bottom") {
    const centre = trigger.left + trigger.width / 2;
    const left = clamp(centre - tip.width / 2, tip.width, viewport.width);
    const top = side === "top" ? trigger.top - GAP_PX - tip.height : trigger.top + trigger.height + GAP_PX;
    return { side, left, top, arrow: Math.min(Math.max(centre - left, ARROW_INSET_PX), tip.width - ARROW_INSET_PX) };
  }
  const centre = trigger.top + trigger.height / 2;
  const top = clamp(centre - tip.height / 2, tip.height, viewport.height);
  const left = side === "left" ? trigger.left - GAP_PX - tip.width : trigger.left + trigger.width + GAP_PX;
  return { side, left, top, arrow: Math.min(Math.max(centre - top, ARROW_INSET_PX), tip.height - ARROW_INSET_PX) };
}

/** The trigger keeps its own ref: the tooltip hands every node on to it. */
function passRef(ref: React.Ref<HTMLElement> | undefined, node: HTMLElement | null) {
  if (typeof ref === "function") ref(node);
  else if (ref && typeof ref === "object") (ref as React.MutableRefObject<HTMLElement | null>).current = node;
}

/**
 * The one tooltip. It waits 300ms, points at its trigger with a tail, flips
 * and shifts to stay on screen, and leaves on mouse leave, focus out, Escape,
 * a tap outside or a scroll. Keyboard focus shows it; a mouse click does not.
 */
export function Tooltip({ content, children, side = "right" }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<TooltipPlacement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const tooltipId = useId();

  const hide = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setOpen(false);
    setPlacement(null);
  }, []);
  const show = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(true), TOOLTIP_DELAY_MS);
  };

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  // Measure the real bubble, then place it; it renders hidden for that one frame.
  useLayoutEffect(() => {
    if (!open || !triggerRef.current || !tipRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const tip = tipRef.current.getBoundingClientRect();
    setPlacement(placeTooltip(rect, { width: tip.width, height: tip.height }, { width: window.innerWidth, height: window.innerHeight }, side));
  }, [open, side, content]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") hide(); };
    const onPointer = (event: PointerEvent) => { if (!triggerRef.current?.contains(event.target as Node)) hide(); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer, true);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer, true);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [open, hide]);

  const child = children;
  const childProps = child.props;
  const childRef = (childProps as { ref?: React.Ref<HTMLElement> }).ref;
  const setTriggerRef = (node: HTMLElement | null) => {
    triggerRef.current = node;
    passRef(childRef, node);
  };
  const describedBy = [childProps["aria-describedby"], open ? tooltipId : null].filter(Boolean).join(" ") || undefined;

  const trigger = React.cloneElement(child, {
    ref: setTriggerRef,
    "aria-describedby": describedBy,
    onMouseEnter: (event: React.MouseEvent<HTMLElement>) => {
      childProps.onMouseEnter?.(event);
      show();
    },
    onMouseLeave: (event: React.MouseEvent<HTMLElement>) => {
      childProps.onMouseLeave?.(event);
      hide();
    },
    onFocus: (event: React.FocusEvent<HTMLElement>) => {
      childProps.onFocus?.(event);
      if (event.currentTarget.matches(":focus-visible")) show();
    },
    onBlur: (event: React.FocusEvent<HTMLElement>) => {
      childProps.onBlur?.(event);
      hide();
    },
  });

  const arrowSide = placement ? OPPOSITE[placement.side] : "bottom";
  const arrowStyle: React.CSSProperties = !placement ? {} : placement.side === "top" || placement.side === "bottom"
    ? { left: placement.arrow - 4, [arrowSide]: -5 }
    : { top: placement.arrow - 4, [arrowSide]: -5 };

  return (
    <>
      {trigger}
      {open && typeof document !== "undefined" ? createPortal(
        <div
          id={tooltipId}
          role="tooltip"
          ref={tipRef}
          data-side={placement?.side ?? side}
          style={{
            position: "fixed",
            top: placement?.top ?? 0,
            left: placement?.left ?? 0,
            maxWidth: TOOLTIP_MAX_WIDTH_PX,
            visibility: placement ? "visible" : "hidden",
            zIndex: 9999,
          }}
          className="pointer-events-none w-max rounded-item border border-[#DCE0DA] bg-white px-2.5 py-1.5 text-[13px] font-medium leading-[18px] text-[#172b26] dark:border-white/10 dark:bg-[#1f2225] dark:text-white"
        >
          {content}
          <span
            aria-hidden="true"
            data-tooltip-arrow={arrowSide}
            style={arrowStyle}
            className={`absolute h-2 w-2 rotate-45 bg-white dark:bg-[#1f2225] ${
              arrowSide === "bottom" ? "border-b border-r" : arrowSide === "top" ? "border-l border-t" : arrowSide === "left" ? "border-b border-l" : "border-r border-t"
            } border-[#DCE0DA] dark:border-white/10`}
          />
        </div>,
        document.body,
      ) : null}
    </>
  );
}
