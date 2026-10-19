import type { BusinessFact } from "./business-dossier";

export type RncStatus = "missing" | "invalid_length" | "unverified";

export function rncStatus(fact: BusinessFact<string> | null | undefined): RncStatus {
  if (fact?.state !== "known" || !fact.value.trim()) return "missing";
  const digits = fact.value.replace(/\D/g, "");
  return digits.length === 9 || digits.length === 11 ? "unverified" : "invalid_length";
}

export function formatRnc(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length === 9) return `${digits.slice(0, 1)}-${digits.slice(1, 3)}-${digits.slice(3, 8)}-${digits.slice(8)}`;
  if (digits.length === 11) return `${digits.slice(0, 3)}-${digits.slice(3, 10)}-${digits.slice(10)}`;
  return value;
}
