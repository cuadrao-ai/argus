"use client";

import { createContext, useContext } from "react";

export type BusinessConsentValue = {
  accepted: boolean;
  reopen: () => void;
};

const ALLOWED: BusinessConsentValue = { accepted: true, reopen: () => {} };

export const BusinessConsentContext = createContext<BusinessConsentValue | null>(null);

export function useBusinessConsent(): BusinessConsentValue {
  return useContext(BusinessConsentContext) ?? ALLOWED;
}
