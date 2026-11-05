"use client";

import { HandCoins, Store, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { resolveLanguage } from "@/lib/language-features";
import { businessBankMatchingEnabled } from "@/lib/private-alpha-flags";
import { formatMoney, UNKNOWN_VALUE } from "./business-format";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

/** Tailwind `h-11` is 44px. The inline size is what the tap-target test reads. */
const TAP_TARGET_PX = 44;

const KIND: Record<"receipt" | "venta", { icon: LucideIcon; key: string; label: string }> = {
  receipt: { icon: HandCoins, key: "business.bank.suggestion.receipt", label: "Gasto" },
  venta: { icon: Store, key: "business.bank.suggestion.venta", label: "Venta" },
};

export type BankMatchSide = {
  occurredOn: string;
  description: string;
  amount: string;
  /** Unknown reads as "-", never as a default currency. */
  currency: string | null;
};

export type BankMatchSuggestionCardProps = {
  line: BankMatchSide;
  document: BankMatchSide & { kind: "receipt" | "venta" };
  onConfirm: () => void;
  onDecline: () => void;
  disabled?: boolean;
  enabled?: boolean;
};

export function BankMatchSuggestionCard({
  line,
  document,
  onConfirm,
  onDecline,
  disabled = false,
  enabled = businessBankMatchingEnabled,
}: BankMatchSuggestionCardProps) {
  const { t, i18n } = useTranslation();
  if (!enabled) return null;
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const money = (side: BankMatchSide) => formatMoney(side.amount, side.currency, locale) || UNKNOWN_VALUE;
  const kind = KIND[document.kind];
  const Icon = kind.icon;
  const tap = { minHeight: TAP_TARGET_PX, minWidth: TAP_TARGET_PX };
  return (
    <article data-testid="bank-match-card" className="rounded-surface border border-black/[0.06] bg-white p-4 dark:border-white/[0.06] dark:bg-[#1f2225]">
      <div data-testid="bank-match-row" className="flex flex-row flex-nowrap items-stretch gap-3">
        <section data-testid="bank-match-line" className="min-w-0 flex-1">
          <p className="text-[13px] text-black/55 dark:text-white/55">{line.occurredOn}</p>
          <p className="mt-1 text-[15px] text-black dark:text-white">{line.description}</p>
          <p className="mt-2 font-medium tabular-nums text-black dark:text-white">{money(line)}</p>
        </section>
        <section data-testid="bank-match-document" className="min-w-0 flex-1">
          <p data-testid="bank-match-kind" className="inline-flex items-center gap-2 text-[15px] text-black dark:text-white">
            <Icon aria-hidden="true" size={18} />
            <span>{t(kind.key, kind.label)}</span>
          </p>
          <p className="mt-1 text-[13px] text-black/55 dark:text-white/55">{document.occurredOn}</p>
          <p className="mt-1 text-[15px] text-black dark:text-white">{document.description}</p>
          <p className="mt-2 font-medium tabular-nums text-black dark:text-white">{money(document)}</p>
        </section>
      </div>
      <div className="mt-4 flex flex-row flex-wrap gap-2">
        <button
          type="button"
          data-testid="bank-match-confirm"
          className={`${primaryButtonClass} min-w-11`}
          style={tap}
          disabled={disabled}
          onClick={onConfirm}
        >
          {t("business.bank.suggestion.confirm", "Confirmar")}
        </button>
        <button
          type="button"
          data-testid="bank-match-decline"
          className={`${secondaryButtonClass} min-w-11`}
          style={tap}
          disabled={disabled}
          onClick={onDecline}
        >
          {t("business.bank.suggestion.decline", "No es este")}
        </button>
      </div>
    </article>
  );
}
