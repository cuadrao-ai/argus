"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { BusinessAction } from "./business-actions";

type ActionMenuProps = {
  actions: readonly (Omit<BusinessAction, "id"> & { id: BusinessAction["id"] | "mark_personal" })[];
  label: string;
  /** Where the menu opens relative to its trigger. */
  placement: "above-start" | "below-end" | "above-start-compact";
  /**
   * Render in the body at the trigger's position. Needed inside the desktop
   * rail, which clips its overflow while it animates its width.
   */
  portal?: boolean;
  renderTrigger: (props: {
    ref: React.RefObject<HTMLButtonElement | null>;
    open: boolean;
    toggle: () => void;
    menuId: string;
  }) => ReactNode;
};

const PLACEMENT: Record<ActionMenuProps["placement"], string> = {
  "above-start": "bottom-full left-0 mb-2",
  "above-start-compact": "bottom-full left-0 mb-3",
  "below-end": "right-0 top-full mt-2",
};

/** A short menu of working actions. Opening it does nothing else. */
export default function ActionMenu({ actions, label, placement, portal = false, renderTrigger }: ActionMenuProps) {
  const [open, setOpen] = useState(false);
  const [fixedStyle, setFixedStyle] = useState<CSSProperties | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  // A portaled menu mounts once it has a position; focus lands then, and a
  // later reposition never moves it.
  const menuVisible = open && (!portal || fixedStyle !== null);
  useEffect(() => {
    if (menuVisible) itemRefs.current[0]?.focus();
  }, [menuVisible]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !portal) return;
    const place = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setFixedStyle({
        position: "fixed",
        left: Math.max(8, rect.left),
        bottom: window.innerHeight - rect.top + 8,
      });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open, portal]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const items = itemRefs.current.filter(Boolean) as HTMLButtonElement[];
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(index + 1) % items.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length]?.focus();
    } else if (event.key === "Home") {
      event.preventDefault();
      items[0]?.focus();
    } else if (event.key === "End") {
      event.preventDefault();
      items[items.length - 1]?.focus();
    } else if (event.key === "Tab") {
      event.preventDefault();
      close();
    }
  };

  const menu =
    menuVisible ? (
    <div
      ref={menuRef}
      id={menuId}
      role="menu"
      aria-label={label}
      onKeyDown={onKeyDown}
      style={portal ? (fixedStyle ?? undefined) : undefined}
      className={`z-[70] min-w-[220px] rounded-[14px] border border-black/10 bg-white py-1.5 dark:border-white/10 dark:bg-[#1f2225] ${portal ? "" : `absolute ${PLACEMENT[placement]}`}`}
    >
      {actions.map((action, index) => {
        const Icon = action.icon;
        return (
          <button
            key={`${action.id}-${index}`}
            ref={(element) => {
              itemRefs.current[index] = element;
            }}
            type="button"
            role="menuitem"
            onClick={() => {
              close();
              action.run();
            }}
            className="mx-1 my-0.5 flex min-h-11 w-[calc(100%-0.5rem)] items-center gap-3 rounded-[10px] px-3 text-left text-[14px] font-medium text-black transition-colors hover:bg-black/5 focus-visible:bg-black/5 focus-visible:outline-none dark:text-white dark:hover:bg-white/5 dark:focus-visible:bg-white/5"
          >
            <Icon className="h-[18px] w-[18px] shrink-0 text-black/60 dark:text-white/60" />
            {action.label}
          </button>
        );
      })}
    </div>
    ) : null;

  return (
    <div className="relative">
      {renderTrigger({ ref: triggerRef, open, toggle: () => setOpen((value) => !value), menuId })}
      {menu && portal ? createPortal(menu, document.body) : menu}
    </div>
  );
}
