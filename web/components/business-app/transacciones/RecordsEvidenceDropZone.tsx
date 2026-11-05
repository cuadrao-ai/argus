"use client";

import { useEffect, useRef, useState } from "react";
import { FileUp, FolderOpen } from "lucide-react";
import type { ReceiptLimits } from "@/lib/business-api";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { primaryButtonClass } from "../business-ui";
import { receiptFileAccept, receiptFormatLabels } from "../receipt-file";
import { useInputCapabilities } from "../useInputCapabilities";
import { useTransaccionesWords } from "./transacciones-words";

export default function RecordsEvidenceDropZone({ limits, busy, onFiles }: { limits: ReceiptLimits; busy: boolean; onFiles: (files: File[]) => void }) {
  const { t, locale } = useTransaccionesWords();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const capabilities = useInputCapabilities();
  const field = useRef<HTMLInputElement>(null);
  const zone = useRef<HTMLDivElement>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const desktopDrop = capabilities.dragAndDrop && !phone;
  const formats = receiptFormatLabels(limits).join(", ");
  const size = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(limits.max_bytes / 1024 / 1024);
  const pasteKeys = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘V" : "Ctrl+V";
  useEffect(() => {
    const paste = (event: ClipboardEvent) => {
      if (busy || !zone.current?.closest('[role="dialog"]')?.contains(event.target as Node)) return;
      const files = Array.from(event.clipboardData?.files ?? []);
      if (!files.length) return;
      event.preventDefault();
      onFiles(files);
    };
    window.addEventListener("paste", paste);
    return () => window.removeEventListener("paste", paste);
  }, [busy, onFiles]);
  return <div ref={zone} data-testid="records-evidence-drop-zone" data-drag={dragging ? "accept" : "idle"}
    onDragEnter={(event) => { event.preventDefault(); if (!busy) { depth.current++; setDragging(true); } }}
    onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = busy ? "none" : "copy"; }}
    onDragLeave={() => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDragging(false); }}
    onDrop={(event) => { event.preventDefault(); depth.current = 0; setDragging(false); if (!busy) onFiles(Array.from(event.dataTransfer.files)); }}
    className={`mt-3 rounded-item px-5 py-6 text-center transition-colors motion-reduce:transition-none ${dragging ? "border border-solid border-[#2f5a49] bg-[#e3ebe1] ring-4 ring-[#2f5a49]/15 dark:border-[#8fcbb0] dark:bg-[#8fcbb0]/10" : "border border-dashed border-[#7d8a84] bg-[#FFFEFA] dark:border-white/30 dark:bg-white/[0.02]"}`}>
    <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-item bg-[#2f5a49]/10 text-[#2f5a49] dark:text-[#8fcbb0]"><FileUp size={28} aria-hidden="true" /></span>
    <p role={dragging ? "status" : undefined} className="mt-4 font-display text-[18px] font-medium leading-6">{t(`business.transactions.layout.annotations.${dragging ? "drop_release" : desktopDrop ? "drop_title" : "choose_file"}`)}</p>
    <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.intake.formats_short", { formats, size })}</p>
    <button type="button" className={`${primaryButtonClass} mt-5`} disabled={busy} onClick={() => field.current?.click()}><FolderOpen size={16} aria-hidden="true" />{t("business.intake.choose_multiple")}</button>
    {desktopDrop ? <p className="mt-3 text-[14px] text-[#56635e] dark:text-white/70">{t("business.intake.paste_hint", { keys: pasteKeys })}</p> : null}
    <input ref={field} hidden type="file" multiple disabled={busy} accept={receiptFileAccept(limits)} onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; onFiles(files); }} />
  </div>;
}
