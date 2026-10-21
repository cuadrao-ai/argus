"use client";

import { createContext, useContext, type ReactNode } from "react";
import { businessBankMatchingEnabled } from "@/lib/private-alpha-flags";

/**
 * Whether the third screen is Transacciones or Gastos. The web flag
 * `businessBankMatchingEnabled` owns it; the local design preview and tests
 * may turn it on for their own tree. Default off.
 */
const TransaccionesGateContext = createContext<boolean>(businessBankMatchingEnabled);

export function TransaccionesGate({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  return <TransaccionesGateContext.Provider value={enabled}>{children}</TransaccionesGateContext.Provider>;
}

export function useTransaccionesEnabled(): boolean {
  return useContext(TransaccionesGateContext);
}
