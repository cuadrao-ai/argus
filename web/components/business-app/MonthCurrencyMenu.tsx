"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { resolveLanguage } from "@/lib/language-features";

function currencyName(code: string, locale: string): string {
  try {
    const name = new Intl.DisplayNames([locale], { type: "currency" }).of(code) ?? code;
    return `${name.charAt(0).toLocaleUpperCase(locale)}${name.slice(1)}`;
  } catch {
    return code;
  }
}

/**
 * Moneda: which currency the figures show, when there is more than one. The ISO code is the button ("DOP"); the
 * list names each currency ("DOP · Peso dominicano") with its document count when the screen has one. Nothing
 * converts: each choice shows that currency's own figures.
 */
export function MonthCurrencyMenu({
  currencies,
  value,
  onChoose,
  counts,
  note,
}: {
  /** The currencies, the Business currency first. */
  currencies: readonly string[];
  value: string;
  onChoose: (currency: string) => void;
  /** Each currency's document count, from the server, beside its name. */
  counts?: Readonly<Record<string, number>>;
  /** A screen's own line beside the button (Registros names what each other currency holds). */
  note?: ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [announced, setAnnounced] = useState<string | null>(null);
  const [position, setPosition] = useState({ left: 8, top: 48 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  function choose(currency: string) {
    if (currency !== value) {
      onChoose(currency);
      setAnnounced(currency);
    }
    close();
  }

  useOverlayLayer({
    isOpen: open,
    overlayId: listId,
    containerRef: listRef,
    onKeyDown: (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((index) => Math.min(currencies.length - 1, index + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((index) => Math.max(0, index - 1));
      } else if (event.key === "Home") {
        event.preventDefault();
        setActive(0);
      } else if (event.key === "End") {
        event.preventDefault();
        setActive(Math.max(0, currencies.length - 1));
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        const currency = currencies[active];
        if (currency) choose(currency);
      }
    },
    onOutsidePointerDown: (event) => {
      if (buttonRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    },
  });

  useEffect(() => {
    if (open) listRef.current?.focus();
  }, [open]);

  return (
    <div data-testid="month-close-currency-row" className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <button
        ref={buttonRef}
        type="button"
        data-testid="month-close-currency"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={t("business.month_close.currency_menu_named", { currency: value })}
        className="inline-flex min-h-11 items-center gap-1 rounded-full border border-black/10 px-3 text-[14px] font-medium tabular-nums text-black hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40 dark:border-white/15 dark:text-white dark:hover:bg-white/5"
        onClick={() => {
          if (open) {
            close();
            return;
          }
          // Placed before it opens, so the list never paints at a default spot first.
          const rect = buttonRef.current?.getBoundingClientRect();
          if (rect) setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - 256 - 8)), top: rect.bottom + 4 });
          setActive(Math.max(0, currencies.indexOf(value)));
          setOpen(true);
        }}
      >
        {value}
        <ChevronDown className="h-4 w-4 text-black/60 dark:text-white/60" aria-hidden="true" />
      </button>
      {note ?? null}
      <p role="status" data-testid="month-close-currency-announce" className="sr-only">
        {announced ? t("business.month_close.currency_announce", { currency: announced }) : ""}
      </p>
      {open ? createPortal(
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          tabIndex={-1}
          data-testid="month-close-currency-picker"
          aria-label={t("business.month_close.currency_menu")}
          aria-activedescendant={currencies[active] ? `${listId}-${currencies[active]}` : undefined}
          style={{ left: position.left, top: position.top }}
          className="fixed z-[100] w-64 rounded-surface border border-black/10 bg-white p-1.5 shadow-lg focus-visible:outline-none dark:border-white/10 dark:bg-[var(--cuadrao-menu-surface)]"
        >
          <li role="presentation" aria-hidden="true" className="px-3 pb-1 pt-1.5 text-[12px] font-medium text-[#56635e] dark:text-white/70">
            {t("business.month_close.currency_menu")}
          </li>
          {currencies.map((currency, index) => {
            const selected = currency === value;
            return (
              <li
                key={currency}
                id={`${listId}-${currency}`}
                role="option"
                aria-selected={selected}
                data-currency={currency}
                data-active={index === active ? "true" : undefined}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(currency)}
                className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-item px-3 py-1.5 text-black dark:text-white ${index === active ? "bg-black/5 dark:bg-white/5" : ""}`}
              >
                <span className="min-w-0 flex-1 text-[15px]"><span className="font-medium tabular-nums">{currency}</span>{` · ${currencyName(currency, locale)}`}</span>
                {counts?.[currency] !== undefined ? <span data-testid="month-close-currency-count" className="shrink-0 text-[13px] tabular-nums text-[#56635e] dark:text-white/70">{counts[currency]}</span> : null}
                <Check className={`h-4 w-4 shrink-0 text-[var(--cuadrao-green)] ${selected ? "" : "invisible"}`} aria-hidden="true" />
              </li>
            );
          })}
        </ul>,
        document.body,
      ) : null}
    </div>
  );
}
