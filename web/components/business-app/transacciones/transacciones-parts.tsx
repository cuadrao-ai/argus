"use client";

import type { ReactNode } from "react";
import { Banknote, CreditCard, Landmark, type LucideIcon } from "lucide-react";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatAmount, formatMoney, UNKNOWN_VALUE } from "../business-format";
import { magnitude, signOf, type AccountKind, type MatchState, type Money, type MovementAccount } from "./transacciones-model";
import { useTransaccionesWords } from "./transacciones-words";

const line = { fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

/** One shape per state, never a colour: igualar states are their own axis beside the Bandeja's coloured statuses. */
const SHAPES: Record<MatchState, ReactNode> = {
  igualada: <><circle cx="8" cy="8" r="6.25" {...line} /><path d="M5.3 8.2 7.1 10l3.6-3.8" {...line} /></>,
  sugerencia: <><circle cx="8" cy="8" r="6.25" {...line} strokeDasharray="2 2" /><circle cx="8" cy="8" r="1.6" fill="currentColor" /></>,
  falta_comprobante: <circle cx="8" cy="8" r="6.25" {...line} />,
  no_lleva: <><circle cx="8" cy="8" r="6.25" {...line} /><path d="m3.6 12.4 8.8-8.8" {...line} /></>,
  sin_movimiento: <><path d="M4 1.75h5.5L12.25 4.5v9.75H4Z" {...line} /><path d="M9.25 1.75V4.75h3M6 8h4.25M6 10.75h4.25" {...line} /></>,
};

/** The state as a gray 16px icon. Its word is its label for screen readers and its tooltip on hover. */
export function StateIcon({ state }: { state: MatchState }) {
  const { stateWord } = useTransaccionesWords();
  const word = stateWord(state);
  return (
    <Tooltip content={word} side="top">
      <span data-testid="state-icon" data-state={state} role="img" aria-label={word} className="inline-flex h-4 w-4 shrink-0 text-[#56635e] dark:text-white/60">
        <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden="true">{SHAPES[state]}</svg>
      </span>
    </Tooltip>
  );
}

/** Unknown is a plain dash on screen and its meaning ("sin dato" unless a cell says better) to a screen reader; never a zero. */
export function Unknown({ meaning }: { meaning?: string }) {
  const { t } = useTransaccionesWords();
  return (
    <span>
      <span aria-hidden="true">{UNKNOWN_VALUE}</span>
      <span className="sr-only">{meaning ?? t("business.transactions.unknown", "sin dato")}</span>
    </span>
  );
}

const SIGN = { in: "+", out: "−", zero: "" } as const;

/**
 * A signed amount: "+" for money in, "−" for money out, nothing on a known
 * zero. Under a header that names the currency the row shows the number
 * alone; another currency keeps its symbol. Read aloud with its sign word.
 */
export function SignedAmount({ money, header }: { money: Money; header: string | null }) {
  const { t, locale } = useTransaccionesWords();
  const sign = signOf(money);
  const bare = magnitude(money);
  const number = money.currency === header ? formatAmount(bare.amount, bare.currency, locale) : formatMoney(bare.amount, bare.currency, locale);
  const spoken = `${sign === "zero" ? "" : `${t(`business.transactions.sign.${sign}`)} `}${formatMoney(bare.amount, bare.currency, locale)}`;
  return (
    <span className="cuadrao-amount whitespace-nowrap tabular-nums">
      <span aria-hidden="true">{SIGN[sign]}{number}</span>
      <span className="sr-only">{spoken}</span>
    </span>
  );
}

/** A document's own figure (a total, its ITBIS): exact, with its symbol, no sign. */
export function PlainAmount({ money }: { money: Money }) {
  const { locale } = useTransaccionesWords();
  return <span className="cuadrao-amount whitespace-nowrap tabular-nums">{formatMoney(magnitude(money).amount, money.currency, locale)}</span>;
}

/**
 * Totals in one currency each, side by side, never added; unknown when the
 * server does not serve them. With no row in the period the total is a known
 * zero, shown in the currency `zeroIn` names, or as unknown when nothing names one.
 */
export function MoneyList({ totals, header, locale, zeroIn = header }: { totals: readonly Money[] | null; header: string | null; locale: string; zeroIn?: string | null }) {
  if (totals === null) return <Unknown />;
  if (totals.length === 0) return zeroIn ? <span className="cuadrao-amount tabular-nums">{formatMoney("0", zeroIn, locale)}</span> : <Unknown />;
  return (
    <span className="flex flex-wrap items-baseline gap-x-2">
      {totals.map((money, index) => (
        <span key={money.currency} className={`cuadrao-amount tabular-nums ${index > 0 ? "text-[14px] font-normal text-[#56635e] dark:text-white/60" : ""}`}>{formatMoney(magnitude(money).amount, money.currency, locale)}</span>
      ))}
    </span>
  );
}

const ACCOUNT_ICON: Record<AccountKind, LucideIcon> = { bank: Landmark, card: CreditCard, cash: Banknote };

export function AccountLabel({ account }: { account: MovementAccount | null }) {
  if (!account) return <Unknown />;
  const Icon = ACCOUNT_ICON[account.kind];
  return (
    <span className="flex min-w-0 items-center gap-2">
      <Icon className="h-3.5 w-3.5 shrink-0 text-[#56635e] dark:text-white/60" aria-hidden="true" />
      {account.name ? <span className="truncate">{account.name}</span> : <Unknown />}
    </span>
  );
}

export function KeyHint({ children }: { children: string }) {
  // Drawn in the label's own colour, so it reads on a green primary and on an outlined button alike. Phones have no keys to show.
  return <kbd className="ml-1.5 hidden h-[18px] tablet:inline-flex min-w-[18px] items-center justify-center rounded-mark border border-current/30 px-1 font-sans text-[11px] font-medium opacity-80">{children}</kbd>;
}

/** A long value cut to one line; the whole of it shows on hover and keyboard focus. */
export function Truncated({ text, className = "" }: { text: string; className?: string }) {
  return (
    <Tooltip content={text} side="top">
      <span className={`block min-w-0 truncate ${className}`}>{text}</span>
    </Tooltip>
  );
}
