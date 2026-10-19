"use client";

import { createPortal } from "react-dom";
import { ArrowLeftRight, UsersRound } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import type { GrantedSpace } from "@/lib/business-api";
import { formatBusinessName } from "./business-format";

function initial(name: string): string {
  const letter = name.trim().charAt(0);
  return letter ? letter.toLocaleUpperCase() : "·";
}

type MenuMode = "closed" | "menu" | "choose";

export default function BusinessSwitcher({ spaces, chosen, collapsed, onChoose, onOpenAccess }: {
  spaces: GrantedSpace[] | null;
  chosen: GrantedSpace | null;
  collapsed: boolean;
  onChoose: (grantId: string | null) => void;
  onOpenAccess: () => void;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<MenuMode>("closed");
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const menuId = useId();
  const [position, setPosition] = useState({ left: 8, top: 80, above: false });
  const options = useMemo(() => spaces ?? [], [spaces]);
  const current = chosen ?? options[0] ?? null;
  const canSwitch = options.length > 1;

  useOverlayLayer({
    isOpen: mode !== "closed",
    overlayId: menuId,
    containerRef: menuRef,
    onEscape: () => {
      setMode("closed");
      buttonRef.current?.focus();
    },
  });

  useEffect(() => {
    if (mode === "closed") return;
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) {
      const above = rect.bottom > window.innerHeight - 220;
      setPosition({
        left: Math.min(Math.max(8, collapsed ? rect.right + 8 : rect.left), window.innerWidth - 304),
        top: above ? rect.top - 8 : rect.bottom + 4,
        above,
      });
    }
    const index = Math.max(0, options.findIndex((space) => space.grant_id === current?.grant_id));
    setActive(index);
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !buttonRef.current?.contains(target)) setMode("closed");
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [mode, options, current?.grant_id, collapsed]);

  useEffect(() => {
    if (mode === "menu") menuRef.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus();
    if (mode === "choose") listRef.current?.focus();
  }, [mode]);

  if (!current) return null;
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
    else if (event.key === "Escape" || event.key === "Tab") { closeToButton(); if (event.key === "Escape") event.preventDefault(); }
    else if (event.key.length === 1 && /\S/.test(event.key)) {
      const letter = event.key.toLocaleLowerCase();
      const index = options.findIndex((space, i) => i > active && formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      const wrapped = index >= 0 ? index : options.findIndex((space) => formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      if (wrapped >= 0) setActive(wrapped);
    }
  };

  const badge = (
    <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[#2f5a49] text-[13px] font-medium text-[#fffefa]">
      {initial(name)}
    </span>
  );

  return (
    <div className={collapsed ? "" : "mx-1 mb-1"} data-testid="business-switcher" data-switchable={canSwitch ? "true" : "false"}>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={mode !== "closed"}
        aria-controls={menuId}
        aria-label={name}
        onClick={() => setMode((value) => value === "closed" ? "menu" : "closed")}
        className={`flex min-h-11 min-w-11 items-center gap-2 rounded-[12px] px-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${collapsed ? "justify-center" : "w-full"}`}
      >
        {badge}
        {collapsed ? <span className="sr-only" data-testid="business-current-name">{name}</span> : (
          <span data-testid="business-current-name" className="min-w-0 flex-1 break-words text-[15px] font-medium leading-5 text-[#172b26] dark:text-white">{name}</span>
        )}
      </button>
      {mode !== "closed" ? createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={name}
          style={{ left: Math.max(8, position.left), top: position.top, transform: position.above ? "translateY(-100%)" : undefined }}
          className="fixed z-[100] w-72 max-w-[calc(100vw-1rem)] rounded-[12px] border border-[#dce0da] bg-[#fffefa] p-2 dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)]"
        >
          <p className="break-words px-2 py-2 text-[16px] font-medium text-[#172b26] dark:text-white">{name}</p>
          {mode === "menu" ? (
            <>
              <button
                type="button"
                role="menuitem"
                className="flex min-h-11 w-full items-center gap-2 rounded-[12px] px-2 text-left text-[16px] text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white"
                onClick={() => { setMode("closed"); onOpenAccess(); }}
              >
                <UsersRound className="h-5 w-5 shrink-0" strokeWidth={2} aria-hidden="true" />
                {t("business.switcher.team", "Equipo y accesos")}
              </button>
              {canSwitch ? (
                <button
                  type="button"
                  role="menuitem"
                  className="flex min-h-11 w-full items-center gap-2 rounded-[12px] px-2 text-left text-[16px] text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white"
                  onClick={() => setMode("choose")}
                >
                  <ArrowLeftRight className="h-5 w-5 shrink-0" strokeWidth={2} aria-hidden="true" />
                  {t("business.switcher.change", "Cambiar de negocio")}
                </button>
              ) : null}
            </>
          ) : (
            <ul
              ref={listRef}
              role="listbox"
              tabIndex={-1}
              aria-label={t("business.switcher.choose", "Elige un negocio")}
              aria-activedescendant={options[active] ? `${menuId}-${options[active].grant_id}` : undefined}
              onKeyDown={onListKey}
              className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]"
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
                    className={`flex min-h-11 cursor-pointer items-center rounded-[12px] px-2 text-[16px] ${index === active ? "bg-[#efebdf]" : ""}`}
                  >
                    <span className="min-w-0 break-words">{optionName}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
