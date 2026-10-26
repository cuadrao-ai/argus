"use client";
import { createContext } from "react";
import type { RecordRow } from "./transacciones-model";

/** Explicit loaded-row preview; it does not replace a failed detail response. */
export const RecordGlanceContext = createContext<((row: RecordRow) => void) | null>(null);

export const RecordEvidenceContext = createContext<((row: RecordRow) => void) | null>(null);
