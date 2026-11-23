import { useEffect, useState } from "react";
import type { BusinessAmountsPreview, BusinessAmountsPreviewInput } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessDataSource } from "./business-data";
import type { useReviewRows } from "./receipt-review-save";

export function useAmountsPreview(dossier: BusinessDossier | null, rows: ReturnType<typeof useReviewRows>["rows"], ask: BusinessDataSource["previewAmounts"]) {
  const input: BusinessAmountsPreviewInput = {};
  let invalid = false;
  for (const field of ["amount", "itbis", "net_amount", "legal_tip"] as const) {
    const edit = rows[field]?.edit;
    if (!edit) continue;
    invalid ||= edit.invalid;
    const change = edit.change;
    if (field === "itbis" && change.write === "fiscal") input.itbis = change.fiscal.itbis != null ? { state: "known", value: change.fiscal.itbis } : { state: "unknown", value: null };
    else if (field === "amount" && change.write === "facts") {
      const fact = change.facts.amount;
      if (fact) input.amount = fact.state === "known" ? fact : { state: "unknown", value: null };
    } else if ((field === "net_amount" || field === "legal_tip") && change.write === "montos") {
      const fact = change.montos[field];
      if (fact) input[field] = fact.state === "known" ? fact : { state: "unknown", value: null };
    }
  }
  const active = Object.keys(input).length > 0;
  const preview = usePreview(ask, dossier, active ? input : null, invalid);
  if (!active) return undefined;
  // Until the server answers this draft, the saved record's own check stands.
  const saved = dossier?.amounts_check;
  const value: Pick<BusinessAmountsPreview, "net_amount" | "mismatch"> = preview.current ?? {
    net_amount: dossier?.net_amount ?? { amount: null, source: null },
    mismatch: saved?.state === "difference" ? { code: "amounts_mismatch", difference: saved.difference } : null,
  };
  return { ...value, status: preview.status };
}

export const PREVIEW_DELAY_MS = 120;
/**
 * The server's preview of a draft, asked once typing settles. `current` is its
 * answer to this exact draft. `last` is the newest answer to land: it stays
 * while a newer one is on the way and goes when there is no draft. `hold`
 * keeps a draft that cannot be sent from asking.
 */
export function usePreview(ask: BusinessDataSource["previewAmounts"], dossier: Pick<BusinessDossier, "draft_id" | "version"> | null, draft: BusinessAmountsPreviewInput | null, hold = false) {
  const serialized = draft === null ? null : JSON.stringify(draft);
  const id = dossier?.draft_id;
  const version = dossier?.version;
  const key = `${id}:${version}:${hold}:${serialized}`;
  const [result, setResult] = useState<{ key: string; value: BusinessAmountsPreview } | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  if (serialized === null && result !== null) setResult(null);
  if (serialized === null && failedKey !== null) setFailedKey(null);
  useEffect(() => {
    if (!ask || !id || !version || serialized === null || hold) return;
    let current = true;
    const timer = setTimeout(() => {
      void ask(id, version, JSON.parse(serialized)).then((value) => { if (current) setResult({ key, value }); }).catch(() => { if (current) setFailedKey(key); });
    }, PREVIEW_DELAY_MS);
    return () => { current = false; clearTimeout(timer); };
  }, [ask, id, version, serialized, hold, key]);
  const current = result?.key === key ? result.value : undefined;
  return { current, last: result?.value, status: current ? "ready" as const : failedKey === key ? "error" as const : "pending" as const };
}
