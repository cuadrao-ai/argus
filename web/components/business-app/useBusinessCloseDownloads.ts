"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchBusinessExport } from "@/lib/business-api";
import type { OwnedBusiness } from "@/lib/business-lifecycle-api";
import { saveBlobDownload } from "@/lib/save-blob-download";
import { showToast } from "./foundation/toasts";

export type CloseDownloadStatus = "idle" | "loading" | "downloaded" | "failed";
/** One server export period and how far its download got in this visit. */
export type CloseDownload = OwnedBusiness["export_windows"][number] & { key: string; status: CloseDownloadStatus };
export type CloseDownloads = {
  items: CloseDownload[];
  /** Downloads one period, or in order every period not downloaded yet. One run at a time. */
  start: (key?: string) => void;
};

/** The handover downloads of a Business about to close: the server's periods, one ZIP each. */
export function useBusinessCloseDownloads(business: OwnedBusiness): CloseDownloads {
  const { t } = useTranslation();
  const [statuses, setStatuses] = useState<Record<string, CloseDownloadStatus>>({});
  const request = useRef<AbortController | null>(null);
  // Leaving cancels the file in flight: nothing downloads after the dialog is gone.
  useEffect(() => () => request.current?.abort(), []);

  const items = business.export_windows.map((period) => {
    const key = `${period.start}/${period.end}`;
    return { ...period, key, status: statuses[key] ?? "idle" };
  });

  const start = async (only?: string) => {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    const mark = (key: string, status: CloseDownloadStatus) => setStatuses((current) => ({ ...current, [key]: status }));
    const saved: { blob: Blob; filename: string }[] = [];
    try {
      for (const item of items.filter((candidate) => (only ? candidate.key === only : candidate.status !== "downloaded"))) {
        mark(item.key, "loading");
        try {
          const blob = await fetchBusinessExport(item.start, item.end, controller.signal, business.grant_id);
          controller.signal.throwIfAborted();
          const filename = `business-export-${item.start}-${item.end}.zip`;
          saveBlobDownload(blob, filename);
          saved.push({ blob, filename });
          mark(item.key, "downloaded");
        } catch {
          if (!controller.signal.aborted) mark(item.key, "failed");
          return;
        }
      }
      // The same toast as Exportar registros: the same bytes again, never a second request.
      if (saved.length) showToast({ kind: "success", text: t("business.transactions.reporting.export.done"), action: { label: t("business.transactions.reporting.export.download_again"), run: () => saved.forEach((file) => saveBlobDownload(file.blob, file.filename)) } });
    } finally {
      if (request.current === controller) request.current = null;
    }
  };

  return { items, start: (key) => { void start(key); } };
}
