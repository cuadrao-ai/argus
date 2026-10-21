"use client";

import { createContext, useContext, type ReactNode } from "react";
import { businessBankMatchingEnabled } from "@/lib/private-alpha-flags";

/**
 * Whether Transacciones igualas against the bank: movements, suggestions,
 * the run and the Por igualar segments. With it off the screen lists the
 * period's saved gastos. The web flag `businessBankMatchingEnabled` owns it;
 * the local design preview and tests may turn it on for their own tree.
 * Default off. Beside the sample workspace the bank is the sample bank,
 * unless the preview asks for the real routes (`transport="api"`).
 */
type Gate = Readonly<{ enabled: boolean; transport: "sample" | "api" }>;

const IgualarGateContext = createContext<Gate>({ enabled: businessBankMatchingEnabled, transport: "sample" });

export function IgualarGate({ enabled, transport = "sample", children }: { enabled: boolean; transport?: Gate["transport"]; children: ReactNode }) {
  return <IgualarGateContext.Provider value={{ enabled, transport }}>{children}</IgualarGateContext.Provider>;
}

export function useIgualarEnabled(): boolean {
  return useContext(IgualarGateContext).enabled;
}

export function useBankTransport(): Gate["transport"] {
  return useContext(IgualarGateContext).transport;
}
