"use client";

import { HandCoins, Store, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { businessBankMatchingEnabled } from "@/lib/private-alpha-flags";

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
  currency: string;
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
  const { t } = useTranslation();
  if (!enabled) return null;
  const kind = KIND[document.kind];
  const Icon = kind.icon;
  const tap = { minHeight: TAP_TARGET_PX, minWidth: TAP_TARGET_PX };
  return (
    <article data-testid="bank-match-card" className="rounded-[20px] border border-black/[0.06] bg-white p-4 dark:border-white/[0.06] dark:bg-[#1f2225]">
      <div data-testid="bank-match-row" className="flex flex-row flex-nowrap items-stretch gap-3">
        <section data-testid="bank-match-line" className="min-w-0 flex-1">
          <p className="text-[13px] text-black/55 dark:text-white/55">{line.occurredOn}</p>
          <p className="mt-1 text-[15px] text-black dark:text-white">{line.description}</p>
          <p className="mt-2 font-medium tabular-nums text-black dark:text-white">{line.amount} {line.currency}</p>
        </section>
        <section data-testid="bank-match-document" className="min-w-0 flex-1">
          <p data-testid="bank-match-kind" className="inline-flex items-center gap-2 text-[15px] text-black dark:text-white">
            <Icon aria-hidden="true" size={18} />
            <span>{t(kind.key, kind.label)}</span>
          </p>
          <p className="mt-1 text-[13px] text-black/55 dark:text-white/55">{document.occurredOn}</p>
          <p className="mt-1 text-[15px] text-black dark:text-white">{document.description}</p>
          <p className="mt-2 font-medium tabular-nums text-black dark:text-white">{document.amount} {document.currency}</p>
        </section>
      </div>
      <div className="mt-4 flex flex-row flex-wrap gap-2">
        <button
          type="button"
          data-testid="bank-match-confirm"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full bg-black px-4 text-[15px] font-medium text-white dark:bg-white dark:text-black"
          style={tap}
          disabled={disabled}
          onClick={onConfirm}
        >
          {t("business.bank.suggestion.confirm", "Confirmar")}
        </button>
        <button
          type="button"
          data-testid="bank-match-decline"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-black/10 bg-white px-4 text-[15px] font-medium text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white"
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
