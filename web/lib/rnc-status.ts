import type { BusinessFact, ReviewFlag } from "./business-dossier";

export type RncStatus = "missing" | "invalid_length" | "check_digit" | "unverified";

/** Presence and length are read here. Whether the check digit matches is the dossier's `rnc_check_digit` flag alone. */
export function rncStatus(fact: BusinessFact<string> | null | undefined, flags: readonly ReviewFlag[]): RncStatus {
  if (fact?.state !== "known" || !fact.value.trim()) return "missing";
  if (flags.some((flag) => flag.code === "rnc_check_digit")) return "check_digit";
  const digits = fact.value.replace(/\D/g, "");
  return digits.length === 9 || digits.length === 11 ? "unverified" : "invalid_length";
}

export function formatRnc(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length === 9) return `${digits.slice(0, 1)}-${digits.slice(1, 3)}-${digits.slice(3, 8)}-${digits.slice(8)}`;
  if (digits.length === 11) return `${digits.slice(0, 3)}-${digits.slice(3, 10)}-${digits.slice(10)}`;
  return value;
}
