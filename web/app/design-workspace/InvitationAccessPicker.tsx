"use client";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useOverlayLayer } from "@/components/layout/overlayStack";

export default function InvitationAccessPicker({ slot }: { slot: HTMLElement }) {
  const { isBelowDesktop } = useResponsiveLayout();
  const { t } = useTranslation();
  const select = slot.parentElement?.querySelector<HTMLSelectElement>("select");
  const options = useMemo(() => Array.from(select?.options ?? []), [select]);
  const [value, setValue] = useState(select?.value ?? "editor");
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 0, maxHeight: 320 });
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();
  const selected = options.find(option => option.value === value);
  const label = slot.dataset.label ?? "";
  const compact = slot.dataset.compact === "true";
  const close = () => { setOpen(false); requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true })); };
  useOverlayLayer({ isOpen: open && !isBelowDesktop, overlayId: id, containerRef: list, onEscape: close,
    onKeyDown: event => {
      const index = items.current.indexOf(document.activeElement as HTMLButtonElement);
      if (event.key === "Escape") { event.preventDefault(); close(); }
      else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
        items.current[next]?.focus({ preventScroll: true });
      } else if (event.key === "Tab") {
        event.preventDefault(); setOpen(false);
        const controls = Array.from(slot.ownerDocument.querySelectorAll<HTMLElement>('input:not([disabled]), button:not([disabled])')).filter(node => node.offsetParent !== null);
        const current = controls.indexOf(trigger.current!);
        controls[current + (event.shiftKey ? -1 : 1)]?.focus();
      }
    },
  });
  useLayoutEffect(() => {
    if (!open || isBelowDesktop) return;
    const place = () => {
      const rect = trigger.current?.getBoundingClientRect();
      const frame = slot.ownerDocument.defaultView?.frameElement?.getBoundingClientRect();
      if (!rect || !frame) return;
      const bottom = frame.top + rect.bottom;
      const top = frame.top + rect.top;
      const height = list.current?.offsetHeight ?? 280;
      const below = window.innerHeight - bottom - 16;
      const above = top - 16;
      const upwards = below < height && above > below;
      setPosition({ left: Math.max(8, Math.min(frame.left + rect.left, window.innerWidth - Math.min(420, Math.max(rect.width, 300)) - 8)),
        top: upwards ? Math.max(8, top - height - 8) : bottom + 8, width: Math.min(420, Math.max(rect.width, 300)),
        maxHeight: Math.max(120, upwards ? above : below) });
    };
    place();
    const observer = new ResizeObserver(place);
    if (list.current) observer.observe(list.current);
    window.addEventListener("resize", place);
    document.addEventListener("scroll", place, true);
    items.current[options.findIndex(option => option.value === value)]?.focus({ preventScroll: true });
    return () => { observer.disconnect(); window.removeEventListener("resize", place); document.removeEventListener("scroll", place, true); };
  }, [open, slot, value, options, isBelowDesktop]);
  useEffect(() => {
    if (!open || isBelowDesktop) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!list.current?.contains(target) && !trigger.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    slot.ownerDocument.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("pointerdown", outside); slot.ownerDocument.removeEventListener("pointerdown", outside); };
  }, [open, slot, isBelowDesktop]);
  const modal = document.querySelector("[data-invitation-modal]");
  const choices = <>
      {options.map((option, index) => <button key={option.value} ref={node => { items.current[index] = node; }} type="button" role="option" tabIndex={-1} aria-selected={option.value === value}
        onClick={() => {
          setValue(option.value);
          if (select) { select.value = option.value; const ChangeEvent = slot.ownerDocument.defaultView?.Event ?? Event; select.dispatchEvent(new ChangeEvent("change", { bubbles: true })); }
          close();
        }}
        className="flex min-h-11 w-full items-center gap-3 rounded-item px-3 py-2.5 text-left text-[#172b26] hover:bg-black/5 focus:bg-black/5 focus:outline-none dark:text-white dark:hover:bg-white/5 dark:focus:bg-white/5">
        <span className="min-w-0 flex-1"><span className="block text-[16px] font-medium">{option.textContent}</span><span className="mt-1 block text-[14px] leading-snug text-[#56635e] dark:text-white/70">{option.dataset.description}</span></span>
        <Check aria-hidden="true" className={`h-4 w-4 shrink-0 ${option.value === value ? "" : "invisible"}`} />
      </button>)}
  </>;
  return <>
    <label id={`${id}-label`} className={compact ? isBelowDesktop ? "mb-1 block text-[14px] font-medium" : "sr-only" : "mb-2 block text-[16px] font-medium"}>{compact && isBelowDesktop ? t("workspace_setup_preview.permission_label") : label}</label>
    <button ref={trigger} type="button" role="combobox" aria-haspopup="listbox" aria-expanded={open}
      aria-labelledby={compact ? undefined : `${id}-label ${id}-value`} aria-label={compact ? `${label} ${selected?.textContent ?? ""}` : undefined} aria-describedby={compact ? undefined : `${id}-detail`} aria-controls={open ? id : undefined}
      disabled={select?.disabled} onClick={() => setOpen(!open)}
      onKeyDown={event => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); setOpen(true); } }}
      className="flex min-h-12 w-full items-center justify-between gap-3 rounded-lg border border-[#7d8a84] bg-transparent px-3 text-left text-[16px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:focus-visible:outline-[#8fcbb0]">
      <span id={`${id}-value`}>{selected?.textContent}</span><ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
    </button>
    {!compact ? <p id={`${id}-detail`} className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{selected?.dataset.description}</p> : null}
    {open && isBelowDesktop ? <BottomSheet isOpen onClose={close} title={label} closeLabel={t("common.close")} backLabel={t("common.back")} snaps="fit">
      <div ref={list} role="listbox" aria-label={label} className="p-2">{choices}</div>
    </BottomSheet> : open && modal ? createPortal(<div ref={list} id={id} role="listbox" aria-label={label}
      style={{ position: "fixed", ...position }}
      className="z-[150] overflow-y-auto rounded-surface border border-black/10 bg-white p-1.5 shadow-lg dark:border-white/10 dark:bg-[#1f2225]">
      {choices}
    </div>, modal) : null}
  </>;
}
