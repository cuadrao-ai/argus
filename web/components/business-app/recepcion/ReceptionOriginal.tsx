"use client";

import { useId, useRef, useState, type RefObject } from "react";
import { FileText, ImageIcon, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import BottomSheet from "@/components/ui/BottomSheet";
import { Tooltip } from "@/components/ui/Tooltip";
import ReceiptSourcePreview from "../ReceiptSourcePreview";
import styles from "../transacciones/records-annotations-preview.module.css";

function OriginalContent({ receipt, close }: { receipt: ReceiptSummary; close: () => void }) {
  return <div className={styles.content} onClick={event => { event.stopPropagation(); if ((event.target as HTMLElement).closest('[data-testid="receipt-see-email"],[data-testid="receipt-see-first-email"]')) close(); }}><ReceiptSourcePreview detail={receipt} initialExpanded /></div>;
}

const DesktopOriginal = withViewportPortal(function DesktopOriginal({ receipt, close, returnFocusRef }: { receipt: ReceiptSummary; close: () => void; returnFocusRef: RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  useModalSurface({ isOpen: true, overlayId: id, containerRef: panel, onDismiss: close, onOutsidePointerDown: close, initialFocusRef: closeButton, returnFocusRef });
  return <div className={styles.overlay} onClick={event => event.stopPropagation()}><div ref={panel} role="dialog" aria-modal="true" aria-labelledby={id} className={styles.dialog} style={{ width: "min(900px, 100%)" }}><header className={styles.header}><h2 id={id} className="min-w-0 break-all">{receipt.filename || t("business.review.source")}</h2><button ref={closeButton} type="button" className={styles.icon} onClick={close} aria-label={t("common.close")}><X size={18} aria-hidden="true" /></button></header><OriginalContent receipt={receipt} close={close} /></div></div>;
});

export default function ReceptionOriginal({ receipt, onOpen }: { receipt: ReceiptSummary; onOpen: () => void }) {
  const { t } = useTranslation();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const name = receipt.filename || t("business.review.source");
  const Icon = receipt.media_type.startsWith("image/") ? ImageIcon : FileText;
  const close = () => setOpen(false);
  return <>
    <Tooltip content={name} side="top"><button ref={trigger} type="button" className={styles.icon} data-testid="reception-original" title={name} aria-label={t("business.reception_preview.open_file", { name })} aria-haspopup="dialog" onClick={() => { onOpen(); setOpen(true); }}><Icon size={18} aria-hidden="true" /></button></Tooltip>
    {open ? phone ? <BottomSheet isOpen onClose={close} title={name} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen><OriginalContent receipt={receipt} close={close} /></BottomSheet> : <DesktopOriginal receipt={receipt} close={close} returnFocusRef={trigger} /> : null}
  </>;
}
