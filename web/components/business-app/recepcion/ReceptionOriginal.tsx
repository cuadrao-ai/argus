"use client";

import { useRef, useState, type RefObject } from "react";
import { FileText, ImageIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import BottomSheet from "@/components/ui/BottomSheet";
import { Tooltip } from "@/components/ui/Tooltip";
import ReceiptSourcePreview from "../ReceiptSourcePreview";

function OriginalContent({ receipt, close }: { receipt: ReceiptSummary; close: () => void }) {
  return <div className="px-6 pb-6 pt-3" onClick={event => { if ((event.target as HTMLElement).closest('[data-testid="receipt-see-email"],[data-testid="receipt-see-first-email"]')) close(); }}><ReceiptSourcePreview detail={receipt} initialExpanded /></div>;
}

function DesktopOriginal({ receipt, close, returnFocusRef }: { receipt: ReceiptSummary; close: () => void; returnFocusRef: RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  return <AdaptivePanel titleClassName="break-all" title={receipt.filename || t("business.document_delete.unnamed")} closeLabel={t("common.close")} onClose={close} width="lg" returnFocusRef={returnFocusRef}><OriginalContent receipt={receipt} close={close} /></AdaptivePanel>;
}

export default function ReceptionOriginal({ receipt }: { receipt: ReceiptSummary }) {
  const { t } = useTranslation();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const name = receipt.filename || t("business.document_delete.unnamed");
  const Icon = receipt.media_type.startsWith("image/") ? ImageIcon : FileText;
  const close = () => setOpen(false);
  return <>
    <Tooltip content={name} side="top"><button ref={trigger} type="button" className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-black/60 hover:bg-black/[0.06] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/60 dark:hover:bg-white/[0.06]" data-testid="reception-original" aria-label={t("business.reception_preview.open_file", { name })} aria-haspopup="dialog" onClick={() => setOpen(true)}><Icon size={18} aria-hidden="true" /></button></Tooltip>
    {/* The sheet is portalled but React carries its clicks up through the row, which would open the record behind it. */}
    {open ? <span onClick={event => event.stopPropagation()}>{phone ? <BottomSheet isOpen onClose={close} title={name} closeLabel={t("common.close")} snaps={["full"]} initialSnap="full" fullScreen><OriginalContent receipt={receipt} close={close} /></BottomSheet> : <DesktopOriginal receipt={receipt} close={close} returnFocusRef={trigger} />}</span> : null}
  </>;
}
