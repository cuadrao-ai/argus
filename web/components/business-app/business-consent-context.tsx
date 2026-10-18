"use client";

import { createContext, useContext, type ReactNode } from "react";

export type BusinessConsentValue = {
  accepted: boolean;
  reopen: () => void;
};

const OPEN: BusinessConsentValue = { accepted: true, reopen: () => {} };
const CLOSED: BusinessConsentValue = { accepted: false, reopen: () => {} };

export const BusinessConsentContext = createContext<BusinessConsentValue | null>(null);

export function useBusinessConsent(): BusinessConsentValue {
  return useContext(BusinessConsentContext) ?? CLOSED;
}

export function BusinessConsentTestProvider({
  accepted,
  children,
}: {
  accepted: boolean;
  children: ReactNode;
}) {
  return (
    <BusinessConsentContext.Provider value={accepted ? OPEN : CLOSED}>
      {children}
    </BusinessConsentContext.Provider>
  );
}
