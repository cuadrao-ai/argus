"use client";

import { createContext, useContext, useSyncExternalStore } from "react";
import type { TFunction } from "i18next";
import { reportFailure, type ReportFailure, type ReportingTransport } from "@/lib/business-reporting-wire";
import { reportRequestSchema, type RecordsExportChoice, type RecordsExportFile, type ReportRequest, type ReportScope } from "@/lib/business-reports-api";
import { chooseSavePlace, saveToPlace, type SaveAsPlace } from "@/lib/save-file-as";

/** What Exportar was opened on: the table's request as it stood, and how the screen names it. */
export type ExportPanelRequest = { scope: ReportScope; request: ReportRequest; periodLabel: string; filterCount: number };

/** Records an action inside Exportar asks the screen to show. */
export type ExportReview = Pick<ExportPanelRequest, "scope" | "request">;

/** The purchases a 606 holds back for fiscal data: the panel's own period and family in the form's currency, with no other filter. */
export function pendingFiscalReview({ scope, request }: ExportPanelRequest, currency: string): ExportReview {
  const { period, record_families } = request.filters;
  return { scope, request: reportRequestSchema.parse({ filters: { period, record_families, currencies: [currency], fiscal_data: "missing" } }) };
}

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
  /** `place`: the Save As place chosen for the file that failed. Only that same file's Reintentar writes there. */
  | { kind: "failed"; run: ExportRun; at: number; problem: ReportFailure; place: SaveAsPlace | null };

type Snapshot = { state: ExportJobState; panel: ExportPanelRequest | null };
type ExportFailure = Extract<ExportJobState, { kind: "failed" }>;

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/**
 * The failure, when it is this request's own: the same Business and table
 * request and, once the panel has its choices, the same file. A failure never
 * shows on another request.
 */
export function failureOn(state: ExportJobState, panel: Pick<ExportPanelRequest, "scope" | "request"> | null, choice?: RecordsExportChoice | null): ExportFailure | null {
  if (state.kind !== "failed" || !panel) return null;
  const { run } = state;
  return same(run.panel.scope, panel.scope) && same(run.panel.request, panel.request) && (!choice || same(run.choice, choice)) ? state : null;
}

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

  /** A failed file that is let go takes the empty file its Save As made with it. */
  private letGo(failed: ExportFailure, next: Partial<Snapshot> = {}) {
    void failed.place?.discard();
    this.set({ ...next, state: { kind: "idle" } });
  }

  /** Closing never stops a file being prepared. Closing the panel of a file that failed lets the failure go. */
  close() {
    const failed = failureOn(this.current.state, this.current.panel);
    if (failed) this.letGo(failed, { panel: null });
    else this.set({ panel: null });
  }

  /** Call it in the click itself: the browser opens Save As only during the click, before the server builds the file. */
  async start(run: ExportRun) {
    if (this.picking || this.current.state.kind === "preparing") return;
    const { state } = this.current;
    const own = failureOn(state, run.panel, run.choice);
    // Another file replaces the failed one before Save As opens: the person may pick the same name for it.
    if (!own && state.kind === "failed") this.letGo(state);
    this.picking = true;
    const place = own?.place ?? await chooseSavePlace(run.filename, run.choice.format);
    this.picking = false;
    if (place === "cancelled") return;
    this.set({ panel: null, state: { kind: "preparing", run, at: Date.now() } });
    let file: RecordsExportFile;
    try {
      file = await run.exportFile(run.panel.scope, run.panel.request, run.choice);
    } catch (error) {
      this.set({ state: { kind: "failed", run, at: Date.now(), problem: reportFailure(error), place } });
      return;
    }
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
