import { cache } from "react";
import type { AssetClass } from "./argus-types";
import { CUADRAO_API_BASE_URL } from "./argus-api-transport";
import { receiptDocumentSupported, type PublicReceiptDocument, type ReceiptKind } from "./public-receipt-turns";

/**
 * Mirrors src/argus/api/public_excerpt_schemas.py. The payload is closed: this
 * type is the whole of what a receipt can ever show.
 */
export type PublicReceiptDateRange = {
  start: string;
  end: string;
};

/** Closed key set; the label is rendered from the key in the viewer's language. */
export type PublicReceiptStrategyFactKey =
  | "strategy_type"
  | "cadence"
  | "indicator"
  | "indicator_period"
  | "entry_threshold"
  | "exit_threshold"
  // A crossover is defined by both of its windows, so neither one is optional.
  | "fast_indicator"
  | "fast_period"
  | "slow_indicator"
  | "slow_period"
  // Entry and exit are compiled independently and need not match, so when they
  // differ the exit side gets its own facts rather than being spoken for.
  | "exit_fast_indicator"
  | "exit_fast_period"
  | "exit_slow_indicator"
  | "exit_slow_period"
  // Direction is not published: Argus executes long only, so a frozen "bearish"
  // names which way two averages crossed and not a position taken.
  | "signal_period";

export type PublicReceiptStrategyFact = {
  key: PublicReceiptStrategyFactKey;
  value: string;
};

/**
 * Closed key set, same reason as the strategy facts: the run assumed these in the
 * author's language and the page speaks them in the viewer's. Values are bare
 * scalars, so numbers pick up the viewer's separators rather than the author's.
 */
export type PublicReceiptAssumptionKey =
  | "long_only"
  | "equal_weight"
  | "no_costs"
  | "modeled_fee_bps"
  | "modeled_slippage_bps"
  | "benchmark"
  | "benchmark_same_modeled_costs"
  | "recurring_contribution"
  | "contribution_cadence"
  | "starting_principal"
  | "fractional_shares";

export type PublicReceiptAssumption = {
  key: PublicReceiptAssumptionKey;
  value?: string | null;
};

/**
 * Closed key set, and no frozen label. The card's own `benchmark_delta` row is
 * absent because its value is an English sentence; the two keys below carry the
 * same comparison as numbers, read from the run's metrics, and the page composes
 * the sentence in the reader's language.
 *
 * Values are the run's display strings, except `delta_vs_benchmark_pct`, which is
 * a bare signed number because its unit is percentage points and that unit is a
 * word.
 */
export type PublicReceiptMetricKey =
  | "cash_value"
  | "total_return_pct"
  | "contribution_return_pct"
  | "max_drawdown_pct"
  | "win_rate"
  | "benchmark_return_pct"
  | "delta_vs_benchmark_pct";

export type PublicReceiptMetric = {
  key: PublicReceiptMetricKey;
  value: string;
};

export type PublicReceiptVisualPoint = {
  time: string;
  value: number;
};

export type PublicReceiptVisual = {
  kind: "portfolio_equity" | "value_path";
  currency?: string | null;
  base_value?: number | null;
  series: PublicReceiptVisualPoint[];
};

export type PublicReceiptPayload = {
  schema_version: 1;
  idea_title: string;
  asset_class?: AssetClass | null;
  symbols: string[];
  strategy_facts: PublicReceiptStrategyFact[];
  assumptions: PublicReceiptAssumption[];
  date_range: PublicReceiptDateRange;
  metrics: PublicReceiptMetric[];
  benchmark_symbol?: string | null;
  visual?: PublicReceiptVisual | null;
  owner_note?: string | null;
  content_language: "en" | "es-419";
  framing: "historical_simulation_not_advice";
  provenance_mark: "tested_with_argus";
};

export type PublicReceiptView = {
  public_id: string;
  status: "available" | "revoked";
  kind?: ReceiptKind | null;
  indexing: "noindex, nofollow";
  created_at?: string | null;
  payload?: PublicReceiptDocument | null;
};

export const PUBLIC_RECEIPT_PATH_PREFIX = "/r/";
export const PUBLIC_RECEIPT_MAX_ID_LENGTH = 64;

const PUBLIC_RECEIPT_ID_PATTERN = /^[A-Za-z0-9_-]{22,64}$/;

export function isPublicReceiptId(value: string): boolean {
  return PUBLIC_RECEIPT_ID_PATTERN.test(value);
}

export function publicReceiptPath(publicId: string): string {
  return `${PUBLIC_RECEIPT_PATH_PREFIX}${publicId}`;
}

/**
 * Three page states, not two. A revoked receipt is gone for good and says so; a
 * backend that cannot answer right now is a different, temporary thing, and
 * telling a viewer their link is dead when it is not would be a lie.
 */
export type PublicReceiptResult =
  | { kind: "available"; payload: PublicReceiptDocument; createdAt: string | null }
  | { kind: "revoked" }
  | { kind: "unavailable" };

/**
 * The only network call the public route makes. No credentials and no auth
 * header, so this request cannot carry an Argus session even by accident.
 *
 * Wrapped in `cache` at the call site so the metadata pass and the page render
 * share one read per request instead of asking the backend twice.
 */
export async function fetchPublicReceipt(
  publicId: string,
): Promise<PublicReceiptResult> {
  if (!isPublicReceiptId(publicId)) {
    return { kind: "revoked" };
  }
  try {
    const response = await fetch(
      `${CUADRAO_API_BASE_URL}/public/receipts/${encodeURIComponent(publicId)}`,
      {
        headers: { Accept: "application/json" },
        cache: "no-store",
      },
    );
    // Only the backend saying so makes a receipt revoked. An unknown id already
    // answers 200 with status "revoked", so a 404 here means the endpoint is not
    // there, which happens when sharing is enabled on this app and disabled on the
    // API. That is a deployment state, not a statement about this receipt, and
    // calling it revoked would be permanent-sounding and wrong.
    if (response.status === 410) {
      return { kind: "revoked" };
    }
    if (!response.ok) {
      return { kind: "unavailable" };
    }
    const view = (await response.json()) as PublicReceiptView;
    if (view.status === "revoked") {
      return { kind: "revoked" };
    }
    if (view.status !== "available" || !view.payload || !receiptDocumentSupported(view.payload)) {
      // A shape we do not recognise is not evidence that anything was revoked.
      return { kind: "unavailable" };
    }
    return {
      kind: "available",
      payload: view.payload,
      createdAt: view.created_at ?? null,
    };
  } catch {
    return { kind: "unavailable" };
  }
}

export function headlineReceiptMetric(
  payload: PublicReceiptPayload,
): PublicReceiptMetric | null {
  // A run freezes exactly one of these: total_return_pct for one-bankroll
  // templates, contribution_return_pct for recurring plans.
  const preferred: PublicReceiptMetricKey[] = [
    "total_return_pct",
    "contribution_return_pct",
  ];
  for (const key of preferred) {
    const match = payload.metrics.find((metric) => metric.key === key);
    if (match) return match;
  }
  return payload.metrics[0] ?? null;
}

/**
 * Request-scoped dedupe. `generateMetadata` and the page render both need the
 * receipt in the same request, and `no-store` means fetch will not dedupe them.
 */
export const readPublicReceipt = cache(fetchPublicReceipt);
