import { useEffect, useState } from "react";
import type { BusinessAmountsPreview, BusinessAmountsPreviewInput } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessDataSource } from "./business-data";
import type { useReviewRows } from "./receipt-review-save";

export function useAmountsPreview(dossier: BusinessDossier | null, rows: ReturnType<typeof useReviewRows>["rows"], preview: BusinessDataSource["previewAmounts"]) {
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
  const fields = Object.keys(input).join(",");
  const serialized = JSON.stringify(input);
  const active = Object.keys(input).length > 0;
  const key = `${dossier?.draft_id}:${dossier?.version}:${invalid}:${serialized}`;
  const [result, setResult] = useState<{ key: string; draftId: string; version: number; fields: string; value: BusinessAmountsPreview } | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const id = dossier?.draft_id;
  const version = dossier?.version;
  if (!active && result !== null) setResult(null);
  if (!active && failedKey !== null) setFailedKey(null);
  useEffect(() => {
    if (!preview || !id || !version || !active || invalid) return;
    let current = true;
    const timer = setTimeout(() => {
      void preview(id, version, JSON.parse(serialized)).then((value) => { if (current) setResult({ key, draftId: id, version, fields, value }); }).catch(() => { if (current) setFailedKey(key); });
    }, 120);
    return () => { current = false; clearTimeout(timer); };
  }, [preview, id, version, active, invalid, serialized, key, fields]);
  if (!active) return undefined;
  const mismatch = dossier?.review_flags?.find((flag) => flag.code === "amounts_mismatch");
  const value: BusinessAmountsPreview = result !== null && result.draftId === id && result.version === version && result.fields === fields ? result.value : {
    net_amount: dossier?.net_amount ?? { amount: null, source: null },
    mismatch: mismatch?.difference != null ? { code: "amounts_mismatch", difference: mismatch.difference } : null,
  };
  return { ...value, status: result?.key === key ? "ready" as const : failedKey === key ? "error" as const : "pending" as const };
}
