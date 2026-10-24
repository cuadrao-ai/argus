"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useOverlayLayer } from "@/components/layout/overlayStack";

export type AccessRoleOption = {value:string;label:string;description:string};
export default function AccessRolePicker({options,value,onChange,label,disabled=false,compact=false,variant="field",ownerDocument,portalRoot}: {
  options:AccessRoleOption[];value:string;onChange:(value:string)=>void;label:string;disabled?:boolean;compact?:boolean;variant?:"field"|"quiet";ownerDocument?:Document;portalRoot?:Element|null;
}) {
  const { isBelowDesktop } = useResponsiveLayout();
  const { t } = useTranslation();
  const sourceDocument = ownerDocument ?? (typeof document === "undefined" ? null : document);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 0, maxHeight: 320 });
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();
  const selected = options.find(option => option.value === value);
  const close = () => { setOpen(false); requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true })); };
  const moveOptionFocus = (event: {key:string;preventDefault:()=>void}) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return false;
    event.preventDefault();
    const index = items.current.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    items.current[next]?.focus({preventScroll:true});
    return true;
  };
  useOverlayLayer({ isOpen: open && !isBelowDesktop, overlayId: id, containerRef: list, onEscape: close,
    onKeyDown: event => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      else if (moveOptionFocus(event)) return;
      else if (event.key === "Tab") {
        event.preventDefault(); setOpen(false);
        const controls = Array.from(sourceDocument?.querySelectorAll<HTMLElement>('input:not([disabled]), button:not([disabled]), select:not([disabled]), a[href], [tabindex="0"]') ?? []).filter(node => node.tabIndex >= 0 && node.getClientRects().length > 0 && !list.current?.contains(node));
        const current = controls.indexOf(trigger.current!);
        controls[current + (event.shiftKey ? -1 : 1)]?.focus();
      }
    },
  });
  useLayoutEffect(() => {
    if (!open || isBelowDesktop || !sourceDocument) return;
    const place = () => {
      const rect = trigger.current?.getBoundingClientRect();
      const frame = sourceDocument.defaultView?.frameElement?.getBoundingClientRect();
      if (!rect) return;
      const bottom = (frame?.top ?? 0) + rect.bottom;
      const top = (frame?.top ?? 0) + rect.top;
      const height = list.current?.offsetHeight ?? 280;
      const below = window.innerHeight - bottom - 16;
      const above = top - 16;
      const upwards = below < height && above > below;
      setPosition({ left: Math.max(8, Math.min((frame?.left ?? 0) + rect.left, window.innerWidth - Math.min(420, Math.max(rect.width, 300)) - 8)),
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
  }, [open, sourceDocument, value, options, isBelowDesktop]);
  useEffect(() => {
    if (!open || isBelowDesktop || !sourceDocument) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!list.current?.contains(target) && !trigger.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    sourceDocument.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("pointerdown", outside); sourceDocument.removeEventListener("pointerdown", outside); };
  }, [open, sourceDocument, isBelowDesktop]);
  const destination = portalRoot ?? (typeof document === "undefined" ? null : document.body);
  const choices = <>
      {options.map((option, index) => <button key={option.value} ref={node => { items.current[index] = node; }} type="button" role="option" tabIndex={isBelowDesktop && option.value === value ? 0 : -1} aria-selected={option.value === value}
        onClick={() => {
          onChange(option.value);
          close();
        }}
        className="flex min-h-11 w-full items-center gap-3 rounded-item px-3 py-2.5 text-left text-[#172b26] hover:bg-black/5 focus:bg-black/5 focus:outline-none dark:text-white dark:hover:bg-white/5 dark:focus:bg-white/5">
        <span className="min-w-0 flex-1"><span className="block text-[16px] font-medium">{option.label}</span><span className="mt-1 block text-[14px] leading-snug text-[#56635e] dark:text-white/70">{option.description}</span></span>
        <Check aria-hidden="true" className={`h-4 w-4 shrink-0 ${option.value === value ? "" : "invisible"}`} />
      </button>)}
  </>;
  return <>
    {variant === "field" ? <label id={`${id}-label`} className={compact ? isBelowDesktop ? "mb-1 block text-[14px] font-medium" : "sr-only" : "mb-2 block text-[16px] font-medium"}>{compact && isBelowDesktop ? t("workspace_setup_preview.permission_label") : label}</label> : null}
    <button ref={trigger} type="button" role="combobox" aria-haspopup="listbox" aria-expanded={open}
      aria-labelledby={compact || variant === "quiet" ? undefined : `${id}-label ${id}-value`} aria-label={compact || variant === "quiet" ? `${label} ${selected?.label ?? ""}` : undefined} aria-describedby={compact || variant === "quiet" ? undefined : `${id}-detail`} aria-controls={open ? id : undefined}
      disabled={disabled} onClick={() => setOpen(!open)}
      onKeyDown={event => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); setOpen(true); } }}
      className={variant === "quiet" ? "flex min-h-11 items-center gap-2 rounded-md bg-transparent text-left text-[16px] text-[#56635e] focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed dark:text-white/70" : "flex min-h-12 w-full items-center justify-between gap-3 rounded-lg border border-[#7d8a84] bg-transparent px-3 text-left text-[16px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:focus-visible:outline-[#8fcbb0]"}>
      <span id={`${id}-value`}>{selected?.label}</span><ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
    </button>
    {!compact && variant === "field" ? <p id={`${id}-detail`} className="mt-2 text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{selected?.description}</p> : null}
    {open && isBelowDesktop ? <BottomSheet isOpen onClose={close} title={label} closeLabel={t("common.close")} backLabel={t("common.back")} snaps="fit">
      <div ref={list} id={id} role="listbox" aria-label={label} onKeyDown={moveOptionFocus} className="p-2">{choices}</div>
    </BottomSheet> : open && destination ? createPortal(<div ref={list} id={id} role="listbox" aria-label={label}
      style={{ position: "fixed", zIndex:150, ...position }}
      className="z-[150] overflow-y-auto rounded-surface border border-black/10 bg-white p-1.5 shadow-lg dark:border-white/10 dark:bg-[#1f2225]">
      {choices}
    </div>, destination) : null}
  </>;
}
