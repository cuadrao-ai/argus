"use client";

import { useTranslation } from "react-i18next";
import { formatShortDay } from "../business-format";
import { signOf, type MatchState, type Movement, type SuggestionReason } from "./transacciones-model";
import { resolveLanguage } from "@/lib/language-features";

/** The words Transacciones says about a row: its state, its Detalle line, and why a pair was offered. */
export function useTransaccionesWords() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const stateWord = (state: MatchState) => t(`business.transactions.states.${state}`);

  /** One plain sentence: why the row is in this state. */
  const detail = (movement: Movement): string => {
    const match = movement.match;
    switch (match.state) {
      case "igualada": {
        const document = match.document;
        if (!document) return t("business.transactions.detail.igualada");
        return document.ncf
          ? t(`business.transactions.detail.igualada_${document.kind}`, { ncf: document.ncf })
          : t(`business.transactions.detail.igualada_${document.kind}_sin_ncf`);
      }
      case "sugerencia": {
        const { document } = match.suggestion;
        return t(`business.transactions.detail.suggested_${document.kind}`, { day: formatShortDay(document.occurredOn, locale) });
      }
      case "falta_comprobante":
        return signOf(movement.money) === "in" ? t("business.transactions.detail.falta_deposit") : t("business.transactions.detail.falta_charge");
      case "no_lleva":
        return t(`business.transactions.detail.no_lleva.${match.reason}`);
      case "sin_movimiento":
        return t("business.transactions.detail.sin_movimiento");
    }
  };

  const reason = (item: SuggestionReason): string => {
    if (item.kind === "amount") return t("business.transactions.why.amount");
    if (item.kind === "name") return t("business.transactions.why.name");
    // `days` is the document's date minus the movement's: below zero, the document came first.
    const apart = Math.abs(item.days);
    if (apart === 0) return t("business.transactions.why.date_same");
    if (item.days < 0) return apart === 1 ? t("business.transactions.why.date_one") : t("business.transactions.why.date_many", { count: apart });
    return apart === 1 ? t("business.transactions.why.date_after_one") : t("business.transactions.why.date_after_many", { count: apart });
  };

  return { t, locale, stateWord, detail, reason };
}
