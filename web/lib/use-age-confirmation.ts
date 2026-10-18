"use client";

import { useSyncExternalStore } from "react";
import { readAgeConfirmation, subscribeAgeConfirmation } from "./age-confirmation";

export function useAgeConfirmation() {
  return useSyncExternalStore(subscribeAgeConfirmation, readAgeConfirmation, () => null);
}
