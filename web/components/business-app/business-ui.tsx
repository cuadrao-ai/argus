"use client";

import { useContext, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { personName, type PersonName } from "@/lib/person-name";
import { BusinessContext } from "./BusinessWorkspace";
import { FOCUS_RING } from "./foundation/presentation";

export const cardClass =
  "rounded-surface border border-black/[0.06] bg-white p-5 dark:border-white/[0.06] dark:bg-[#1f2225]";
/**
 * The one owner of button looks (Lucas, October 21, 2026). Four levels, never a fifth:
 * primary is the screen's one main action in Cuadrao green; secondary is an outlined
 * alternative such as Listo or Volver; quiet is a green text action inside content;
 * danger is the red confirm of a delete. All are fully round with a 44px target.
 * Secondary and both reds darken while pressed (#1495, Ajustes · Cuenta estados).
 */
export const pillButtonClass =
  `inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-[16px] font-medium transition-[opacity,background-color] hover:opacity-90 ${FOCUS_RING} disabled:opacity-40`;

export const primaryButtonClass = `${pillButtonClass} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`;
export const secondaryButtonClass = `${pillButtonClass} border border-[#7d8a84]/60 bg-white text-[#172b26] hover:bg-[#F7F5EE] hover:opacity-100 active:bg-[#EFEDE6] dark:border-white/20 dark:bg-[#1f2225] dark:text-white dark:hover:bg-white/[0.06] dark:active:bg-white/10`;
export const quietButtonClass = `inline-flex min-h-11 items-center gap-1.5 rounded-full px-1 text-[16px] font-medium text-[var(--cuadrao-green)] underline-offset-4 hover:underline ${FOCUS_RING} disabled:opacity-40`;
export const trashButtonClass = "flex h-11 w-11 shrink-0 items-center justify-center rounded-item text-black/55 hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 dark:text-white/65 dark:hover:bg-white/5";
/** A destructive action: red, and always behind a confirmation. */
export const dangerButtonClass = `${pillButtonClass} border border-[#9e2f39]/40 bg-white text-[#9e2f39] active:bg-[#9e2f39]/[0.08] active:opacity-100 dark:border-[#ec9aa0]/40 dark:bg-[#1f2225] dark:text-[#ec9aa0] dark:active:bg-[#ec9aa0]/[0.12]`;
export const dangerConfirmButtonClass = `${pillButtonClass} bg-[#9e2f39] text-white active:bg-[#85262f] active:opacity-100 dark:bg-[#ec9aa0] dark:text-[#172b26] dark:active:bg-[#e0868d]`;

export function PanelHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">{title}</h2>
        {subtitle ? <p className="mt-1 text-[14px] text-black/55 dark:text-white/55">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function useCategoryLabel() {
  const { t } = useTranslation();
  return (id: string | null) =>
    id
      ? t(`business.category.${id}`, {
          defaultValue: {
            other: "Other",
            groceries: "Groceries",
            dining: "Dining",
            transport: "Transport",
            housing: "Housing",
            health: "Health",
            shopping: "Shopping",
            interest_fees: "Interest and fees",
          }[id] ?? id,
        })
      : t("business.category.none", "No category");
}

export function LoadingRows({ rows = 3, layout = "rows" }: { rows?: number; layout?: "rows" | "overview" }) {
  const { t } = useTranslation();
  const line = "rounded-mark bg-black/[0.06] dark:bg-white/[0.08]";
  const pulse = "animate-pulse motion-reduce:animate-none";
  const fields = Array.from({ length: rows }, (_, index) => (
    <div key={index} className={layout === "overview" ? `${cardClass} min-h-40 space-y-4` : "flex min-h-20 items-center gap-3 px-3 py-3"}>
      {layout === "rows" ? <div className={`${line} h-11 w-11 shrink-0 rounded-item`} /> : null}
      <div className="min-w-0 flex-1 space-y-3">
        <div className={`${line} h-3 w-2/5`} />
        <div className={`${line} ${layout === "overview" ? "h-7 w-3/5" : "h-4 w-3/4"}`} />
      </div>
      {layout === "rows" ? <div className={`${line} h-4 w-16 shrink-0`} /> : null}
    </div>
  ));
  return (
    <div role="status" aria-label={t("common.loading", "Loading")} data-testid="business-loading" data-layout={layout}>
      <div aria-hidden="true" className={pulse}>
        <div className={layout === "overview" ? "grid gap-3 tablet:grid-cols-2" : `${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>{fields}</div>
      </div>
    </div>
  );
}

/** Where a source arrived from, by its channel; WhatsApp keeps its name, the rest have a word. */
export function useChannelLabel() {
  const { t } = useTranslation();
  return (channel: "web" | "whatsapp" | "email" | string) =>
    channel === "whatsapp" ? "WhatsApp" : channel === "email" ? t("business.dossier.email", "Email") : t("business.dossier.web", "Web upload");
}

/** The person may add receipts and notes to the Business they are in: the server's prepare capability, the owner's included. */
export function canAddRecords(chosen: { capabilities: readonly string[] } | null | undefined): boolean {
  return Boolean(chosen?.capabilities.includes("prepare"));
}

/** Who may configure the Business (its name, details, access, reception and setup): the server's `manage` permission. */
export function canManageBusiness(chosen: { permissions?: readonly string[] } | null | undefined): boolean {
  return Boolean(chosen?.permissions?.includes("manage"));
}

/** The owner is looking: their own Business, not a client's opened through a grant. */
export function useOwnerView(): boolean {
  const business = useContext(BusinessContext);
  return !business?.chosen || business.chosen.role === "owner";
}

/**
 * The marks a record carries, as text in a muted chip, never colour alone:
 * "Personal" when a person marked it as no part of the Business; "Sin
 * comprobante" when it is stated to have none, out of the 606 and 607.
 * When someone other than the owner marked it Personal, the owner sees a small
 * dot on the chip that reads "Marcado por <nombre>". A missing NCF is not a
 * mark: Estado says it.
 */
export function recordFiscalMark(record: { sin_comprobante?: boolean }): "sin_comprobante" | null {
  return record.sin_comprobante ? "sin_comprobante" : null;
}

export function RecordMarks({ personal, fiscal, markedBy = null, className = "" }: { personal?: boolean; fiscal: ReturnType<typeof recordFiscalMark>; markedBy?: PersonName | null; className?: string }) {
  const { t } = useTranslation();
  const owner = useOwnerView();
  const chip = "inline-flex min-h-6 items-center whitespace-nowrap rounded-mark border px-2 text-[11px] font-medium";
  if (!personal && !fiscal) return null;
  const marker = personal && owner && markedBy ? t("business.marks.marked_by", "Marked by {{name}}", { name: personName(t, markedBy) }) : null;
  return (
    <span className={`flex flex-wrap items-center gap-1.5 ${className}`} data-testid="record-marks">
      {personal ? (
        <span data-mark="personal" title={marker ?? undefined} className={`${chip} gap-1 border-[var(--cuadrao-green)]/35 text-[var(--cuadrao-green)]`}>
          {t("business.marks.personal_chip", "Personal")}
          {marker ? <><span data-testid="personal-marked-dot" aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--cuadrao-green)]" /><span className="sr-only">{marker}</span></> : null}
        </span>
      ) : null}
      {fiscal ? <span data-mark="sin_comprobante" className={`${chip} border-black/15 text-black/55 dark:border-white/15 dark:text-white/55`}>{t("business.marks.sin_comprobante_chip", "No comprobante")}</span> : null}
    </span>
  );
}

/** A short announcement with one way back, for a change the person can undo. */
