"use client";

import Image from "next/image";
import { useState } from "react";
import { ZoomIn, ZoomOut } from "lucide-react";
import { useTranslation } from "react-i18next";

const LEVELS = [1, 1.5, 2, 3] as const;
const CONTROL_CLASS = "flex h-11 w-11 items-center justify-center rounded-full text-[#172b26] hover:bg-black/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] disabled:opacity-40 dark:text-white dark:hover:bg-white/[0.06]";

/** The original as an image a person can read closely: it grows inside its well, which scrolls. */
export default function ReceiptImageZoom({ src, alt }: { src: string; alt: string }) {
  const { t } = useTranslation();
  const [level, setLevel] = useState(0);
  const zoom = LEVELS[level];
  return (
    <div className="relative w-full">
      <div data-testid="receipt-image-zoom" data-zoom={zoom} tabIndex={zoom > 1 ? 0 : undefined} className={`max-h-[520px] overflow-auto ${zoom > 1 ? "" : "flex justify-center"}`}>
        <Image unoptimized src={src} width={640} height={900} alt={alt} style={zoom > 1 ? { width: `${zoom * 100}%`, height: "auto", maxWidth: "none", maxHeight: "none" } : undefined} className="max-h-[300px] w-auto object-contain desktop:max-h-[520px]" />
      </div>
      <div className="absolute bottom-2 right-2 flex items-center rounded-full border border-[#DCE0DA] bg-[#FFFEFA] dark:border-white/10 dark:bg-[#1f2225]">
        <button type="button" className={CONTROL_CLASS} aria-label={t("business.dossier.placeholder.zoom_out", "Zoom out")} disabled={level === 0} onClick={() => setLevel(level - 1)}><ZoomOut className="h-[18px] w-[18px]" aria-hidden="true" /></button>
        <span aria-live="polite" className="min-w-10 text-center text-[13px] tabular-nums text-[#56635e] dark:text-white/70">{zoom * 100}%</span>
        <button type="button" className={CONTROL_CLASS} aria-label={t("business.dossier.placeholder.zoom_in", "Zoom in")} disabled={level === LEVELS.length - 1} onClick={() => setLevel(level + 1)}><ZoomIn className="h-[18px] w-[18px]" aria-hidden="true" /></button>
      </div>
    </div>
  );
}
