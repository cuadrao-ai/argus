import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  confirmationPeriodAdjustmentText,
} from "../lib/confirmation-period-adjustment";
import type { StrategyConfirmationPeriodAdjustment } from "../components/chat/types";

const adjustment: StrategyConfirmationPeriodAdjustment = {
  code: "effective_window_adjusted",
  requested_date_range: { start: "2024-01-01", end: "2024-01-05" },
  effective_date_range: { start: "2024-01-03", end: "2024-01-05" },
};

const limitedAdjustment: StrategyConfirmationPeriodAdjustment = {
  code: "effective_window_adjusted",
  requested_date_range: { start: "2020-01-02", end: "2020-12-31" },
  effective_date_range: { start: "2020-07-27", end: "2020-12-31" },
  limited_by: { symbol: "SPY", first_available: "2020-07-27" },
};

const SHARED_WINDOW_KEY = "chat.confirmation.period_adjustment";
const LIMITED_BY_KEY = "chat.confirmation.period_adjustment_limited_by";

const translations: Record<string, Record<string, string>> = {
  en: {
    [SHARED_WINDOW_KEY]:
      "I adjusted the test period to {{period}} because every asset and the benchmark need a shared data window.",
    [LIMITED_BY_KEY]:
      "I adjusted the test period to {{period}} because Cuadrao has price data for {{symbol}} only from {{date}}.",
  },
  "es-419": {
    [SHARED_WINDOW_KEY]:
      "Ajusté el período de la prueba a {{period}} porque cada activo y la referencia necesitan un rango de datos compartido.",
    [LIMITED_BY_KEY]:
      "Ajusté el período de la prueba a {{period}} porque Cuadrao solo tiene precios de {{symbol}} desde el {{date}}.",
  },
};

const translate = (locale: string, keys: string[] = []) => (
  key: string,
  options: { period: string; symbol?: string; date?: string },
) => {
  keys.push(key);
  return translations[locale][key]
    .replace("{{period}}", options.period)
    .replace("{{symbol}}", options.symbol ?? "")
    .replace("{{date}}", options.date ?? "");
};

describe("confirmation period adjustment", () => {
  test("renders a provider-neutral English lead-in from typed dates", () => {
    const text = confirmationPeriodAdjustmentText(
      adjustment,
      translate("en"),
      "en",
    );

    expect(text).toBe(
      "I adjusted the test period to Jan 3, 2024 – Jan 5, 2024 because every asset and the benchmark need a shared data window.",
    );
    expect(text).not.toContain("Alpaca");
  });

  test("renders the same typed contract in Spanish", () => {
    expect(
      confirmationPeriodAdjustmentText(
        adjustment,
        translate("es-419"),
        "es-419",
      ),
    ).toBe(
      "Ajusté el período de la prueba a 3 ene 2024 – 5 ene 2024 porque cada activo y la referencia necesitan un rango de datos compartido.",
    );
  });

  test("names the limiting asset and its first available date in English", () => {
    const keys: string[] = [];

    expect(
      confirmationPeriodAdjustmentText(
        limitedAdjustment,
        translate("en", keys),
        "en",
      ),
    ).toBe(
      "I adjusted the test period to Jul 27, 2020 – Dec 31, 2020 because Cuadrao has price data for SPY only from Jul 27, 2020.",
    );
    expect(keys).toEqual([LIMITED_BY_KEY]);
  });

  test("names the limiting asset and its first available date in Spanish", () => {
    expect(
      confirmationPeriodAdjustmentText(
        limitedAdjustment,
        translate("es-419"),
        "es-419",
      ),
    ).toBe(
      "Ajusté el período de la prueba a 27 jul 2020 – 31 dic 2020 porque Cuadrao solo tiene precios de SPY desde el 27 jul 2020.",
    );
  });

  test("keeps the shared data window reason when no usable limiting asset is named", () => {
    const cards: StrategyConfirmationPeriodAdjustment[] = [
      adjustment,
      {
        ...limitedAdjustment,
        limited_by: { symbol: "SPY", first_available: "not-a-date" },
      },
      {
        ...limitedAdjustment,
        limited_by: { symbol: " ", first_available: "2020-07-27" },
      },
    ];

    for (const card of cards) {
      const keys: string[] = [];
      const text = confirmationPeriodAdjustmentText(
        card,
        translate("en", keys),
        "en",
      );

      expect(keys).toEqual([SHARED_WINDOW_KEY]);
      expect(text).toContain("need a shared data window");
    }
  });

  test("ships both lead-in reasons in every supported locale", () => {
    for (const locale of Object.keys(translations)) {
      const common = JSON.parse(
        readFileSync(
          join(import.meta.dir, `../public/locales/${locale}/common.json`),
          "utf8",
        ),
      );

      expect(common.chat.confirmation.period_adjustment).toBe(
        translations[locale][SHARED_WINDOW_KEY],
      );
      expect(common.chat.confirmation.period_adjustment_limited_by).toBe(
        translations[locale][LIMITED_BY_KEY],
      );
    }
  });

  test("renders no lead-in for an unknown adjustment", () => {
    expect(
      confirmationPeriodAdjustmentText(
        { ...adjustment, code: "unknown" },
        translate("en"),
        "en",
      ),
    ).toBeNull();
  });

  test("places the lead-in immediately above the corrected confirmation card", () => {
    const source = readFileSync(
      join(import.meta.dir, "../components/chat/ChatMessage.tsx"),
      "utf8",
    );
    const branchStart = source.indexOf(
      ') : message.kind === "strategy_confirmation"',
    );
    const branchEnd = source.indexOf(
      'message.contentPresentation === "result_breakdown"',
      branchStart,
    );
    const branch = source.slice(branchStart, branchEnd);

    expect(branch.indexOf("{confirmationPeriodLeadIn ? (")).toBeGreaterThan(-1);
    expect(branch.indexOf("<StrategyConfirmationCard")).toBeGreaterThan(
      branch.indexOf("{confirmationPeriodLeadIn ? ("),
    );
  });
});
