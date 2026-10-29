import { CUADRAO_API_BASE_URL } from "./argus-api-transport";
import type { ReceiptKind } from "./public-receipt-turns";

/** The viewer-side funnel stages. Neither carries an identifier. */
export type ReceiptFunnelStage = "viewed" | "try_argus";

/**
 * Fire and forget. Analytics never blocks or breaks the page a stranger opened,
 * and a failed beacon is simply an uncounted stage.
 */
export function reportReceiptFunnelStage(stage: ReceiptFunnelStage, kind: ReceiptKind = "backtest"): void {
  const url = `${CUADRAO_API_BASE_URL}/public/receipt-funnel`;
  const body = JSON.stringify({ stage, kind });
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
      return;
    }
    void fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => null);
  } catch {
    // Nothing to recover: a missing event is better than a broken page.
  }
}
