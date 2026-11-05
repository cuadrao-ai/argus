"use client";

import { createContext, useContext } from "react";
import { businessReceivingChannels } from "@/lib/business-api";
import type { BusinessContextValue } from "./BusinessWorkspace";

export const BusinessContext = createContext<BusinessContextValue | null>(null);

export function useBusiness(): BusinessContextValue {
  const value = useContext(BusinessContext);
  if (!value) throw new Error("useBusiness must be used inside BusinessWorkspaceProvider");
  return value;
}

/** Shared settings can render outside Business; that never enables its channels. */
export function useReceivingChannels() {
  return useContext(BusinessContext)?.receivingChannels ?? businessReceivingChannels(null);
}
