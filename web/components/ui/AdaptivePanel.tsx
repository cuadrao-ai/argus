"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useId, useRef, type ReactNode } from "react";
import { ChevronLeft, X } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import BottomSheet from "@/components/ui/BottomSheet";

/**
 * One panel, two presentations, one rule about which.
 *
 * Below the desktop stop a panel is a bottom sheet. Above it, the centred
 * dialog it has always been. The rule lives here rather than in each surface,
 * because it was in each surface before: twelve dialogs drew the same centred
 * card at 390px as at 1440px, and the three that did adapt disagreed about the
 * width to adapt at.
 *
 * Owning the header matters as much as owning the shape. It is what lets a
 * child panel offer a back row instead of a close, so opening Appearance from
 * Preferences returns you to Preferences rather than dismissing everything.
 * It also means one backdrop and one close control exist in the codebase
 * rather than a dozen near-copies.
 */

export type AdaptivePanelWidth = "sm" | "md" | "lg";

const DESKTOP_WIDTH: Record<AdaptivePanelWidth, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-[600px]",
};

export default function AdaptivePanel({
  title,
  onClose,
  onBack,
  backLabel,
  closeLabel,
  dismissible = true,
  width = "sm",
  desktopMaxHeight = "max-h-[85vh]",
  footer,
  returnFocusRef,
  initialFocusRef,
  children,
}: {
  title: string;
  onClose: () => void;
  /** Present on a child panel; returns to the parent instead of dismissing. */
  onBack?: () => void;
  backLabel?: string;
  closeLabel: string;
  dismissible?: boolean;
  width?: AdaptivePanelWidth;
  desktopMaxHeight?: string;
  footer?: ReactNode;
  /** Where focus lands on close when the opener has gone with the parent. */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  /**
   * Where focus lands on open, for a panel whose first job is typing.
   *
   * Both presentations otherwise start on the close control, so a panel that
   * marked a field `autoFocus` lost it: the attribute runs during commit and
   * the surface's own focus effect moves focus afterwards. The visible cost was
   * a search box that could not be typed into, where Enter closed the panel
   * instead of searching.
   */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const { isBelowDesktop } = useResponsiveLayout();
  const overlayId = useId();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  const back = onBack ? (
    <button
      type="button"
      onClick={onBack}
      className="flex min-h-11 w-full items-center gap-1.5 px-4 text-left text-[12px] text-black/45 transition-colors hover:text-black dark:text-white/45 dark:hover:text-white"
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
        closeLabel={closeLabel}
        height="auto"
        footer={footer}
        initialFocusRef={initialFocusRef}
      >
        {back}
        {children}
      </BottomSheet>
    );
  }

  return <DesktopDialog {...{ title, titleId, overlayId, panelRef, onClose, closeLabel, dismissible, width, desktopMaxHeight, footer, returnFocusRef, initialFocusRef, back, children }} />;
}

function DesktopDialogSurface({
  title,
  titleId,
  overlayId,
  panelRef,
  onClose,
  closeLabel,
  dismissible,
  width,
  desktopMaxHeight,
  footer,
  returnFocusRef,
  initialFocusRef,
  back,
  children,
}: {
  title: string;
  titleId: string;
  overlayId: string;
  panelRef: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  closeLabel: string;
  dismissible: boolean;
  width: AdaptivePanelWidth;
  desktopMaxHeight: string;
  footer?: ReactNode;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  back: ReactNode;
  children: ReactNode;
}) {
  useModalSurface({
    isOpen: true,
    overlayId,
    // The panel, not the wrapper: the wrapper's first focusable child is the
    // backdrop, which is a pointer affordance and never a tab stop.
    containerRef: panelRef,
    onDismiss: onClose,
    canDismiss: () => dismissible,
    onEscape: dismissible ? onClose : () => {},
    returnFocusRef,
    initialFocusRef,
  });

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/25 p-4 backdrop-blur-sm dark:bg-black/60">
      <button
        type="button"
        tabIndex={-1}
        className="absolute inset-0"
        onClick={dismissible ? onClose : undefined}
        aria-label={closeLabel}
      />
      <div
        ref={panelRef}
        className={`relative flex w-full ${DESKTOP_WIDTH[width]} ${desktopMaxHeight} flex-col overflow-hidden rounded-[18px] border border-black/5 bg-white dark:border-white/10 dark:bg-[#1b1d20]`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-black/5 px-5 py-4 dark:border-white/5">
          <h2
            id={titleId}
            className="text-[16px] font-medium text-black dark:text-white"
          >
            {title}
          </h2>
          {dismissible ? <button
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-full text-black/45 transition-colors hover:bg-black/5 hover:text-black dark:text-white/45 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X className="h-4 w-4" />
          </button> : null}
        </div>
        {back}
        <div className="argus-thin-scrollbar min-h-0 flex-1 overflow-y-auto">
          {children}
        </div>
        {footer ? (
          <div className="shrink-0 border-t border-black/5 px-5 py-3 dark:border-white/5">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const DesktopDialog = withViewportPortal(DesktopDialogSurface);
