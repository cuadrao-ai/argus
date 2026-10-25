"use client";

import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { profileSubmenuClass } from "@/components/sidebar/profileMenuPlacement";
import { Tooltip } from "@/components/ui/Tooltip";
import { createPortal } from "react-dom";
import { ArrowLeftRight, BriefcaseBusiness, Check, ChevronRight, Plus, Settings2, UserRoundPlus } from "lucide-react";
import { useEffect, useLayoutEffect, useId, useMemo, useRef, useState } from "react";
import { businessDeadlineParts } from "@/lib/business-lifecycle-api";
import { resolveLanguage } from "@/lib/language-features";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import type { ClosedGrantedSpace, GrantedSpace } from "@/lib/business-api";
import { formatBusinessName } from "./business-format";
const menuItemClass = "flex min-h-11 w-full items-center gap-2 rounded-item px-2 text-left text-[16px] text-[#172b26] hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-40 dark:text-white dark:hover:bg-white/5";

/** The shared Business identity icon in expanded and collapsed navigation. */
export function BusinessMark() {
  return <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-mark bg-black/[0.05] dark:bg-white/[0.08]"><BriefcaseBusiness className="h-5 w-5" strokeWidth={2} /></span>;
}

type MenuMode = "closed" | "menu" | "choose";

export default function BusinessSwitcher({ spaces, closedSpaces = [], chosen, collapsed, onChoose, onOpenSettings, onInvite, onAddBusiness, memberEmail }: {
  spaces: GrantedSpace[] | null;
  closedSpaces?: ClosedGrantedSpace[];
  chosen: GrantedSpace | null;
  collapsed: boolean;
  onChoose: (grantId: string | null) => void;
  /** Opens the Negocio page: name and RNC, team and access, receipt email. */
  onOpenSettings: () => void;
  onInvite?: () => void;
  onAddBusiness?: () => void;
  memberEmail?: string | null;
}) {
  const { t, i18n } = useTranslation();
  const held = closedSpaces.filter(space => space.role === "owner");
  const [mode, setMode] = useState<MenuMode>("closed");
  const [active, setActive] = useState(0);
  const { isBelowDesktop } = useResponsiveLayout();
  const switchRef = useRef<HTMLButtonElement>(null);
  const previousMode = useRef<MenuMode>("closed");
  const [submenuPosition, setSubmenuPosition] = useState({ left: 0, top: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const menuId = useId();
  const [position, setPosition] = useState({ left: 8, top: 80 });
  const options = useMemo(() => spaces ?? [], [spaces]);
  const current = chosen ?? options[0] ?? null;
  const canSwitch = options.length > 1;

  useOverlayLayer({
    isOpen: mode !== "closed" && !isBelowDesktop,
    overlayId: menuId,
    containerRef: menuRef,
    onOutsidePointerDown: event => {
      if (!buttonRef.current?.contains(event.target as Node)) setMode("closed");
    },
    onEscape: () => {
      if (mode === "choose") setMode("menu");
      else { setMode("closed"); buttonRef.current?.focus(); }
    },
  });

  useLayoutEffect(() => {
    if (mode === "closed" || isBelowDesktop) return;
    const place = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      const menu = menuRef.current?.getBoundingClientRect();
      if (!rect || !menu) return;
      const top = rect.bottom + 4 + menu.height <= window.innerHeight - 8 ? rect.bottom + 4 : Math.max(8, rect.top - menu.height - 8);
      const left = Math.max(8, Math.min(collapsed ? rect.right + 8 : rect.left, window.innerWidth - menu.width - 8));
      setPosition({ left, top });
      const trigger = switchRef.current?.getBoundingClientRect();
      if (mode === "choose" && trigger) {
        const width = 288;
        const childHeight = listRef.current?.getBoundingClientRect().height ?? 0;
        setSubmenuPosition({
          left: left + menu.width + 6 + width <= window.innerWidth - 8 ? left + menu.width + 6 : Math.max(8, left - width - 6),
          top: Math.max(8, Math.min(top + trigger.top - menu.top, window.innerHeight - childHeight - 8)),
        });
      }
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [mode, collapsed, isBelowDesktop]);

  useEffect(() => {
    if (mode === "menu") {
      if (previousMode.current === "choose") switchRef.current?.focus();
      else menuRef.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus();
    }
    if (mode === "choose") {
      setActive(Math.max(0, options.findIndex(space => space.grant_id === current?.grant_id)));
      listRef.current?.focus();
    }
    previousMode.current = mode;
  }, [mode, options, current?.grant_id]);

  if (!current) {
    // While the list loads, hold the mark's place so the menu below does not jump when it arrives.
    return spaces === null ? (
      <div data-testid="business-switcher-pending" aria-hidden="true" className={`flex min-h-11 items-center gap-2 px-1 ${collapsed ? "justify-center" : "w-full"}`}>
        <span className="h-8 w-8 shrink-0 rounded-mark bg-black/[0.06] dark:bg-white/10" />
        {collapsed ? null : <span className="h-4 w-24 rounded-mark bg-black/[0.06] dark:bg-white/10" />}
      </div>
    ) : null;
  }
  const fallback = t("business.overview.title", "Mi negocio");
  const name = formatBusinessName(current.name, fallback);

  const closeToButton = () => {
    setMode("closed");
    buttonRef.current?.focus();
  };

  const choose = (space: GrantedSpace) => {
    setMode("closed");
    onChoose(space.role === "owner" ? null : space.grant_id);
    buttonRef.current?.focus();
  };

  const onListKey = (event: React.KeyboardEvent<HTMLUListElement>) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((i) => Math.min(options.length - 1, i + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (event.key === "Home") { event.preventDefault(); setActive(0); }
    else if (event.key === "End") { event.preventDefault(); setActive(options.length - 1); }
    else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); if (options[active]) choose(options[active]); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); setMode("menu"); }
    else if (event.key === "Tab") closeToButton();
    else if (event.key.length === 1 && /\S/.test(event.key)) {
      const letter = event.key.toLocaleLowerCase();
      const index = options.findIndex((space, i) => i > active && formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      const wrapped = index >= 0 ? index : options.findIndex((space) => formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      if (wrapped >= 0) setActive(wrapped);
    }
  };

  const rootRows = (<>
    <div className="mb-2 border-b border-black/10 px-2 pb-3 dark:border-white/10">
      {memberEmail ? <p data-testid="business-member-email" className="break-words text-[16px] leading-6 text-[#172b26] dark:text-white">{memberEmail}</p> : <span aria-hidden="true" className="block h-5 w-40 rounded bg-black/[0.05] dark:bg-white/[0.08]" />}
      <p data-testid="business-member-access" className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.your_access")} · {t(current.role === "owner" ? "workspace_setup_preview.permission_owner" : current.capabilities.includes("prepare") ? "workspace_setup_preview.permission_editor" : "workspace_setup_preview.permission_viewer")}</p>
    </div>
    <div className="mb-2 border-b border-black/10 pb-2 dark:border-white/10">
      {current.role === "owner" && onInvite ? <button type="button" role="menuitem" className={menuItemClass} onClick={() => { closeToButton(); onInvite(); }}>
        <UserRoundPlus aria-hidden="true" className="h-5 w-5 shrink-0" />
        {t("business.switcher.invite")}
      </button> : null}
      <button type="button" role="menuitem" className={menuItemClass} onClick={() => { setMode("closed"); onOpenSettings(); }}>
        <Settings2 aria-hidden="true" className="h-5 w-5 shrink-0" />
        {t("business.switcher.configure")}
      </button>
    </div>
    <button type="button" role="menuitem" disabled={!onAddBusiness} onClick={() => { if (onAddBusiness) { setMode("closed"); onAddBusiness(); } }} className={menuItemClass}>
      <span aria-hidden="true" className="relative h-5 w-5 shrink-0"><BriefcaseBusiness className="h-5 w-5" /><Plus style={{ bottom: -2, right: -4 }} className="absolute h-3 w-3 bg-[#fffefa] dark:bg-[var(--cuadrao-menu-surface)]" strokeWidth={2.5} /></span>
      {t("business.switcher.add")}
    </button>
    {held.length ? <div className="mt-2 border-t border-black/10 pt-2 dark:border-white/10">
      <p className="px-2 py-1 text-[12px]">{t("business.lifecycle.closed_group")}</p>
      {held.map(space => <a key={space.grant_id} role="menuitem" href={`/biz?lifecycle=manage&business=${encodeURIComponent(space.space_id)}`} className="block min-h-11 rounded-item px-2 py-2 text-[14px] text-[#56635e] dark:text-white/70">{space.name}<span className="block text-[12px]">{t("business.lifecycle.deadline", businessDeadlineParts(space.reopen_until, i18n.resolvedLanguage ?? resolveLanguage({})))}</span></a>)}
    </div> : null}
    {canSwitch ? (
      <button
        ref={switchRef}
        type="button"
        role="menuitem"
        aria-haspopup="listbox"
        aria-expanded={mode === "choose"}
        aria-controls={`${menuId}-businesses`}
        onKeyDown={event => { if (event.key === "ArrowRight") { event.preventDefault(); setMode("choose"); } }}
        className={menuItemClass}
        onClick={() => setMode("choose")}
      >
        <ArrowLeftRight className="h-5 w-5 shrink-0" strokeWidth={2} aria-hidden="true" />
        {t("business.switcher.change", "Cambiar de negocio")}
        <ChevronRight aria-hidden="true" className="ml-auto h-4 w-4" />
      </button>
    ) : null}
  </>);
  const choices = (<ul
    ref={listRef}
    id={`${menuId}-businesses`}
    role="listbox"
    tabIndex={-1}
    aria-label={t("business.switcher.choose", "Elige un negocio")}
    aria-activedescendant={options[active] ? `${menuId}-${options[active].grant_id}` : undefined}
    onKeyDown={onListKey}
    style={isBelowDesktop ? undefined : { position: "fixed", left: submenuPosition.left, top: submenuPosition.top, bottom: "auto", margin: 0 }}
    className={`${isBelowDesktop ? "" : profileSubmenuClass("rail", "w-72")} z-[101] m-0 max-h-[calc(100dvh-1rem)] overflow-y-auto p-1 text-[#172b26] dark:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]`}
  >
    {options.map((space, index) => {
      const optionName = formatBusinessName(space.name, fallback);
      return (
        <li
          key={space.grant_id}
          id={`${menuId}-${space.grant_id}`}
          role="option"
          aria-selected={space.grant_id === current.grant_id}
          data-active={index === active ? "true" : undefined}
          onMouseEnter={() => setActive(index)}
          onClick={() => choose(space)}
          className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-item px-2 text-[16px] ${index === active ? "bg-black/5 dark:bg-white/10" : ""}`}
        >
          <span className="min-w-0 flex-1 break-words">{optionName}</span>
          {space.grant_id === current.grant_id ? <Check aria-hidden="true" className="h-4 w-4 shrink-0" /> : null}
        </li>
      );
    })}
  </ul>);
  const badge = <BusinessMark />;

  return (
    <div data-testid="business-switcher" data-switchable={canSwitch ? "true" : "false"}>
      {collapsed ? <Tooltip content={name} side="right"><button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={mode !== "closed"}
        aria-controls={menuId}
        aria-label={name}
        onClick={() => setMode((value) => value === "closed" ? "menu" : "closed")}
        className={`flex min-h-11 min-w-11 items-center gap-2 rounded-item px-1.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${collapsed ? "justify-center" : "w-full"}`}
      >
        {badge}
        {collapsed ? <span className="sr-only" data-testid="business-current-name">{name}</span> : (
          <span className="min-w-0 flex-1">
            <span data-testid="business-current-name" className="block truncate whitespace-nowrap text-[16px] font-medium leading-6 text-[#172b26] dark:text-white">{name}</span>
          </span>
        )}
      </button></Tooltip> : (
        <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={mode !== "closed"}
        aria-controls={menuId}
        aria-label={name}
        onClick={() => setMode((value) => value === "closed" ? "menu" : "closed")}
        className={`flex min-h-11 min-w-11 items-center gap-2 rounded-item px-1.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${collapsed ? "justify-center" : "w-full"}`}
      >
        {badge}
        {collapsed ? <span className="sr-only" data-testid="business-current-name">{name}</span> : (
          <span className="min-w-0 flex-1">
            <span data-testid="business-current-name" className="block truncate whitespace-nowrap text-[16px] font-medium leading-6 text-[#172b26] dark:text-white">{name}</span>
          </span>
        )}
      </button>
      )}
      {mode !== "closed" ? isBelowDesktop ? (
        <AdaptivePanel title={mode === "choose" ? t("business.switcher.choose") : name} summary={mode === "choose" ? name : undefined} closeLabel={t("common.close")} onClose={mode === "choose" ? () => setMode("menu") : closeToButton} onBack={mode === "choose" ? () => setMode("menu") : undefined} backLabel={t("common.back")} snaps={["half", "full"]} initialSnap="half" returnFocusRef={buttonRef}>
          <div ref={menuRef} className="px-3 pb-3">{mode === "choose" ? choices : rootRows}</div>
        </AdaptivePanel>
      ) : createPortal(
        <div ref={menuRef} id={menuId} role="menu" aria-label={name} style={{ left: position.left, top: position.top }} className="fixed z-[100] w-80 max-w-[calc(100vw-1rem)] rounded-surface border border-[#dce0da] bg-[#fffefa] p-2 dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)]">
          <div className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
            <div className="flex items-center gap-3 px-2 py-3 text-[#172b26] dark:text-white"><BusinessMark /><p className="min-w-0 break-words text-[16px] font-medium">{name}</p></div>
            {rootRows}
          </div>
          {mode === "choose" ? choices : null}
        </div>, document.body,
      ) : null}
    </div>
  );
}
