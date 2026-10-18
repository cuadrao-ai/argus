"use client";

import { createContext, useContext } from "react";

export type BusinessConsentValue = {
  /** Current notice version is accepted for this person. */
  accepted: boolean;
  /** Bring the notice back. Model features call this instead of running. */
  reopen: () => void;
};

const ALLOWED: BusinessConsentValue = { accepted: true, reopen: () => {} };

/**
 * Absent outside the Business gate (design preview and panel tests). Those
 * surfaces are not the signed-in consent flow, so model actions stay as the
 * screen under test left them.
 */
export const BusinessConsentContext = createContext<BusinessConsentValue | null>(null);

export function useBusinessConsent(): BusinessConsentValue {
  return useContext(BusinessConsentContext) ?? ALLOWED;
}
