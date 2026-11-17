"use client";
import { createContext } from "react";
import type { RecordRow } from "./transacciones-model";
import type { ReportRecord } from "@/lib/business-reports-api";

/** Pass the selected row to its panel without replacing its detail request. */
export type RefreshRecordRow = (signal?: AbortSignal) => Promise<RecordRow | null>;
export const RecordGlanceContext = createContext<((row: RecordRow, refresh?: RefreshRecordRow) => void) | null>(null);

export const RecordEvidenceContext = createContext<((row: RecordRow) => void) | null>(null);

/** The selected report's answer, never a verdict inferred from the detail form. */
export const RecordReadinessContext = createContext<(Pick<ReportRecord, "ready"> & { missing: Readonly<ReportRecord["missing"]> }) | null>(null);
export const RecordRowsContext = createContext<((rows: readonly RecordRow[]) => void) | null>(null);

/** The keys of the rows that just arrived on their own; a row marks itself for a moment. */
export const RecordArrivalsContext = createContext<ReadonlySet<string>>(new Set());
