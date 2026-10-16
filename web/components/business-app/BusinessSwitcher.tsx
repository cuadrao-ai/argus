"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { GrantedSpace } from "@/lib/business-api";
import { formatBusinessName } from "./business-format";

/**
 * The Business the person is working in, always visible at the top left, and
 * the way to change it when they may enter more than one. The names are the
 * server's, the choice is a grant the server proves on every request. With
 * only their own Business the control is a plain label.
 */

function initial(name: string): string {
  const letter = name.trim().charAt(0);
  return letter ? letter.toLocaleUpperCase() : "·";
}

export default function BusinessSwitcher({ spaces, chosen, collapsed, onChoose }: {
  spaces: GrantedSpace[] | null;
  chosen: GrantedSpace | null;
  collapsed: boolean;
  onChoose: (grantId: string | null) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const options = useMemo(() => spaces ?? [], [spaces]);
  const switchable = options.length > 1 || (options.length === 1 && options[0].role !== "owner");
  const current = chosen ?? options[0] ?? null;

  useEffect(() => {
    if (!open) return;
    const index = Math.max(0, options.findIndex((space) => space.grant_id === current?.grant_id));
    setActive(index);
    const close = (event: MouseEvent) => {
      if (!listRef.current?.contains(event.target as Node) && !buttonRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open, options, current?.grant_id]);

  useEffect(() => {
    if (open) listRef.current?.focus();
  }, [open]);

  if (!current) return null;
  const roleLine = current.role === "owner" ? t("business.switcher.own", "Your Business") : t("business.switcher.role_accountant", "View and prepare");
  const fallback = t("business.overview.title", "My business");
  const name = formatBusinessName(current.name, fallback);

  const choose = (space: GrantedSpace) => {
    setOpen(false);
    onChoose(space.role === "owner" ? null : space.grant_id);
    buttonRef.current?.focus();
  };

  const onListKey = (event: React.KeyboardEvent<HTMLUListElement>) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((i) => Math.min(options.length - 1, i + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (event.key === "Home") { event.preventDefault(); setActive(0); }
    else if (event.key === "End") { event.preventDefault(); setActive(options.length - 1); }
    else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); if (options[active]) choose(options[active]); }
    else if (event.key === "Escape" || event.key === "Tab") { setOpen(false); buttonRef.current?.focus(); if (event.key === "Escape") event.preventDefault(); }
    else if (event.key.length === 1 && /\S/.test(event.key)) {
      const letter = event.key.toLocaleLowerCase();
      const index = options.findIndex((space, i) => i > active && formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      const wrapped = index >= 0 ? index : options.findIndex((space) => formatBusinessName(space.name, fallback).toLocaleLowerCase().startsWith(letter));
      if (wrapped >= 0) setActive(wrapped);
    }
  };

  const badge = (
    <span aria-hidden="true" className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] text-[13px] font-semibold ${current.role === "owner" ? "bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]" : "bg-[var(--cuadrao-cream)] text-[var(--cuadrao-green)] ring-1 ring-[var(--cuadrao-green)]/30"}`}>
      {initial(name)}
    </span>
  );

  if (!switchable) {
    return (
      <div data-testid="business-switcher" data-switchable="false" className={`mx-[6px] mb-1 flex items-center gap-2.5 rounded-[14px] px-2 py-2 ${collapsed ? "justify-center" : ""}`} title={collapsed ? name : undefined}>
        {badge}
        {!collapsed ? (
          <span className="min-w-0">
            <span data-testid="business-current-name" className="block truncate text-[14px] font-medium text-black dark:text-white">{name}</span>
            <span className="block truncate text-[11.5px] text-black/50 dark:text-white/50">{roleLine}</span>
          </span>
        ) : <span className="sr-only" data-testid="business-current-name">{name}</span>}
      </div>
    );
  }

  return (
    <div className="relative mx-[6px] mb-1" data-testid="business-switcher" data-switchable="true">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={`${t("business.switcher.label", "Business")}: ${name}. ${t("business.switcher.change", "Switch Business")}`}
        title={collapsed ? `${name} · ${t("business.switcher.change", "Switch Business")}` : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); } }}
        className={`flex h-12 w-full items-center gap-2.5 rounded-[14px] px-2 text-left transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 dark:hover:bg-white/5 ${collapsed ? "justify-center" : ""}`}
      >
        {badge}
        {!collapsed ? (
          <>
            <span className="min-w-0 flex-1">
              <span data-testid="business-current-name" className="block truncate text-[14px] font-medium text-black dark:text-white">{name}</span>
              <span className="block truncate text-[11.5px] text-black/50 dark:text-white/50">{current.role === "owner" ? roleLine : t("business.switcher.client_cue", "Client: {{name}}", { name: "" }).replace(/:\s*$/, "") + " · " + roleLine}</span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-black/40 dark:text-white/40" aria-hidden="true" />
          </>
        ) : <span className="sr-only" data-testid="business-current-name">{name}</span>}
      </button>
      {open ? (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          aria-label={t("business.switcher.choose", "Choose a Business")}
          aria-activedescendant={options[active] ? `${listId}-${options[active].grant_id}` : undefined}
          onKeyDown={onListKey}
          className="absolute left-0 top-full z-30 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-[16px] border border-black/10 bg-white p-1.5 shadow-lg focus-visible:outline-none dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)]"
        >
          {options.map((space, index) => {
            const selected = space.grant_id === current.grant_id;
            const optionName = formatBusinessName(space.name, fallback);
            return (
              <li
                key={space.grant_id}
                id={`${listId}-${space.grant_id}`}
                role="option"
                aria-selected={selected}
                data-active={index === active ? "true" : undefined}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(space)}
                className={`flex min-h-11 cursor-pointer items-center gap-2.5 rounded-[12px] px-2 text-[14px] ${index === active ? "bg-black/5 dark:bg-white/5" : ""}`}
              >
                <span aria-hidden="true" className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] text-[12px] font-semibold ${space.role === "owner" ? "bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]" : "bg-[var(--cuadrao-cream)] text-[var(--cuadrao-green)] ring-1 ring-[var(--cuadrao-green)]/30"}`}>{initial(optionName)}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-black dark:text-white">{optionName}</span>
                  <span className="block truncate text-[11.5px] text-black/50 dark:text-white/50">{space.role === "owner" ? t("business.switcher.own", "Your Business") : `${t("business.switcher.client", "Client")} · ${t("business.switcher.role_accountant", "View and prepare")}`}</span>
                </span>
                {selected ? <Check className="h-4 w-4 shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" /> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
