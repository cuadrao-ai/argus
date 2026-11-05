import { test } from "bun:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { TFunction } from "i18next";

import {
  recoveryDisplayFromMetadata,
  recoveryDisplayText,
} from "../lib/chat-recovery-display";

const root = join(import.meta.dir, "..");
const enCatalog = JSON.parse(
  readFileSync(join(root, "public/locales/en/common.json"), "utf8"),
) as Record<string, unknown>;
const esCatalog = JSON.parse(
  readFileSync(join(root, "public/locales/es-419/common.json"), "utf8"),
) as Record<string, unknown>;

function tFromCatalog(catalog: Record<string, unknown>): TFunction {
  const translate = (key: string, options?: Record<string, unknown> | string) => {
    const template = key
      .split(".")
      .reduce<unknown>(
        (value, segment) =>
          typeof value === "object" && value !== null && !Array.isArray(value)
            ? (value as Record<string, unknown>)[segment]
            : undefined,
        catalog,
      );
    if (typeof template !== "string") {
      return key;
    }
    const values =
      typeof options === "object" && options !== null ? options : {};
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
      String(values[name] ?? ""),
    );
  };
  return translate as unknown as TFunction;
}

const en = tFromCatalog(enCatalog);
const es = tFromCatalog(esCatalog);

function recoveryText(metadata: Record<string, unknown>, t: TFunction): string {
  return recoveryDisplayText(recoveryDisplayFromMetadata(metadata), t);
}

function unsupportedStrategyMetadata(rawValue: string): Record<string, unknown> {
  return {
    clarification: {
      kind: "unsupported_recovery",
      reason_code: "unsupported_strategy_logic",
      prompt_source: "degraded_fallback",
      requested_field: "unsupported_constraints",
      semantic_needs: ["simplification_choice"],
      payload: {
        raw_value: rawValue,
        strategy: { asset_universe: ["TSLA"] },
      },
      options: [
        {
          id: "rsi_threshold",
          replacement_values: { simplify_logic: "rsi_only" },
        },
        {
          id: "buy_and_hold",
          replacement_values: { strategy_type: "buy_and_hold" },
        },
      ],
    },
  };
}

for (const rawValue of [
  "User wants to invest $500",
  "MACD golden cross",
  "BTC_USDT",
]) {
  test(`issue 453 keeps generic raw value ${rawValue} out of recovery sentence subjects`, () => {
    const metadata = unsupportedStrategyMetadata(rawValue);
    const english = recoveryText(metadata, en);
    const spanish = recoveryText(metadata, es);

    assert.equal(
      english,
      "Cuadrao can't run that rule directly yet for TSLA. Which supported direction should I use: Use a supported RSI threshold rule or Compare with buy and hold?",
    );
    assert.equal(
      spanish,
      "Cuadrao todavía no puede ejecutar esa regla directamente para TSLA. ¿Qué camino quieres usar: Usar una regla RSI compatible o Comparar con comprar y mantener?",
    );
    assert.ok(!english.includes(rawValue));
    assert.ok(!spanish.includes(rawValue));
  });
}

function startingCapitalMetadata(
  minimum: number,
  maximum: number,
): Record<string, unknown> {
  return {
    clarification: {
      kind: "unsupported_recovery",
      reason_code: "unsupported_starting_capital",
      prompt_source: "degraded_fallback",
      requested_field: "capital_amount",
      semantic_needs: ["simplification_choice"],
      payload: {
        raw_value: "User wants to invest $500",
        minimum,
        maximum,
        strategy: { asset_universe: ["NFLX"] },
      },
      options: [
        {
          id: "option_0",
          replacement_values: { capital_amount: 10000 },
        },
      ],
    },
  };
}

test("issue 453 renders starting capital only from typed numeric bounds", () => {
  const metadata = startingCapitalMetadata(1000, 100000000);
  const english = recoveryText(metadata, en);
  const spanish = recoveryText(metadata, es);

  assert.equal(
    english,
    "Starting capital must be between $1,000 and $100,000,000. What amount in that range should I use?",
  );
  assert.equal(
    spanish,
    "El capital inicial debe estar entre $1,000 y $100,000,000. ¿Qué monto dentro de ese rango quieres usar?",
  );
  assert.ok(!english.includes("User wants to invest $500"));
  assert.ok(!spanish.includes("User wants to invest $500"));
});

for (const { minimum, maximum } of [
  { minimum: 100000000, maximum: 1000 },
  { minimum: Number.NaN, maximum: 100000000 },
  { minimum: 1000, maximum: Number.POSITIVE_INFINITY },
]) {
  test(`issue 453 rejects malformed starting-capital bound pair ${minimum} to ${maximum}`, () => {
    const metadata = startingCapitalMetadata(minimum, maximum);

    assert.equal(recoveryText(metadata, en), en("chat.clarification.starting_capital_unavailable_bounds"));
    assert.equal(recoveryText(metadata, es), es("chat.clarification.starting_capital_unavailable_bounds"));
  });
}
