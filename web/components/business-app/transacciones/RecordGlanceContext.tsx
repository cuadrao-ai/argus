"use client";
import { createContext } from "react";
import type { DossierDetailsCard } from "../BusinessWorkspace";
import type { RecordRow } from "./transacciones-model";

/** Opening a connected report row also saves its anchor and URL. */
export type OpenRecordGlance = (row: RecordRow, options?: { detailsCard?: DossierDetailsCard }) => void;
export const RecordGlanceContext = createContext<OpenRecordGlance | null>(null);

/** The keys of the rows that just arrived on their own; a row marks itself for a moment. */
export const RecordArrivalsContext = createContext<ReadonlySet<string>>(new Set());
