"use client";

import { createPortal } from "react-dom";
import { Tooltip } from "@/components/ui/Tooltip";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { ArrowLeftRight, Check, UsersRound } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { GrantedSpace } from "@/lib/business-api";
import { identityInitials } from "@/lib/sidebar-identity";
import { formatBusinessName } from "./business-format";

type OpenPanel = "menu" | "switcher" | null;
const rowClass = "flex min-h-11 w-full items-center gap-2.5 rounded-[12px] px-2 text-left text-[14px] transition-colors duration-150 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)] dark:hover:bg-white/5 motion-reduce:transition-none motion-reduce:duration-0";

export default function BusinessSwitcher({ spaces, chosen, collapsed, onChoose, onAccess }: {
  spaces: GrantedSpace[] | null;
  chosen: GrantedSpace | null;
  collapsed: boolean;
  onChoose: (grantId: string | null) => void;
  onAccess: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<OpenPanel>(null);
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const [position, setPosition] = useState({ left: 8, bottom: 64 });
  const close = () => { setOpen(null); buttonRef.current?.focus(); };
  useOverlayLayer({ isOpen: open !== null, overlayId: panelId, containerRef: panelRef, onEscape: close });
  const options = useMemo(() => spaces ?? [], [spaces]);
  const current = chosen ?? options[0] ?? null;
  const fallback = t("business.overview.title", "My business");
  const name = formatBusinessName(current?.name, fallback);

  useEffect(() => {
    if (!open) return;
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) setPosition({ left: Math.min(Math.max(8, rect.left), window.innerWidth - 304), bottom: window.innerHeight - rect.top + 8 });
    setActive(Math.max(0, options.findIndex((space) => space.grant_id === current?.grant_id)));
    if (open === "menu") panelRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    else panelRef.current?.focus();
    const outside = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node) && !buttonRef.current?.contains(event.target as Node)) setOpen(null);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open, options, current?.grant_id]);

  if (!current) return null;
  const choose = (space: GrantedSpace) => {
    close();
    onChoose(space.role === "owner" ? null : space.grant_id);
  };
  const badge = (value: string) => <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-[var(--cuadrao-green)] text-[12px] font-semibold text-[var(--cuadrao-cream)]">{identityInitials(value)}</span>;
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Tab") { setOpen(null); return; }
    if (open === "menu") {
      const buttons = Array.from(panelRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === "ArrowDown" ? (index + 1) % buttons.length : event.key === "ArrowUp" ? (index - 1 + buttons.length) % buttons.length : event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : null;
      if (next !== null) { event.preventDefault(); buttons[next]?.focus(); }
      return;
    }
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((i) => Math.min(options.length - 1, i + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (event.key === "Home") { event.preventDefault(); setActive(0); }
    else if (event.key === "End") { event.preventDefault(); setActive(options.length - 1); }
    else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); if (options[active]) choose(options[active]); }
    else if (event.key.length === 1 && /\S/.test(event.key)) {
      const letter = event.key.toLocaleLowerCase();
      const index = options.findIndex((space, i) => i > active && formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      const wrapped = index >= 0 ? index : options.findIndex((space) => formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      if (wrapped >= 0) setActive(wrapped);
    }
  };

  return <div data-testid="business-switcher" data-switchable={options.length > 1}>
    <Tooltip content={name} side={collapsed ? "right" : "top"} delay={150}>
      <span className="block"><button ref={buttonRef} type="button" data-testid="business-mark-trigger" aria-label={`${t("business.switcher.label", "Business")}: ${name}`} aria-haspopup="menu" aria-expanded={open !== null} aria-controls={panelId} onClick={() => setOpen((value) => value ? null : "menu")} onKeyDown={(event) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen("menu"); } }} className="flex h-11 w-11 items-center justify-center rounded-[14px] transition-colors duration-150 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)] dark:hover:bg-white/5 motion-reduce:transition-none motion-reduce:duration-0">{badge(name)}</button></span>
    </Tooltip>
    {open ? createPortal(<div ref={panelRef} id={panelId} role={open === "menu" ? "menu" : "listbox"} tabIndex={-1} aria-label={open === "menu" ? name : t("business.switcher.choose", "Choose a Business")} aria-activedescendant={open === "switcher" && options[active] ? `${panelId}-${options[active].grant_id}` : undefined} onKeyDown={onKeyDown} style={position} className="fixed z-[100] w-72 max-w-[calc(100vw-1rem)] max-h-[70dvh] overflow-y-auto rounded-[16px] border border-black/10 bg-white p-1.5 text-black shadow-lg focus-visible:outline-none dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)] dark:text-white">
      {open === "menu" ? <>
        <div className="mb-1 flex items-center gap-2.5 border-b border-black/5 px-2 py-3 dark:border-white/5">{badge(name)}<span data-testid="business-current-name" className="min-w-0 truncate text-[14px] font-medium">{name}</span></div>
        <button type="button" role="menuitem" className={rowClass} onClick={() => { close(); onAccess(); }}><UsersRound size={20} aria-hidden="true" />{t("business_access.nav", "Access")}</button>
        {options.length > 1 ? <button type="button" role="menuitem" className={rowClass} onClick={() => setOpen("switcher")}><ArrowLeftRight size={20} aria-hidden="true" />{t("business.switcher.change", "Switch Business")}</button> : null}
      </> : options.map((space, index) => {
        const optionName = formatBusinessName(space.name, fallback);
        return <div key={space.grant_id} id={`${panelId}-${space.grant_id}`} role="option" aria-selected={space.grant_id === current.grant_id} data-active={index === active || undefined} onMouseEnter={() => setActive(index)} onClick={() => choose(space)} className={`${rowClass} cursor-pointer ${index === active ? "bg-black/5 dark:bg-white/5" : ""}`}>
          {badge(optionName)}<span className="min-w-0 flex-1"><span className="block truncate font-medium">{optionName}</span><span className="block text-[12px] text-black/60 dark:text-white/60">{space.role === "owner" ? t("business.switcher.own", "Your Business") : t("business.switcher.role_accountant", "View and prepare")}</span></span>
          {space.grant_id === current.grant_id ? <Check size={20} className="shrink-0" aria-hidden="true" /> : null}
        </div>;
      })}
    </div>, document.body) : null}
  </div>;
}
