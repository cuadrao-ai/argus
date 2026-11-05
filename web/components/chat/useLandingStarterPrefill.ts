"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  captureLandingIntentFromLocation,
  LANDING_STARTER_COPY_FALLBACKS,
  landingStarterAppliedThisRuntime,
  landingStarterCopyKey,
  landingStarterSurfaceEpoch,
  stripLandingStarterFromLocation,
  takeLandingStarterPrefill,
  type LandingStarter,
} from "@/lib/landing-intent";

export function useLandingStarterPrefill(canConsume: boolean): string | null {
  const { t } = useTranslation();
  const epoch = landingStarterSurfaceEpoch();
  const [prefill, setPrefill] = useState<{
    epoch: number;
    starter: LandingStarter | null;
  }>(() => ({ epoch, starter: null }));
  const starter = prefill.epoch === epoch ? prefill.starter : null;

  useEffect(() => {
    captureLandingIntentFromLocation();
    if (!canConsume) return;
    const next =
      takeLandingStarterPrefill() ?? landingStarterAppliedThisRuntime();
    if (next) stripLandingStarterFromLocation();
    setPrefill({ epoch, starter: next });
  }, [canConsume, epoch]);

  if (!starter) return null;
  return t(landingStarterCopyKey(starter), LANDING_STARTER_COPY_FALLBACKS[starter]);
}
