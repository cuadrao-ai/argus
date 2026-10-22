"use client";

import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { fetchBusinessExport } from "@/lib/business-api";
import type { OwnedBusiness } from "@/lib/business-lifecycle-api";
import { saveBlobDownload } from "./ExportRecordsPanel";
import { primaryButtonClass } from "./business-ui";

type ExportState = "idle" | "loading" | "failed" | "complete";
export type BusinessCloseExportJournal = { nextWindow: number; state: ExportState };

export default function BusinessCloseExport({ business, label, journal, setJournal }: { business: OwnedBusiness; label: string; journal: BusinessCloseExportJournal; setJournal: Dispatch<SetStateAction<BusinessCloseExportJournal>> }) {
  const { t } = useTranslation();
  const state = journal.state;
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => {
    request.current?.abort();
    setJournal(current => current.state === "loading" ? { ...current, state: "idle" } : current);
  }, [setJournal]);

  const download = async () => {
    if (request.current || !business.export_windows.length || state === "complete") return;
    const controller = new AbortController();
    request.current = controller;
    let nextWindow = journal.nextWindow;
    setJournal({ nextWindow, state: "loading" });
    try {
      while (nextWindow < business.export_windows.length) {
        const period = business.export_windows[nextWindow];
        const blob = await fetchBusinessExport(undefined, period.start, period.end, controller.signal, business.grant_id);
        controller.signal.throwIfAborted();
        saveBlobDownload(blob, `business-export-${period.start}-${period.end}.zip`);
        nextWindow += 1;
        setJournal({ nextWindow, state: "loading" });
      }
      setJournal({ nextWindow, state: "complete" });
    } catch {
      if (!controller.signal.aborted) setJournal({ nextWindow, state: "failed" });
    } finally {
      if (request.current === controller) request.current = null;
    }
  };

  return <div className="space-y-3" aria-busy={state === "loading"}>
    {!business.export_windows.length ? <p className="text-[14px]">{t("business.lifecycle.export.empty", { defaultValue: "No hay registros ni comprobantes para descargar." })}</p> : null}
    <ul className="space-y-1 text-[14px] tabular-nums">
      {business.export_windows.map(period => <li key={`${period.start}/${period.end}`}>{t("business.export.range", { from: period.start, to: period.end })}</li>)}
    </ul>
    {state === "failed" ? <p role="alert" className="text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.lifecycle.export.failed", { defaultValue: "No pudimos iniciar todas las descargas. Reintenta para continuar." })}</p> : null}
    {state === "complete" ? <p role="status" className="text-[14px]">{t("business.lifecycle.export.complete", { defaultValue: "Se iniciaron todas las descargas. Revisa las descargas de tu navegador." })}</p> : null}
    {business.export_windows.length ? <button type="button" className={primaryButtonClass} disabled={state === "loading" || state === "complete"} onClick={() => { void download(); }}>
      {state === "loading" ? t("business.lifecycle.export.preparing", { defaultValue: "Preparando las descargas…" }) : state === "failed" ? t("common.retry") : label}
    </button> : null}
  </div>;
}
