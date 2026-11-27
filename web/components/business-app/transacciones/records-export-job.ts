"use client";

import { createContext, useContext, useSyncExternalStore } from "react";
import type { TFunction } from "i18next";
import { reportFailure, type ReportFailure, type ReportingTransport } from "@/lib/business-reporting-wire";
import type { RecordsExportChoice, RecordsExportFile, ReportRequest, ReportScope } from "@/lib/business-reports-api";
import { chooseSavePlace, saveToPlace, type SaveAsPlace } from "@/lib/save-file-as";

/** What Exportar was opened on: the table's request as it stood, and how the screen names it. */
export type ExportPanelRequest = { scope: ReportScope; request: ReportRequest; periodLabel: string; filterCount: number };

/** One file to build and save. Reintentar runs the same one again. */
export type ExportRun = {
  panel: ExportPanelRequest;
  choice: RecordsExportChoice;
  filename: string;
  exportFile: ReportingTransport["exportFile"];
  /** Says the result once the file is saved or downloaded. */
  onSaved: (result: "saved" | "downloaded", file: RecordsExportFile) => void;
};

export type ExportJobState =
  | { kind: "idle" }
  | { kind: "preparing"; run: ExportRun; at: number }
  | { kind: "done"; run: ExportRun; at: number }
  /** `toPlace`: the person had chosen a Save As place for the file that failed. */
  | { kind: "failed"; run: ExportRun; at: number; problem: ReportFailure; toPlace: boolean };

type Snapshot = { state: ExportJobState; panel: ExportPanelRequest | null };

const LIMIT_CODES = new Set(["business_report_too_large"]);

/** The sentence for an export that failed, in the island and in the panel. */
export function exportFailureText(t: TFunction, problem: ReportFailure, toPlace: boolean): string {
  if (problem.kind === "access") return t("business.transactions.reporting.access_unavailable");
  if (LIMIT_CODES.has(problem.code)) return t("business.export.limit_error");
  return t(toPlace ? "business.transactions.reporting.export.save_failed" : "business.transactions.reporting.export.error");
}

/**
 * The one Registros export of this workspace: which panel is open, and the file
 * being prepared. It outlives the panel, so the island and the panel read the
 * same run. One export runs at a time.
 */
export class RecordsExportJob {
  private current: Snapshot = { state: { kind: "idle" }, panel: null };
  private listeners = new Set<() => void>();
  /** The Save As place of a file that failed, kept so Reintentar does not ask where again. */
  private place: SaveAsPlace | null = null;
  private picking = false;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  snapshot = () => this.current;

  private set(next: Partial<Snapshot>) {
    this.current = { ...this.current, ...next };
    this.listeners.forEach((listener) => listener());
  }

  open(panel: ExportPanelRequest) {
    this.set({ panel });
  }

  /** The panel again, on the request of the file that failed. */
  reopen() {
    const { state } = this.current;
    if (state.kind === "failed") this.set({ panel: state.run.panel });
  }

  /** Closing never stops a file being prepared. Closing on a failure lets it go, with the empty file Save As made. */
  close() {
    if (this.current.state.kind !== "failed") return this.set({ panel: null });
    void this.place?.discard();
    this.place = null;
    this.set({ panel: null, state: { kind: "idle" } });
  }

  /** Call it in the click itself: the browser opens Save As only during the click, before the server builds the file. */
  async start(run: ExportRun) {
    if (this.picking || this.current.state.kind === "preparing") return;
    this.picking = true;
    const kept = this.place?.filename === run.filename ? this.place : null;
    if (!kept) void this.place?.discard();
    const chosen = kept ?? await chooseSavePlace(run.filename, run.choice.format);
    this.picking = false;
    const place = chosen === "cancelled" ? null : chosen;
    this.place = place;
    if (chosen === "cancelled") return;
    this.set({ panel: null, state: { kind: "preparing", run, at: Date.now() } });
    let file: RecordsExportFile;
    try {
      file = await run.exportFile(run.panel.scope, run.panel.request, run.choice);
    } catch (error) {
      this.set({ state: { kind: "failed", run, at: Date.now(), problem: reportFailure(error), toPlace: place !== null } });
      return;
    }
    this.place = null;
    const result = await saveToPlace(place, file.blob, file.filename);
    this.set({ state: { kind: "done", run, at: Date.now() } });
    run.onSaved(result, file);
  }
}

/** The workspace provides its own. A screen mounted alone gets this one. */
export const RecordsExportJobContext = createContext(new RecordsExportJob());

export function useRecordsExportJob() {
  const job = useContext(RecordsExportJobContext);
  return { job, ...useSyncExternalStore(job.subscribe, job.snapshot, job.snapshot) };
}
