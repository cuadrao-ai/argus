import type { ReceiptStatus } from "@/lib/business-api";

export const BUSINESS_STATUS = {
  approved: { labelKey: "business.status.pill_approved", label: "Aprobado", ink: "#2f5a49", surface: "#e3ebe1" },
  pending: { labelKey: "business.status.pill_pending", label: "Pendiente", ink: "#735c14", surface: "#f2e8c9" },
  needs_attention: { labelKey: "business.status.pill_attention", label: "Necesita atención", ink: "#9e2f39", surface: "#f6dfe0" },
} as const;

export type BusinessStatusName = keyof typeof BUSINESS_STATUS;

export const CANVAS = "#F7F5EE";
export const LOADING_TRACK = "#7d8a84";
export const MUTED_TEXT = "#56635e";
export const CONFIRM_ACTION = "#9e2f39";
export const PLAIN_TOAST_MS = 3000;
export const UNDO_TOAST_MS = 8000;

export function statusNameForReceipt(status: ReceiptStatus): BusinessStatusName {
  if (status === "confirmed") return "approved";
  if (status === "needs_attention") return "needs_attention";
  return "pending";
}

function channel(hex: string, index: number): number {
  const value = Number.parseInt(hex.slice(1 + index * 2, 3 + index * 2), 16) / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 0) + 0.7152 * channel(hex, 1) + 0.0722 * channel(hex, 2);
}

export function contrastRatio(foreground: string, background: string): number {
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}
