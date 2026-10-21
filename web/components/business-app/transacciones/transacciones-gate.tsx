"use client";

import { createContext, useContext, type ReactNode } from "react";
import { businessBankMatchingEnabled } from "@/lib/private-alpha-flags";

/**
 * Whether Transacciones igualas against the bank: movements, suggestions,
 * the run and the Por igualar segments. With it off the screen lists the
 * period's saved gastos and ventas. The web flag
 * `businessBankMatchingEnabled` owns it; the local design preview and tests
 * may turn it on for their own tree. Default off.
 */
const IgualarGateContext = createContext<boolean>(businessBankMatchingEnabled);

export function IgualarGate({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  return <IgualarGateContext.Provider value={enabled}>{children}</IgualarGateContext.Provider>;
}

export function useIgualarEnabled(): boolean {
  return useContext(IgualarGateContext);
}
