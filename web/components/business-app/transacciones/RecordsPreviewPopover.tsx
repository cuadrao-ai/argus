"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import styles from "./records-filter-preview.module.css";

export default function RecordsPreviewPopover({ label, icon, count, width = 660, preferredHeight = 320, children }: { label: string; icon: ReactNode; count?: number; width?: number; preferredHeight?: number; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 16, top: 100, width, maxHeight: 500 });
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = () => setOpen(false);
  const place = useCallback(() => {
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const measuredWidth = Math.min(width, window.innerWidth - 32);
    const top = Math.min(rect.bottom + 8, Math.max(16, window.innerHeight - preferredHeight - 16));
    setPosition({ left: Math.max(16, Math.min(rect.left, window.innerWidth - measuredWidth - 16)), top, width: measuredWidth, maxHeight: window.innerHeight - top - 16 });
  }, [width, preferredHeight]);
  useOverlayLayer({ isOpen: open, overlayId: id, containerRef: panel, onEscape: close, onOutsidePointerDown: (event) => { if (!trigger.current?.contains(event.target as Node)) close(); } });
  useEffect(() => {
    if (!open) return;
    const opener = trigger.current;
    panel.current?.querySelector<HTMLElement>("button, input")?.focus();
    const reposition = () => place();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      opener?.focus();
    };
  }, [open, place]);
  return <>
    <button ref={trigger} type="button" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => { place(); setOpen((value) => !value); }} className={styles.trigger}>
      {icon}<span>{label}</span>{count ? <span className={styles.count}>{count}</span> : null}<ChevronDown size={16} aria-hidden="true" className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} />
    </button>
    {open ? createPortal(<div ref={panel} id={id} role="dialog" aria-label={label} className={styles.popover} style={position}>{children(close)}</div>, document.body) : null}
  </>;
}
