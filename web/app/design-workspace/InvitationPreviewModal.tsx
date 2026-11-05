"use client";

import { useCallback, useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { focusableWithin, nextFocusIndex } from "@/components/layout/overlayFocus";
import { withViewportPortal } from "@/components/ui/withViewportPortal";

type InvitationProps = {
  children: ReactNode;
  frame: RefObject<HTMLIFrameElement | null>;
  onClose: () => void;
};

function DesktopInvitationModal({ children, frame, onClose }: {
  children: ReactNode;
  frame: RefObject<HTMLIFrameElement | null>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const handleKey = useCallback((event: KeyboardEvent) => {
    if (event.key === "Escape") {
      const picker = panel.current?.querySelector("iframe")?.contentDocument?.querySelector<HTMLElement>('.picker-trigger[aria-expanded="true"]');
      if (picker) { event.preventDefault(); event.stopPropagation(); picker.click(); return; }
      event.preventDefault(); onClose(); return;
    }
    if (event.key !== "Tab") return;
    // The preview form is a separate document, so its tab order spans both roots.
    const iframe = panel.current?.querySelector("iframe");
    const doc = iframe?.contentDocument;
    const expanded = doc?.querySelector<HTMLElement>('.picker-trigger[aria-expanded="true"]');
    if (expanded) expanded.click();
    const controls = [close.current, ...focusableWithin(doc?.body ?? null)].filter((node): node is HTMLElement => Boolean(node));
    const active = document.activeElement === iframe ? doc?.activeElement : document.activeElement;
    event.preventDefault();
    controls[nextFocusIndex({ count: controls.length, currentIndex: controls.indexOf(active as HTMLElement), direction: event.shiftKey ? "focus-previous" : "focus-next" })]?.focus();
  }, [onClose]);
  useModalSurface({ isOpen: true, overlayId: id, containerRef: panel,
    onDismiss: onClose, trapFocus: false, onKeyDown: handleKey });
  useEffect(() => {
    const iframe = frame.current;
    let doc: Document | null = null;
    const connect = (focus = false) => {
      doc?.removeEventListener("keydown", handleKey, true);
      doc = iframe?.contentDocument ?? null;
      doc?.addEventListener("keydown", handleKey, true);
      if (focus) doc?.querySelector<HTMLInputElement>('[data-recipient-email]:not([disabled])')?.focus();
    };
    const onLoad = () => connect(true);
    iframe?.addEventListener("load", onLoad);
    connect();
    return () => { iframe?.removeEventListener("load", onLoad); doc?.removeEventListener("keydown", handleKey, true); };
  }, [frame, handleKey]);
  return <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
    <button type="button" tabIndex={-1} aria-label={t("common.close")} className="absolute inset-0" onClick={onClose} />
    <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={id}
      data-invitation-modal
      style={{ maxWidth: 600, maxHeight: "calc(100dvh - 2rem)" }}
      className="relative max-h-[calc(100dvh-2rem)] w-full max-w-[600px] overflow-y-auto overscroll-contain rounded-[20px] border border-black/10 bg-white p-5 text-[#172b26] sm:p-7 dark:border-white/10 dark:bg-[#151719] dark:text-white">
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 44px" }} className="mb-0 items-start gap-2">
        <h2 id={id} className="font-display pt-1 text-left text-[24px] font-medium tracking-tight">{t("workspace_setup_preview.batch_title")}</h2>
        <button ref={close} type="button" aria-label={t("common.close")} onClick={onClose}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#56635e] hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-offset-2 dark:text-white/70 dark:hover:bg-white/5"><X className="h-5 w-5" aria-hidden="true" /></button>
      </div>
      {children}
    </div>
  </div>;
}

const DesktopModal = withViewportPortal(DesktopInvitationModal);

export default function InvitationPreviewModal(props: InvitationProps) {
  const { isBelowDesktop } = useResponsiveLayout();
  const { t } = useTranslation();
  if (isBelowDesktop) return <BottomSheet isOpen onClose={props.onClose}
    title={t("workspace_setup_preview.batch_title")} closeLabel={t("common.close")} backLabel={t("common.back")}
    snaps={["full"]} initialSnap="full">
    <div data-invitation-modal className="bg-white px-0 pb-5 pt-3 dark:bg-[#1f2225]">{props.children}</div>
  </BottomSheet>;
  return <DesktopModal {...props} />;
}
