"use client";

import { useTranslation } from "react-i18next";
import { formatMoney, formatShortDay } from "../business-format";
import { magnitude, signOf, type MatchState, type Movement, type SuggestionReason } from "./transacciones-model";

/** The words Transacciones says about a row: its state, its Detalle line, and why a pair was offered. */
export function useTransaccionesWords() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "es-419";
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
        const { document, documentKind } = match.suggestion;
        return document?.occurredOn
          ? t(`business.transactions.detail.suggested_${documentKind}`, { day: formatShortDay(document.occurredOn, locale) })
          : t(`business.transactions.detail.suggested_${documentKind}_unknown`);
      }
      case "falta_comprobante":
        return signOf(movement.money) === "in" ? t("business.transactions.detail.falta_deposit") : t("business.transactions.detail.falta_charge");
      case "igualada_en_parte":
        return t("business.transactions.detail.en_parte", { amount: formatMoney(magnitude(match.missing).amount, match.missing.currency, locale) });
      case "no_lleva":
        return t(`business.transactions.detail.no_lleva.${match.reason}`);
      case "sin_movimiento":
        return t("business.transactions.detail.sin_movimiento");
    }
  };

  const reason = (item: SuggestionReason): string => {
    if (item.kind === "amount") return t("business.transactions.why.amount");
    if (item.kind === "name") return t("business.transactions.why.name");
    if (item.daysBefore === null) return t("business.transactions.why.date_near");
    if (item.daysBefore === 0) return t("business.transactions.why.date_same");
    return item.daysBefore === 1 ? t("business.transactions.why.date_one") : t("business.transactions.why.date_many", { count: item.daysBefore });
  };

  return { t, locale, stateWord, detail, reason };
}
