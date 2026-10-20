"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { ChevronLeft, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import BottomSheet, { type SheetSnap } from "@/components/ui/BottomSheet";
import { useSheetStack } from "@/components/ui/sheetStack";

/**
 * The one sheet: for anything done while the page stays in view (a form, a
 * picker, a list, a record's details). Below the desktop stop it is a bottom
 * sheet that rests at its snap points. From the desktop stop it is a side
 * drawer on the right, between 320px and 40% of the screen, so the page stays
 * readable beside it. A full stop (delete, close a month) is not a sheet: it
 * is a ConfirmDialog.
 *
 * Owning the header matters as much as owning the shape. It is what lets a
 * child panel offer a back row instead of a close, so opening Appearance from
 * Preferences returns you to Preferences rather than dismissing everything.
 */

export type AdaptivePanelWidth = "sm" | "md" | "lg";

/** The drawer's preferred width; 40% of the screen caps it and 320px floors it. */
const DRAWER_WIDTH: Record<AdaptivePanelWidth, number> = { sm: 360, md: 420, lg: 560 };

export default function AdaptivePanel({
  title,
  summary,
  onClose,
  onBack,
  backLabel,
  closeLabel,
  dismissible = true,
  width = "sm",
  snaps = ["half", "full"],
  initialSnap,
  footer,
  returnFocusRef,
  initialFocusRef,
  children,
}: {
  title: string;
  /** One line under the title; on a phone it is what the peek snap shows. */
  summary?: string;
  onClose: () => void;
  /** Present on a child panel; returns to the parent instead of dismissing. */
  onBack?: () => void;
  backLabel?: string;
  closeLabel: string;
  dismissible?: boolean;
  width?: AdaptivePanelWidth;
  /** The bottom sheet's snap points on a phone. */
  snaps?: readonly SheetSnap[];
  initialSnap?: SheetSnap;
  footer?: ReactNode;
  /** Where focus lands on close when the opener has gone with the parent. */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  /**
   * Where focus lands on open, for a panel whose first job is typing.
   *
   * Both presentations otherwise start on the close control, so a panel that
   * marked a field `autoFocus` lost it: the attribute runs during commit and
   * the surface's own focus effect moves focus afterwards.
   */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const { isBelowDesktop } = useResponsiveLayout();
  const overlayId = useId();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const stackBackLabel = t("common.back", "Back");

  const back = onBack ? (
    <button
      type="button"
      onClick={onBack}
      className="flex min-h-11 w-full items-center gap-1.5 px-4 text-left text-[13px] text-[#56635e] transition-colors hover:text-black dark:text-white/70 dark:hover:text-white"
    >
      <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
      {backLabel}
    </button>
  ) : null;

  if (isBelowDesktop) {
    return (
      <BottomSheet
        isOpen
        onClose={onClose}
        dismissible={dismissible}
        title={title}
        description={summary}
        closeLabel={closeLabel}
        backLabel={stackBackLabel}
        snaps={snaps}
        initialSnap={initialSnap}
        footer={footer}
        initialFocusRef={initialFocusRef}
      >
        {back}
        {children}
      </BottomSheet>
    );
  }

  return <SideDrawer {...{ title, summary, titleId, overlayId, panelRef, onClose, closeLabel, stackBackLabel, dismissible, width, footer, returnFocusRef, initialFocusRef, back, children }} />;
}

/** While the drawer is drawn, the page gives up its width so it stays readable beside it. */
function useDrawerSpace(preferred: number, drawn: boolean) {
  useEffect(() => {
    if (!drawn) return undefined;
    const root = document.documentElement;
    const apply = () => root.style.setProperty("--cuadrao-drawer-space", `${Math.max(320, Math.min(preferred, window.innerWidth * 0.4))}px`);
    apply();
    window.addEventListener("resize", apply);
    return () => {
      window.removeEventListener("resize", apply);
      root.style.removeProperty("--cuadrao-drawer-space");
    };
  }, [preferred, drawn]);
}

function SideDrawerSurface({
  title,
  summary,
  titleId,
  overlayId,
  panelRef,
  onClose,
  closeLabel,
  stackBackLabel,
  dismissible,
  width,
  footer,
  returnFocusRef,
  initialFocusRef,
  back,
  children,
}: {
  title: string;
  summary?: string;
  titleId: string;
  overlayId: string;
  panelRef: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  closeLabel: string;
  stackBackLabel: string;
  dismissible: boolean;
  width: AdaptivePanelWidth;
  footer?: ReactNode;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  back: ReactNode;
  children: ReactNode;
}) {
  const { drawn, hasBelow } = useSheetStack(overlayId, true);
  useDrawerSpace(DRAWER_WIDTH[width], drawn);
  useModalSurface({
    isOpen: true,
    overlayId,
    containerRef: panelRef,
    onDismiss: onClose,
    canDismiss: () => dismissible,
    onEscape: dismissible ? onClose : () => {},
    returnFocusRef,
    initialFocusRef,
  });

  return (
    <div className="fixed inset-0 z-[70]" hidden={!drawn} data-sheet-stacked={hasBelow ? "true" : undefined}>
      {/* The page stays in view: no dimming, no blur. A click beside the drawer closes it. */}
      <button type="button" tabIndex={-1} className="absolute inset-0 cursor-default" onClick={dismissible ? onClose : undefined} aria-label={closeLabel} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="side-drawer"
        style={{ width: `min(${DRAWER_WIDTH[width]}px, 40vw)` }}
        className={`absolute inset-y-0 right-0 flex min-w-[320px] flex-col border-l border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1b1d20] ${hasBelow ? "" : "cuadrao-side-drawer-enter"}`}
      >
        <div className="flex shrink-0 items-start gap-2 border-b border-[#DCE0DA] px-5 py-4 dark:border-white/10">
          {hasBelow ? (
            <button
              type="button"
              onClick={onClose}
              aria-label={stackBackLabel}
              className="-ml-2 flex min-h-11 min-w-11 items-center justify-center rounded-full text-black/70 hover:bg-black/5 dark:text-white/70 dark:hover:bg-white/10"
            >
              <ChevronLeft className="h-5 w-5" aria-hidden="true" />
            </button>
          ) : null}
          <div className="min-w-0 flex-1 pt-2.5">
            <h2 id={titleId} className="font-display text-[17px] font-medium text-black dark:text-white">{title}</h2>
            {summary ? <p className="mt-1 text-[13px] text-[#56635e] dark:text-white/70">{summary}</p> : null}
          </div>
          {dismissible && !hasBelow ? (
            <button
              type="button"
              onClick={onClose}
              aria-label={closeLabel}
              className="flex min-h-11 min-w-11 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          ) : null}
        </div>
        {back}
        <div className="argus-thin-scrollbar min-h-0 flex-1 overflow-y-auto">
          {children}
        </div>
        {footer ? (
          <div className="shrink-0 border-t border-[#DCE0DA] px-5 py-3 dark:border-white/10">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const SideDrawer = withViewportPortal(SideDrawerSurface);
